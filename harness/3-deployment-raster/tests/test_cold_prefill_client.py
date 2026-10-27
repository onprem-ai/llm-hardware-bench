"""The cold client must be runnable by a person who only has a URL and a key (R-03-28).

Tests drive a stub benchmark binary, so they assert the tool's own contract: it refuses
without a credential in the environment, it refuses when the installed build lacks the input
controls that make a run cold, it halts instead of reporting cache-served work, and the
credential never appears in anything it writes.
"""
from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
CLIENT = REPO / "harness" / "3-deployment-raster" / "code" / "cold-prefill-client.py"

STUB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
argv = sys.argv[1:]
if "--help" in argv:
    # Mirrors the flag surface verified against the real aiperf 0.13.0 build.
    print("usage: aiperf profile [--isl N] [--isl-stddev N] [--osl N] [--osl-stddev N] "
          "[--custom-dataset-type T] [--input-file F] [--num-dataset-entries N] "
          "[--dataset-sampling-strategy S] [--server-metrics] [--concurrency C] "
          "[--benchmark-duration S] [--benchmark-grace-period P] [--use-server-token-count] "
          "[--extra-inputs KV] [--request-timeout-seconds S] [--endpoint-type T] [--streaming] "
          "[--api-key KEY] [--url URL] [--model M] [--tokenizer T] [--output-artifact-dir D]")
    sys.exit(0)
def flag(name):
    return argv[argv.index(name) + 1] if name in argv else None
out = pathlib.Path(flag("--output-artifact-dir")); out.mkdir(parents=True, exist_ok=True)
served = float(os.environ.get("FAKE_SERVED_PCT", "0"))
queries = 2_048 * 400
(out / "profile_export_aiperf.json").write_text(json.dumps({
    "input_token_throughput": {"avg": 12_345.6, "unit": "tokens/sec"},
    "request_count": {"avg": 400}}))
(out / "server_metrics_export.json").write_text(json.dumps({"metrics": {
    "vllm:prefix_cache_hits": {"series": [{"stats": {"total": int(queries * served / 100)}}]},
    "vllm:prefix_cache_queries": {"series": [{"stats": {"total": queries}}]}}}))
print("invoked with", " ".join(argv))
'''


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.aiperf = self.tmp / "aiperf"
        self.aiperf.write_text(STUB)
        self.aiperf.chmod(self.aiperf.stat().st_mode | stat.S_IEXEC)

    def call(self, *extra, token="sekret-token-8f31", env_extra=None, expect=None):
        env = {**os.environ, "PATH": f"{self.tmp}:{os.environ['PATH']}"}
        env.pop("APIKEY", None)
        if token:
            env["APIKEY"] = token
        env.setdefault("FAKE_SERVED_PCT", "0")
        env.update(env_extra or {})
        p = subprocess.run([sys.executable, str(CLIENT), "--url", "https://example.invalid",
                            "--model", "test-model", "--aiperf", str(self.aiperf),
                            "--grid", "8,32", "--reps", "1", *extra],
                           capture_output=True, text=True, env=env)
        if expect is not None:
            self.assertEqual(expect, p.returncode, p.stdout + p.stderr)
        return p


class Refusals(Harness):
    def test_missing_credential_in_environment_is_refused(self):
        p = self.call("--out", str(self.tmp / "o1"), token=None, expect=2)
        self.assertIn("REFUSED", p.stderr)
        self.assertIn("argument", p.stderr)   # explains why argv is not acceptable

    def test_refusal_names_the_variable_to_set(self):
        self.assertIn("APIKEY", self.call("--out", str(self.tmp / "o1"), token=None).stderr)

    def test_unrecognised_input_vocabulary_is_refused(self):
        """A build that matches neither vocabulary must not be measured with guessed flags."""
        odd = self.tmp / "aiperf-unknown-vocab"
        odd.write_text(STUB.replace("[--isl N] ", "").replace("[--custom-dataset-type T] ", ""))
        odd.chmod(odd.stat().st_mode | stat.S_IEXEC)
        env = {**os.environ, "APIKEY": "x"}
        p = subprocess.run([sys.executable, str(CLIENT), "--url", "https://example.invalid",
                            "--model", "m", "--aiperf", str(odd), "--grid", "8", "--reps", "1",
                            "--out", str(self.tmp / "o3")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(2, p.returncode)
        self.assertIn("REFUSED", p.stderr)
        self.assertIn("vocabulary", p.stderr)

    def test_build_without_corpus_control_is_refused_when_a_book_is_requested(self):
        book = self.tmp / "book.txt"
        book.write_text(" ".join(f"Sentence {i} has many words in it." for i in range(200_000)))
        stripped = self.tmp / "aiperf-nocorpus"
        stripped.write_text(STUB.replace("[--input-file F] ", ""))  # --custom-dataset-type kept
        stripped.chmod(stripped.stat().st_mode | stat.S_IEXEC)
        env = {**os.environ, "APIKEY": "x"}
        p = subprocess.run([sys.executable, str(CLIENT), "--url", "https://example.invalid",
                            "--model", "m", "--aiperf", str(stripped), "--grid", "8",
                            "--reps", "1", "--book", str(book),
                            "--out", str(self.tmp / "o2")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(2, p.returncode)
        self.assertIn("--input-file", p.stderr)


class AnonymousEndpoint(Harness):
    """An unauthenticated endpoint is a real case; inventing a key to satisfy the tool is not."""

    def test_anonymous_requires_an_explicit_declaration(self):
        p = self.call("--out", str(self.tmp / "a1"), token=None, expect=2)
        self.assertIn("--allow-anonymous", p.stderr)

    def test_declared_anonymous_endpoint_runs_without_a_credential(self):
        out = self.tmp / "a2"
        p = subprocess.run([sys.executable, str(CLIENT), "--url", "https://example.invalid",
                            "--model", "m", "--aiperf", str(self.aiperf), "--grid", "8",
                            "--reps", "1", "--allow-anonymous", "--out", str(out)],
                           capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if k != "APIKEY"})
        self.assertEqual(0, p.returncode, p.stdout + p.stderr[-400:])
        self.assertIn("credential flag --api-key", p.stdout)
        # no key existed, so nothing can have leaked; the plan must not carry an auth value
        self.assertNotIn("--api-key ''", (out / "commands.log").read_text())


class ColdSweep(Harness):
    def test_cold_run_produces_a_reportable_number(self):
        out = self.tmp / "cold"
        self.call("--out", str(out), env_extra={"FAKE_SERVED_PCT": "0"}, expect=0)
        result = json.loads((out / "result.json").read_text())
        self.assertFalse(result["halted"])
        self.assertTrue(result["claim_permitted"])
        self.assertEqual({"8", "32"}, set(result["cold_input_tokens_per_s_by_concurrency"]))

    def test_cache_reads_halt_the_sweep_and_yield_no_headline(self):
        out = self.tmp / "warm"
        self.call("--out", str(out), env_extra={"FAKE_SERVED_PCT": "88.9"}, expect=1)
        self.assertTrue((out / "INVALID.cold-cache").is_file())
        result = json.loads((out / "result.json").read_text())
        self.assertTrue(result["halted"])
        self.assertFalse(result["claim_permitted"])
        self.assertEqual({}, result["cold_input_tokens_per_s_by_concurrency"])

    def test_absent_counters_are_unknown_and_not_cold(self):
        out = self.tmp / "unknown"
        self.call("--out", str(out), env_extra={"FAKE_SERVED_PCT": "0"}, expect=0)
        rows = json.loads((out / "result.json").read_text())["runs"]
        self.assertTrue(all(r["cache_verdict"] == "cold" for r in rows))


class CredentialHygiene(Harness):
    def test_token_never_appears_in_logs_or_results(self):
        out = self.tmp / "hygiene"
        token = "sekret-token-8f31"
        self.call("--out", str(out), token=token, expect=0)
        for path in sorted(out.rglob("*")):
            if path.is_file():
                text = path.read_text(errors="replace")
                self.assertNotIn(token, text, f"credential leaked into {path.name}")
        commands = (out / "commands.log").read_text()
        self.assertIn("[REDACTED]", commands)
        self.assertIn("--api-key", commands)          # the flag is visible; the value is not

    def test_plan_mode_is_deterministic_and_credentials_stay_in_the_environment(self):
        first = self.call("--plan", "--out", str(self.tmp / "p"), expect=0).stdout
        second = self.call("--plan", "--out", str(self.tmp / "p"), expect=0).stdout
        self.assertEqual(first, second, "the same arguments must emit the same commands")
        self.assertNotIn("sekret-token-8f31", first)
        self.assertIn("aiperf profile", first)
        self.assertEqual(2, first.count("--concurrency"), "grid 8,32 x 1 rep = 2 commands")
        self.assertIn("token from $APIKEY: set", first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
