#!/usr/bin/env python3
"""
Analytics C2 producer — pontualidade (on-time performance).

Consumes a C1 raw flight dataset (C1 v1.0.0) and produces the C2 punctuality
indicator (C2 v1.1.0), grouped by (directional route x airline x reference month).

Source of truth for the numbers this script encodes:
  - docs/ecosystem/contracts.md            -> C1 v1.0.0 (input) / C2 v1.0.0 (output)
  - docs/product/metrics-definitions.md    -> pontualidade v1.0.0

Scope (Sprint 1, Walking Skeleton): one metric (pontualidade), flat files only.
Stdlib only: csv, json, hashlib (reserved), datetime, argparse.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone

# --- Frozen constants encoded from the contracts (single source of truth) ----

ANALYTICS_VERSION = "1.1.0"            # semver of this Analytics logic (determinism)
C1_CONTRACT_VERSION = "v1.0.0"
METRIC_ID = "pontualidade"
METRIC_VERSION = "v1.1.0"
METRIC_DEFINITION_SOURCE = "docs/product/metrics-definitions.md#pontualidade"
ON_TIME_BASIS = "arrival"             # punctuality measured at arrival to destination
ON_TIME_THRESHOLD_MINUTES = 15        # <= 15 min inclusive; early counts as on-time
ON_TIME_THRESHOLD = timedelta(minutes=ON_TIME_THRESHOLD_MINUTES)
TIMEZONE = "America/Sao_Paulo"        # VRA publishes naive local (Brasilia) times

# ICAO -> IATA map is Analytics' responsibility (NOT C1). Never invent: absent -> None.
ICAO_TO_IATA = {
    "SBSP": "CGH",
    "SBRJ": "SDU",
}

# Flight status enum (raw, exactly as published by the source; no translation).
STATUS_REALIZADO = "REALIZADO"
STATUS_CANCELADO = "CANCELADO"
STATUS_NAO_INFORMADO = "NÃO INFORMADO"

# Accepted timestamp input formats. C1 timestamps are naive (America/Sao_Paulo).
# ISO forms are canonical; DD/MM/YYYY is accepted as a defensive fallback (C0 source form).
_TS_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)


def parse_ts(value):
    """Parse a naive C1 timestamp. Empty / whitespace -> None (nullable field)."""
    if value is None:
        return None
    v = value.strip()
    if v == "":
        return None
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    raise ValueError("Unparseable timestamp: %r" % value)


def clean(value):
    """Strip a string cell; empty -> None (never invent values)."""
    if value is None:
        return None
    v = value.strip()
    return v if v != "" else None


def reference_month_of(row):
    """Derive YYYY-MM from reference_date, falling back to scheduled arrival/departure."""
    ref_date = clean(row.get("reference_date"))
    if ref_date and len(ref_date) >= 7:
        # reference_date is 'YYYY-MM-DD' (day of service).
        return ref_date[:7]
    for key in ("scheduled_arrival", "scheduled_departure"):
        ts = parse_ts(row.get(key))
        if ts is not None:
            return ts.strftime("%Y-%m")
    raise ValueError("Cannot derive reference_month for row: no reference_date/scheduled")


def iata_of(icao):
    """Map ICAO->IATA; unknown ICAO -> None (never invented)."""
    if icao is None:
        return None
    return ICAO_TO_IATA.get(icao)


class Group:
    """Accumulator for one (route_id, airline_icao, reference_month) key."""

    __slots__ = (
        "route_id", "route_pair_id", "origin_icao", "dest_icao",
        "airline_icao", "airline_name", "reference_month",
        "flights_operated", "flights_on_time",
        "flights_cancelled", "flights_not_reported",
        "flights_operated_missing_arrival", "flights_operated_missing_schedule",
        "rows_seen", "lineage", "source_year_months",
    )

    def __init__(self, origin_icao, dest_icao, airline_icao, reference_month):
        self.origin_icao = origin_icao
        self.dest_icao = dest_icao
        self.airline_icao = airline_icao
        self.reference_month = reference_month
        self.route_id = "%s-%s" % (origin_icao, dest_icao)                    # directional
        self.route_pair_id = "-".join(sorted([origin_icao, dest_icao]))       # non-directional
        self.airline_name = None
        self.flights_operated = 0
        self.flights_on_time = 0
        self.flights_cancelled = 0
        self.flights_not_reported = 0
        self.flights_operated_missing_arrival = 0
        self.flights_operated_missing_schedule = 0
        self.rows_seen = 0
        self.lineage = {}            # (source_file, file_sha256, source_year_month) -> None (dedupe)
        self.source_year_months = set()

    def add(self, row):
        self.rows_seen += 1

        # airline_name: inherited from C1; first non-null wins, never invented.
        if self.airline_name is None:
            self.airline_name = clean(row.get("airline_name"))

        # Lineage / provenance (derived from C1 provenance columns).
        sf = clean(row.get("source_file"))
        sha = clean(row.get("file_sha256"))
        sym = clean(row.get("source_year_month"))
        if sym is not None:
            self.source_year_months.add(sym)
        self.lineage[(sf, sha, sym)] = None

        status = clean(row.get("flight_status"))
        actual_arrival = parse_ts(row.get("actual_arrival"))
        scheduled_arrival = parse_ts(row.get("scheduled_arrival"))

        if status == STATUS_REALIZADO:
            if actual_arrival is None:
                # Missing arrival: punctuality unmeasurable. Reported, not judged.
                self.flights_operated_missing_arrival += 1
            elif scheduled_arrival is None:
                # Missing schedule: pontual(v) = (actual - scheduled) <= 15min is
                # UNDEFINED without scheduled_arrival. Keeping such a row in the
                # denominator would silently classify it as late -- inventing a fact
                # the source does not support. Excluded and reported instead.
                self.flights_operated_missing_schedule += 1
            else:
                # Denominator: REALIZADO with both arrival timestamps present.
                self.flights_operated += 1
                # Numerator: subset with (actual - scheduled) <= 15 min (early counts).
                if (actual_arrival - scheduled_arrival) <= ON_TIME_THRESHOLD:
                    self.flights_on_time += 1
        elif status == STATUS_CANCELADO:
            self.flights_cancelled += 1
        elif status == STATUS_NAO_INFORMADO:
            self.flights_not_reported += 1
        else:
            # Unknown status must never be silently dropped (guarantee: no C1 row lost).
            raise ValueError(
                "Unexpected flight_status %r (route=%s airline=%s month=%s)"
                % (status, self.route_id, self.airline_icao, self.reference_month)
            )

    def to_record(self, computed_at_utc):
        operated = self.flights_operated
        on_time = self.flights_on_time
        # on_time_rate: null when denominator = 0 (never 0/0). Full precision fraction.
        on_time_rate = (on_time / operated) if operated > 0 else None

        source_total = (
            operated
            + self.flights_operated_missing_arrival
            + self.flights_operated_missing_schedule
            + self.flights_cancelled
            + self.flights_not_reported
        )
        # Reconciliation guarantee (AC4): every C1 row landed in exactly one bucket.
        assert source_total == self.rows_seen, (
            "source_total (%d) != rows_seen (%d) for %s / %s / %s"
            % (source_total, self.rows_seen, self.route_id,
               self.airline_icao, self.reference_month)
        )

        # source_year_month: the C1 partition. Deterministic: sorted, comma-joined if >1.
        syms = sorted(s for s in self.source_year_months if s is not None)
        source_year_month = ",".join(syms) if syms else None

        # source_lineage: one entry per distinct source file; deterministic sort.
        lineage = [
            {"source_file": sf, "file_sha256": sha, "source_year_month": sym}
            for (sf, sha, sym) in sorted(
                self.lineage.keys(),
                key=lambda t: (t[0] or "", t[1] or "", t[2] or ""),
            )
        ]

        return {
            # --- Keys / dimensions ---
            "route_id": self.route_id,
            "route_pair_id": self.route_pair_id,
            "origin_icao": self.origin_icao,
            "origin_iata": iata_of(self.origin_icao),
            "dest_icao": self.dest_icao,
            "dest_iata": iata_of(self.dest_icao),
            "airline_icao": self.airline_icao,
            "airline_name": self.airline_name,
            "reference_month": self.reference_month,
            "timezone": TIMEZONE,
            # --- Measures ---
            "flights_operated": operated,
            "flights_on_time": on_time,
            "on_time_rate": on_time_rate,
            "flights_cancelled": self.flights_cancelled,
            "flights_not_reported": self.flights_not_reported,
            "flights_operated_missing_arrival": self.flights_operated_missing_arrival,
            "flights_operated_missing_schedule": self.flights_operated_missing_schedule,
            "flights_source_total": source_total,
            # --- Metric provenance ---
            "metric_id": METRIC_ID,
            "metric_version": METRIC_VERSION,
            "metric_definition_source": METRIC_DEFINITION_SOURCE,
            "on_time_basis": ON_TIME_BASIS,
            "on_time_threshold_minutes": ON_TIME_THRESHOLD_MINUTES,
            # --- C1 lineage (reconciliation, AC4) ---
            "c1_contract_version": C1_CONTRACT_VERSION,
            "source_year_month": source_year_month,
            "source_lineage": lineage,
            # --- Audit / determinism ---
            "analytics_version": ANALYTICS_VERSION,
            "computed_at_utc": computed_at_utc,   # informative; outside determinism equality
        }


def analyze(rows):
    """Fold C1 rows into C2 group accumulators. Returns dict keyed by group tuple."""
    groups = {}
    for row in rows:
        origin_icao = clean(row.get("origin_icao"))
        dest_icao = clean(row.get("dest_icao"))
        airline_icao = clean(row.get("airline_icao"))
        reference_month = reference_month_of(row)

        key = ("%s-%s" % (origin_icao, dest_icao), airline_icao, reference_month)
        group = groups.get(key)
        if group is None:
            group = Group(origin_icao, dest_icao, airline_icao, reference_month)
            groups[key] = group
        group.add(row)
    return groups


def build_records(groups, computed_at_utc):
    """Emit C2 records with a stable sort (determinism)."""
    records = [g.to_record(computed_at_utc) for g in groups.values()]
    records.sort(key=lambda r: (r["route_id"], r["airline_icao"] or "", r["reference_month"]))
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description="Produce C2 punctuality from a C1 CSV.")
    parser.add_argument("--input", default="input/c1_flights.csv",
                        help="Path to the C1 CSV (default: input/c1_flights.csv).")
    parser.add_argument("--output", default="output/c2_punctuality.json",
                        help="Path to the C2 JSON output (default: output/c2_punctuality.json).")
    parser.add_argument("--computed-at", default=None,
                        help="Override computed_at_utc (ISO 8601). Default: now (UTC).")
    args = parser.parse_args(argv)

    computed_at_utc = args.computed_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    with open(args.input, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    groups = analyze(rows)
    records = build_records(groups, computed_at_utc)

    with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("Read %d C1 rows -> wrote %d C2 records to %s" %
          (len(rows), len(records), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
