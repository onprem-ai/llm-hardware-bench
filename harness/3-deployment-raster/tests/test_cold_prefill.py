"""Two-sided tests for the cold-prefill gate (R-05-2).

The gate exists because a campaign ran 84 measurements whose prompt pool was 100 prompts
replayed across 312-470 requests, and nothing checked it. A check that is never run against
the evidence that motivated it is not a check, so one test here reads the real mirrored
export of that campaign and requires the gate to reject it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
GATE = REPO / "harness" / "3-deployment-raster" / "code" / "cold_gate.py"
FORMAL = REPO / "studies" / "xe7740" / "_local-evidence" / "xe7740-04" / "glm5.3" / \
    "5-campaign" / "formal-20260907"


def verdict(run_dir: pathlib.Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(GATE), str(run_dir), "--expect-cold"],
                       capture_output=True, text=True)
    line = (p.stdout.strip().splitlines() or [p.stderr.strip()])[-1]
    return p.returncode, line


def fixture(hits, queries, requests=100) -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "server_metrics_export.json").write_text(json.dumps({"metrics": {
        "vllm:prefix_cache_hits": {"series": [{"stats": {"total": hits}}]},
        "vllm:prefix_cache_queries": {"series": [{"stats": {"total": queries}}]},
    }}))
    (d / "profile_export_aiperf.json").write_text(json.dumps({"request_count": requests}))
    return d


class ColdGate(unittest.TestCase):
    def test_zero_hits_is_cold(self):
        self.assertEqual(0, verdict(fixture(0, 228_660))[0])

    def test_fraction_within_limit_is_cold(self):
        self.assertEqual(0, verdict(fixture(6_860, 2_286_600))[0])

    def test_limit_is_inclusive(self):
        self.assertEqual(0, verdict(fixture(2_000, 100_000))[0])

    def test_warm_run_is_rejected(self):
        self.assertEqual(1, verdict(fixture(861_056, 968_200))[0])

    def test_absent_counters_are_not_cold(self):
        """Unknown must never be read as cold: absence of evidence is not evidence of cold."""
        self.assertEqual(2, verdict(pathlib.Path(tempfile.mkdtemp()))[0])

    def test_custom_threshold_is_honoured(self):
        d = fixture(420_608, 642_720)
        self.assertEqual(1, subprocess.run(
            [sys.executable, str(GATE), str(d), "--expect-cold", "--max-served-pct", "2.0"],
            capture_output=True).returncode)
        self.assertEqual(0, subprocess.run(
            [sys.executable, str(GATE), str(d), "--expect-cold", "--max-served-pct", "90"],
            capture_output=True).returncode)

    def test_the_campaign_that_motivated_the_gate_is_rejected(self):
        """The published prefill runs measured heavy prefix-cache reads; the gate must say so."""
        run = FORMAL / "runs" / "prefill" / "c032" / "r1"
        if not run.is_dir():
            self.skipTest("formal evidence not mirrored in this checkout")
        rc, line = verdict(run)
        self.assertEqual(1, rc, f"gate accepted a warm run: {line}")
        self.assertIn("verdict=warm", line)

    def test_decode_shape_measures_no_cache_reads(self):
        """Decode (8-token prompts) is not cache-confounded; the headline depends on this."""
        run = FORMAL / "runs" / "decode" / "c128" / "r1"
        if not run.is_dir():
            self.skipTest("formal evidence not mirrored in this checkout")
        metrics = json.loads((run / "server_metrics_export.json").read_text())["metrics"]
        hits = (metrics["vllm:prefix_cache_hits"]["series"][0]["stats"]["total"])
        queries = (metrics["vllm:prefix_cache_queries"]["series"][0]["stats"]["total"])
        self.assertEqual(0.0, 100.0 * hits / queries)


class CorpusBuilder(unittest.TestCase):
    def test_prompts_are_unique_and_warmup_is_disjoint(self):
        src = pathlib.Path(tempfile.mkdtemp()) / "book.txt"
        sentences = [f"Sentence number {i} of the book has enough words to be counted."
                     for i in range(400_000)]
        src.write_text(" ".join(sentences))
        out = src.parent / "corpus.jsonl"
        man = src.parent / "manifest.json"
        p = subprocess.run([
            sys.executable, str(REPO / "harness" / "3-deployment-raster" / "code" /
                               "make_book_corpus.py"),
            "--source", str(src), "--out", str(out), "--manifest", str(man),
            "--prompts", "40", "--warmup-prompts", "10", "--target-tokens", "256",
            "--skip-head", "0",
        ], capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        prompts = [json.loads(l)["prompt"] for l in out.read_text().splitlines()]
        self.assertEqual(40, len(prompts))
        self.assertEqual(40, len(set(prompts)), "a repeated prompt defeats the cold campaign")
        manifest = json.loads(man.read_text())
        self.assertEqual([10, 50], manifest["measured_passage_range"])
        self.assertEqual([0, 10], manifest["warmup_passage_range"])

    def test_refuses_a_source_too_short_to_be_unique(self):
        src = pathlib.Path(tempfile.mkdtemp()) / "short.txt"
        src.write_text("A very short book. It ends here.")
        p = subprocess.run([
            sys.executable, str(REPO / "harness" / "3-deployment-raster" / "code" /
                               "make_book_corpus.py"),
            "--source", str(src), "--out", str(src.parent / "c.jsonl"),
            "--manifest", str(src.parent / "m.json"), "--prompts", "500",
            "--warmup-prompts", "50", "--skip-head", "0",
        ], capture_output=True, text=True)
        self.assertEqual(2, p.returncode)
        self.assertIn("REFUSED", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
