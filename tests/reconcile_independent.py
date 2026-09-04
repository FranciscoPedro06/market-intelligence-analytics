#!/usr/bin/env python3
"""Independent reconciliation instrument for the C2 punctuality indicator.

WHY THIS EXISTS (GOV-008 / invariant I9)
----------------------------------------
The reconciliation evidence in RECONCILIATION.md was produced by a script that was
never versioned: the numbers survived, the instrument did not. That makes AC4
("every number is reconcilable with the official source") unreproducible by a third
party - the exact risk OE4 exists to eliminate.

This file is that instrument, versioned.

INDEPENDENCE (the whole point)
------------------------------
It recounts C1 from scratch, deriving every rule from the WRITTEN definition in
docs/product/metrics-definitions.md -> "Pontualidade v1.1.0". It MUST NOT import
`analyze` or reuse any function of the pipeline it audits: a recount that calls the
audited code would validate its own error and prove nothing.

Enforced mechanically by tests/test_independence.py, statically and at runtime.

Consequence of that rule: the timestamp parsing, the status classification and the
15-minute comparison below are deliberately written a second time. The duplication
is not an oversight - it is the instrument.

WHAT IT DOES
------------
1. Recounts every (route_id x airline_icao x reference_month) group from the C1 CSV.
2. Optionally compares that recount, field by field, against a C2 document.

The recount stands alone: without --c2 it still produces the evidence. It never
depends on the Analytics output to know what the right answer is.

RULES ENCODED (source: metrics-definitions.md -> pontualidade v1.1.0)
--------------------------------------------------------------------
  on-time(v)   <=>  (actual_arrival - scheduled_arrival) <= 15 min, inclusive.
                    Early arrival counts as on time.
  denominator  =    flight_status == REALIZADO AND actual_arrival AND scheduled_arrival
  numerator    =    subset of the denominator satisfying on-time(v)
  rate         =    numerator / denominator, or None when the denominator is 0
                    (never 0/0, never a fabricated 0.0)
  outside the denominator, each counted on its own:
      CANCELADO                                  -> cancelled
      NAO INFORMADO                              -> not_reported
      REALIZADO without actual arrival           -> missing_arrival
      REALIZADO with actual but no scheduled     -> missing_schedule (unmeasurable)
  source_total =    operated + missing_arrival + missing_schedule
                    + cancelled + not_reported      (closes: no C1 row disappears)

C1 FIELDS USED (source: contracts.md -> C1 v1.0.0)
--------------------------------------------------
  airline_icao, origin_icao, dest_icao, flight_status,
  scheduled_arrival, actual_arrival, source_year_month

`reference_month` of the C2 grain is C1's `source_year_month` (the consumed
partition), per contracts.md.

EXIT CODES
----------
  0  recount produced (and, with --c2, it reconciles)
  1  divergence against the C2 document
  2  a required input is absent - never a silent skip (GOV-005 principle)
  3  the C2 document was produced under a different metric version, so the
     denominators are not comparable; refusing to compare is the honest answer

USAGE
-----
  python tests/reconcile_independent.py
  python tests/reconcile_independent.py --c1 input/c1_flights.csv \
                                        --c2 output/c2_punctuality.json
  python tests/reconcile_independent.py --c1 input/sample_c1.csv   # recount only

Stdlib only: argparse, csv, datetime, json, os, sys.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta

# --- Constants read off the written definition, not off the pipeline ----------

METRIC_ID = "pontualidade"
METRIC_VERSION = "v1.1.0"
METRIC_SOURCE = "docs/product/metrics-definitions.md#pontualidade"

ON_TIME_THRESHOLD = timedelta(minutes=15)   # inclusive; early counts as on time

STATUS_DONE = "REALIZADO"
STATUS_CANCELLED = "CANCELADO"
STATUS_NOT_REPORTED = "NÃO INFORMADO"

# C1 timestamps are naive local (America/Sao_Paulo). Written independently of the
# producer: ISO first, then the DD/MM/YYYY form the raw VRA source publishes.
_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)

# Every measure this instrument recounts, in reconciliation order.
MEASURES = (
    "flights_operated",
    "flights_on_time",
    "on_time_rate",
    "flights_cancelled",
    "flights_not_reported",
    "flights_operated_missing_arrival",
    "flights_operated_missing_schedule",
    "flights_source_total",
)


class MissingInput(Exception):
    """A required input is absent. Loud by construction - see exit code 2."""


def parse_timestamp(raw):
    """Parse a C1 timestamp. Empty/blank -> None (the field is nullable)."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError("unparseable C1 timestamp: %r" % raw)


def is_on_time(scheduled_arrival, actual_arrival):
    """on-time(v) <=> (actual - scheduled) <= 15 min, inclusive.

    Undefined when either side is missing - the caller must not reach here in that
    case, because an undefined predicate is not False (that was the v1.0.0 defect).
    """
    return (actual_arrival - scheduled_arrival) <= ON_TIME_THRESHOLD


def _blank_group(route_id, airline_icao, reference_month):
    return {
        "route_id": route_id,
        "airline_icao": airline_icao,
        "reference_month": reference_month,
        "flights_operated": 0,
        "flights_on_time": 0,
        "flights_cancelled": 0,
        "flights_not_reported": 0,
        "flights_operated_missing_arrival": 0,
        "flights_operated_missing_schedule": 0,
    }


def classify(row, group):
    """Place one C1 row in exactly one bucket. Buckets are disjoint and exhaustive."""
    status = (row.get("flight_status") or "").strip()
    scheduled = parse_timestamp(row.get("scheduled_arrival"))
    actual = parse_timestamp(row.get("actual_arrival"))

    if status == STATUS_CANCELLED:
        group["flights_cancelled"] += 1
    elif status == STATUS_NOT_REPORTED:
        group["flights_not_reported"] += 1
    elif status == STATUS_DONE:
        if actual is None:
            # No real arrival: the flight cannot be measured at all.
            group["flights_operated_missing_arrival"] += 1
        elif scheduled is None:
            # Real arrival but nothing to compare it against: punctuality is
            # UNDEFINED, not False. Outside the denominator; never a delay.
            group["flights_operated_missing_schedule"] += 1
        else:
            group["flights_operated"] += 1
            if is_on_time(scheduled, actual):
                group["flights_on_time"] += 1
    else:
        raise ValueError("unknown flight_status in C1: %r" % status)


def finalize(group):
    """Derive rate and the closing total. Rate is None when the denominator is 0."""
    operated = group["flights_operated"]
    group["on_time_rate"] = (group["flights_on_time"] / operated) if operated else None
    group["flights_source_total"] = (
        operated
        + group["flights_operated_missing_arrival"]
        + group["flights_operated_missing_schedule"]
        + group["flights_cancelled"]
        + group["flights_not_reported"]
    )
    return group


def recount(c1_path):
    """Recount every group straight from C1. Returns (groups, rows_read)."""
    if not os.path.exists(c1_path):
        raise MissingInput(c1_path)

    groups = {}
    rows_read = 0
    with open(c1_path, "r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows_read += 1
            route_id = "%s-%s" % (row["origin_icao"], row["dest_icao"])
            key = (route_id, row["airline_icao"], row["source_year_month"])
            group = groups.get(key)
            if group is None:
                group = _blank_group(*key)
                groups[key] = group
            classify(row, group)

    for group in groups.values():
        finalize(group)
    return groups, rows_read


def load_c2(c2_path):
    """Read a C2 document. Accepts the v1.2.0 envelope and the legacy bare array.

    Reading both is deliberate: an audit instrument that could not read historical
    artifacts would be useless for exactly the evidence it exists to reproduce.
    """
    if not os.path.exists(c2_path):
        raise MissingInput(c2_path)
    with open(c2_path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if isinstance(document, dict):
        return document.get("records", []), document.get("contract_version")
    if isinstance(document, list):
        return document, None
    raise ValueError("C2 must be an object with 'records' or a JSON array")


def compare(groups, records):
    """Compare the recount against C2, group by group. Returns a list of findings."""
    findings = []
    by_key = {}
    for record in records:
        key = (record["route_id"], record["airline_icao"], record["reference_month"])
        by_key[key] = record

    for key in sorted(set(groups) | set(by_key)):
        mine, theirs = groups.get(key), by_key.get(key)
        if mine is None:
            findings.append((key, "group", "absent from the recount", "present in C2"))
            continue
        if theirs is None:
            findings.append((key, "group", "present in the recount", "absent from C2"))
            continue
        for measure in MEASURES:
            expected, got = mine[measure], theirs.get(measure)
            if expected != got:
                findings.append((key, measure, expected, got))
    return findings


def render(groups, rows_read, declared_version, findings, compared):
    lines = []
    lines.append("Independent reconciliation - %s %s" % (METRIC_ID, METRIC_VERSION))
    lines.append("  rule source : %s" % METRIC_SOURCE)
    lines.append("  C1 rows read: %d" % rows_read)
    lines.append("  groups      : %d" % len(groups))
    if compared:
        lines.append("  C2 declared : %s" % (declared_version or "undeclared (legacy bare array)"))
    lines.append("")
    header = ("route_id", "air", "month", "oper", "on_time", "rate",
              "canc", "n/rep", "no_arr", "no_sch", "total")
    lines.append("  %-11s %-4s %-8s %6s %8s %-10s %5s %6s %7s %7s %7s" % header)
    total_rows = 0
    for key in sorted(groups):
        g = groups[key]
        rate = "null" if g["on_time_rate"] is None else "%.4f" % g["on_time_rate"]
        total_rows += g["flights_source_total"]
        lines.append("  %-11s %-4s %-8s %6d %8d %-10s %5d %6d %7d %7d %7d" % (
            g["route_id"], g["airline_icao"], g["reference_month"],
            g["flights_operated"], g["flights_on_time"], rate,
            g["flights_cancelled"], g["flights_not_reported"],
            g["flights_operated_missing_arrival"],
            g["flights_operated_missing_schedule"], g["flights_source_total"]))
    lines.append("")
    lines.append("  closure: sum(source_total) = %d ; C1 rows = %d -> %s"
                 % (total_rows, rows_read, "OK" if total_rows == rows_read else "MISMATCH"))

    if compared:
        lines.append("")
        if not findings:
            lines.append("  RECONCILED: every group matches C2 on all %d measures."
                         % len(MEASURES))
        else:
            lines.append("  DIVERGENCE: %d finding(s)." % len(findings))
            for key, field, expected, got in findings:
                lines.append("    %s | %-34s recount=%r  c2=%r"
                             % (" ".join(key), field, expected, got))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Recount C2 punctuality straight from C1, independently of the "
                    "Analytics pipeline (GOV-008 / I9).")
    parser.add_argument("--c1", default="input/c1_flights.csv",
                        help="C1 CSV to recount (default: input/c1_flights.csv)")
    parser.add_argument("--c2", default=None,
                        help="optional C2 document to compare the recount against")
    args = parser.parse_args(argv)

    try:
        groups, rows_read = recount(args.c1)
    except MissingInput as missing:
        print("ERROR: required input absent: %s" % missing, file=sys.stderr)
        print("  This run verified NOTHING. Absence is a failure, not a skip.", file=sys.stderr)
        print("  The C1 dataset is not versioned (output/ and input/ are gitignored).",
              file=sys.stderr)
        print("  Produce it:  cd ../market-intelligence-collector && python src/collect.py",
              file=sys.stderr)
        print("  Then copy:   cp ../market-intelligence-collector/output/c1_flights.csv %s"
              % args.c1, file=sys.stderr)
        return 2

    declared_version, findings, compared = None, [], False
    if args.c2:
        try:
            records, declared_version = load_c2(args.c2)
        except MissingInput as missing:
            print("ERROR: required input absent: %s" % missing, file=sys.stderr)
            print("  Produce it:  python src/analyze.py --input %s" % args.c1, file=sys.stderr)
            return 2

        versions = {r.get("metric_version") for r in records}
        if versions and versions != {METRIC_VERSION}:
            print("ERROR: this instrument encodes %s %s, but the C2 declares %s."
                  % (METRIC_ID, METRIC_VERSION, ", ".join(sorted(map(str, versions)))),
                  file=sys.stderr)
            print("  Denominator rules differ between metric versions, so comparing "
                  "would be meaningless.", file=sys.stderr)
            print("  Refusing to compare rather than reporting a false divergence.",
                  file=sys.stderr)
            return 3

        findings = compare(groups, records)
        compared = True

    print(render(groups, rows_read, declared_version, findings, compared))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
