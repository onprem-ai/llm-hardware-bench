"""Acceptance must re-derive the cache verdict, not trust the harness (R-06-12).

Run against the real mirrored campaign: the prefill series that was published measured heavy
prefix-cache reuse, so acceptance has to say so, and the decode series measured zero cache
reads, so acceptance has to leave it alone. A gate that only fires on fixtures is not a gate.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
BUILD = REPO / "harness" / "6-accept-and-publish" / "code" / "build_acceptance.py"
CAMPAIGN = REPO / "results" / "xe7740-8x-rtx6000" / "glm5.3" / "5-campaign" / "20260907-glm53-radixark-formal"
GATE = REPO / "harness" / "3-deployment-raster" / "code" / "cold_gate.py"


class AcceptanceReComputesVerdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CAMPAIGN.is_dir() or not BUILD.is_file():
            raise unittest.SkipTest("campaign evidence or builder absent")
        cls.out = pathlib.Path(tempfile.mkdtemp()) / "acceptance.json"
        p = subprocess.run([sys.executable, str(BUILD), str(CAMPAIGN), "--out", str(cls.out)],
                           capture_output=True, text=True)
        # the builder must not crash when the record is written outside the campaign tree
        # 3 = collection contract unmet. This campaign really has no telemetry.csv, so
        # acceptance must be withheld; acceptance.json is still written, which is what these
        # tests read to check that the cache verdicts are re-derived, not copied.
        assert p.returncode == 3, p.stderr[-800:]
        cls.doc = json.loads(cls.out.read_text())

    def test_verdict_recorded_for_every_run(self):
        verdicts = self.doc["cache_gate"]["verdicts"]
        self.assertEqual(self.doc["runs"], len(verdicts))
        self.assertTrue(set(verdicts.values()) <= {"cold", "warm", "unknown", "gate-absent"})

    def test_prefill_points_disclose_cache_serving(self):
        prefill = [v for v in self.doc["point_verdicts"] if v["profile"] == "prefill"]
        self.assertTrue(prefill)
        for point in prefill:
            with self.subTest(concurrency=point["concurrency"]):
                self.assertTrue(any("R-06-12" in r for r in point.get("reasons", [])),
                                "a cache-served prefill point was accepted without disclosure")

    def test_decode_points_are_not_wrongly_flagged(self):
        """Decode uses 8-token prompts; flagging it would bury the real signal."""
        for point in self.doc["point_verdicts"]:
            if point["profile"] != "decode":
                continue
            self.assertFalse(any("R-06-12" in r for r in point.get("reasons", [])),
                             f"decode C{point['concurrency']} flagged for prefix cache")

    def test_decode_measured_zero_cache_reads(self):
        """The decode headline stands only because 8-token prompts cannot be cache-served."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("cold_gate", GATE)
        gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
        checked = 0
        for mf in sorted((CAMPAIGN / "runs" / "decode").glob("c*/run-r*/manifest.json")):
            m = json.loads(mf.read_text())
            measured = (mf.parent / m["artifacts"]["measured_dir"]).resolve()
            fraction, _issued, _reason = gate.served_fraction(measured)
            if fraction is None:
                continue
            checked += 1
            self.assertLess(100.0 * fraction, 2.0,
                            f"decode run {mf.parent.name} is cache-served; the decode "
                            "headline would no longer be interpretable")
        self.assertGreater(checked, 0, "no decode run exposed prefix-cache counters")


class GateFailureModes(unittest.TestCase):
    def test_gate_cannot_be_absent_silently(self):
        """A missing gate must show up as a verdict, never as a silent pass."""
        self.assertTrue(GATE.is_file(), "the owning chapter moved the gate; acceptance must follow")

    def test_unknown_is_not_cold(self):
        d = pathlib.Path(tempfile.mkdtemp())
        rc = subprocess.run([sys.executable, str(GATE), str(d), "--expect-cold"],
                            capture_output=True).returncode
        self.assertEqual(2, rc)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class CollectionGateIsPublicationGate(AcceptanceReComputesVerdict):
    """Reuses the campaign built above; asserts the gate, not the cache verdicts."""
    """The campaign that motivated the contract must be the one the contract rejects."""

    def test_incomplete_campaign_cannot_be_published(self):
        self.assertFalse(self.doc["collection_gate"]["permitted"])
        self.assertFalse(self.doc["publication_permitted"])

    def test_the_defect_names_the_missing_hardware_data(self):
        defects = self.doc["collection_gate"]["defects"]
        self.assertTrue(any("telemetry.csv" in d for d in defects), defects)
