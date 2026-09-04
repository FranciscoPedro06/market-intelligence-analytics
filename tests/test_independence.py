#!/usr/bin/env python3
"""Mechanical enforcement of auditor independence (GOV-008 / invariant I9).

THE RULE
--------
    The independent instrument must not import or depend on the audited code to
    produce its evidence.

A recount that calls `analyze` validates its own error and proves nothing. The rule
is therefore not a style preference - it is what makes the evidence evidence.

WHY TWO LAYERS
--------------
A textual scan alone is defeatable: `importlib.import_module("ana" + "lyze")` never
matches a grep, and an intermediate module that itself imports `analyze` is invisible
to any inspection of the instrument's own source. So:

  Layer 1 - STATIC (AST): rejects direct imports of `analyze`, and rejects dynamic
            import machinery (importlib / __import__ / exec / eval) inside the
            instrument. Dynamic imports are not banned because they are evil; they
            are banned because they make the guarantee unauditable, and an
            unauditable guarantee is not one.

  Layer 2 - RUNTIME: executes the instrument in a subprocess with a meta_path finder
            that raises if any module named `analyze` is imported AT ANY DEPTH -
            including through an intermediate module. If the instrument completes
            its real work under that block, it demonstrably never needed the audited
            code. This is the layer that catches indirect dependency.

CONSEQUENCE
-----------
Failure here is a hard failure, not a warning: an instrument that lost its
independence is worse than no instrument, because it produces confident numbers with
no verification behind them.

Run:  python tests/test_independence.py
Stdlib only.
"""

import ast
import os
import subprocess
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)

INSTRUMENT = os.path.join(TESTS_DIR, "reconcile_independent.py")
AUDITED_MODULE = "analyze"
AUDITED_SOURCE = os.path.join(REPO_ROOT, "src", "analyze.py")

# Fixture that ships with the repo, so this test needs no gitignored dataset.
SAMPLE_C1 = os.path.join(REPO_ROOT, "input", "sample_c1.csv")

# Names that would let the instrument reach the audited code without a plain import.
DYNAMIC_IMPORT_NAMES = ("importlib", "__import__", "exec", "eval", "runpy")

# Executed in the subprocess: blocks `analyze` at any depth, then runs the
# instrument as __main__ with the arguments we pass through.
RUNTIME_BLOCKER = r"""
import runpy, sys

BLOCKED = %(blocked)r

class IndependenceBlocker(object):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == BLOCKED:
            raise AssertionError("INDEPENDENCE VIOLATION: imported %%r" %% name)
        return None
    def find_module(self, name, path=None):   # legacy hook, belt and braces
        if name.split(".")[0] == BLOCKED:
            raise AssertionError("INDEPENDENCE VIOLATION: imported %%r" %% name)
        return None

sys.meta_path.insert(0, IndependenceBlocker())

instrument = sys.argv[1]
sys.argv = [instrument] + sys.argv[2:]
try:
    runpy.run_path(instrument, run_name="__main__")
except SystemExit as exc:
    sys.exit(exc.code if exc.code is not None else 0)
"""


def _parse_instrument():
    with open(INSTRUMENT, "r", encoding="utf-8") as handle:
        return ast.parse(handle.read(), filename=INSTRUMENT)


class TestStaticIndependence(unittest.TestCase):
    """Layer 1: the instrument's own source may not name the audited module."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse_instrument()

    def test_instrument_exists(self):
        self.assertTrue(os.path.exists(INSTRUMENT),
                        "the instrument itself must be versioned (I9)")

    def test_no_direct_import_of_the_audited_module(self):
        """Catches `import analyze` and `from analyze import x`."""
        offenders = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == AUDITED_MODULE:
                        offenders.append("line %d: import %s" % (node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] == AUDITED_MODULE:
                    offenders.append("line %d: from %s import ..." % (node.lineno, node.module))
        self.assertEqual(offenders, [],
                         "the instrument imports the code it audits: %s" % offenders)

    def test_no_dynamic_import_machinery(self):
        """Dynamic imports would make the guarantee unauditable, so they are refused."""
        offenders = []
        for node in ast.walk(self.tree):
            name = None
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    name = func.value.id
            elif isinstance(node, ast.Import):
                name = node.names[0].name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                name = (node.module or "").split(".")[0]
            if name in DYNAMIC_IMPORT_NAMES:
                offenders.append("line %d: %s" % (getattr(node, "lineno", -1), name))
        self.assertEqual(offenders, [],
                         "dynamic import machinery makes independence unverifiable: %s"
                         % offenders)

    def test_does_not_add_the_pipeline_source_dir_to_syspath(self):
        """Putting src/ on sys.path is how an 'independent' script quietly stops being one."""
        with open(INSTRUMENT, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("sys.path.insert", source)
        self.assertNotIn("sys.path.append", source)


class TestRuntimeIndependence(unittest.TestCase):
    """Layer 2: it must complete real work while `analyze` is unimportable."""

    def _run_blocked(self, *args):
        script = RUNTIME_BLOCKER % {"blocked": AUDITED_MODULE}
        return subprocess.run(
            [sys.executable, "-c", script, INSTRUMENT] + list(args),
            cwd=REPO_ROOT, capture_output=True, text=True)

    def test_audited_module_is_actually_reachable(self):
        """Guards the guard: if `analyze` were unimportable anyway, the block proves nothing."""
        self.assertTrue(os.path.exists(AUDITED_SOURCE))
        probe = subprocess.run(
            [sys.executable, "-c", "import analyze; print('reachable')"],
            cwd=os.path.join(REPO_ROOT, "src"), capture_output=True, text=True)
        self.assertIn("reachable", probe.stdout,
                      "the audited module must be importable for the block to mean anything")

    def test_blocker_actually_blocks(self):
        """Guards the guard, part two: prove the blocker fires on a real import."""
        script = RUNTIME_BLOCKER % {"blocked": AUDITED_MODULE}
        probe = subprocess.run(
            [sys.executable, "-c", script.replace(
                'instrument = sys.argv[1]',
                'import analyze\ninstrument = sys.argv[1]'), INSTRUMENT],
            cwd=os.path.join(REPO_ROOT, "src"), capture_output=True, text=True)
        self.assertNotEqual(probe.returncode, 0)
        self.assertIn("INDEPENDENCE VIOLATION", probe.stderr)

    def test_instrument_recounts_with_the_audited_module_blocked(self):
        """The real proof: full recount, no access to the pipeline."""
        result = self._run_blocked("--c1", SAMPLE_C1)
        self.assertNotIn("INDEPENDENCE VIOLATION", result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Independent reconciliation", result.stdout)
        self.assertIn("closure:", result.stdout)


class TestInstrumentBehaviour(unittest.TestCase):
    """The instrument must also be correct and must fail loudly on absent input."""

    def _run(self, *args):
        return subprocess.run([sys.executable, INSTRUMENT] + list(args),
                              cwd=REPO_ROOT, capture_output=True, text=True)

    def test_absent_input_fails_and_never_skips(self):
        """GOV-005 principle: absence of input is a failure, not a silent skip."""
        result = self._run("--c1", "input/does_not_exist.csv")
        self.assertEqual(result.returncode, 2)
        self.assertIn("required input absent", result.stderr)
        self.assertIn("verified NOTHING", result.stderr)
        # The real guarantee is behavioural, not lexical: nothing may be reported.
        self.assertNotIn("Independent reconciliation", result.stdout,
                         "an absent input must produce no evidence at all")
        self.assertNotIn("closure:", result.stdout)

    def test_absent_c2_fails_too(self):
        result = self._run("--c1", SAMPLE_C1, "--c2", "output/does_not_exist.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("required input absent", result.stderr)

    def test_recount_matches_the_documented_fixture_result(self):
        """RECONCILIATION.md section 6 documents this fixture's expected outcome:
        TAM SBSP-SBRJ 4/3 -> 0.75 (8 rows) - GLO SBRJ-SBSP 2/1 -> 0.5 (2 rows) -
        ACN SBRJ-SBSP 0/0 -> null (1 row). Total 11."""
        sys.path.insert(0, TESTS_DIR)
        try:
            import reconcile_independent as instrument
        finally:
            sys.path.pop(0)
        groups, rows = instrument.recount(SAMPLE_C1)
        self.assertEqual(rows, 11)
        self.assertEqual(len(groups), 3)

        tam = groups[("SBSP-SBRJ", "TAM", "2023-06")]
        self.assertEqual((tam["flights_operated"], tam["flights_on_time"]), (4, 3))
        self.assertEqual(tam["on_time_rate"], 0.75)
        self.assertEqual(tam["flights_source_total"], 8)

        glo = groups[("SBRJ-SBSP", "GLO", "2023-06")]
        self.assertEqual((glo["flights_operated"], glo["flights_on_time"]), (2, 1))
        self.assertEqual(glo["on_time_rate"], 0.5)

        acn = groups[("SBRJ-SBSP", "ACN", "2023-06")]
        self.assertEqual(acn["flights_operated"], 0)
        self.assertIsNone(acn["on_time_rate"], "denominator 0 must never become 0.0")
        self.assertEqual(acn["flights_operated_missing_schedule"], 1)

        self.assertEqual(sum(g["flights_source_total"] for g in groups.values()), 11,
                         "no C1 row may disappear")

    def test_fifteen_minute_threshold_is_inclusive(self):
        """The boundary the metric definition calls out explicitly."""
        sys.path.insert(0, TESTS_DIR)
        try:
            import reconcile_independent as instrument
        finally:
            sys.path.pop(0)
        from datetime import datetime, timedelta
        scheduled = datetime(2023, 6, 1, 10, 0)
        self.assertTrue(instrument.is_on_time(scheduled, scheduled + timedelta(minutes=15)))
        self.assertFalse(instrument.is_on_time(scheduled, scheduled + timedelta(minutes=16)))
        self.assertTrue(instrument.is_on_time(scheduled, scheduled - timedelta(minutes=10)),
                        "an early arrival counts as on time")


if __name__ == "__main__":
    unittest.main(verbosity=2)
