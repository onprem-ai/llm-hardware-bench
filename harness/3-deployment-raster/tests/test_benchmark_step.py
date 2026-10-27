"""benchmark-step.py must be complete by construction, not by memory.

Fakes stand in for the host capabilities the collection contract depends on (nvidia-smi, docker,
/proc, the benchmark binary, the client, the sampler). Nothing here tests "did the operator
remember": the tests assert that a step which could not collect something refuses, and that a
step which could writes every artifact.
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

REPO = pathlib.Path(__file__).resolve().parents[2].parent
RUNNER = REPO / "harness" / "3-deployment-raster" / "code" / "benchmark-step.py"

NVSMI = r'''#!/usr/bin/env python3
import sys
q = sys.argv[-1] if sys.argv else ""
many = "utilization" in q or "," in q
for i in range(8):
    print(("82.5, 99, 33, 94040" if many else str(82.5 + i)))
'''

DOCKER = r'''#!/usr/bin/env python3
import sys
if "inspect" in sys.argv:
    print("cafebabe0011")
'''

SAMPLER_OK = r'''#!/usr/bin/env python3
import os, pathlib, sys
out = sys.argv[sys.argv.index("--out") + 1]
proc = pathlib.Path(os.environ.get("PROC_ROOT", "/proc"))
assert (proc / "meminfo").is_file() and (proc / "stat").is_file()
base = ["1", "2", "3", "1174097772"] + ["82.5"] * 8 + \
       ["99.0"] * 8 + ["33.0"] * 8 + ["94040.0"] * 8 + ["1", "2", "3", "4", "5", "6", "7", "900"]
rows = [["2026-09-10T07:00:%02dZ" % i] + base for i in range(12)]
pathlib.Path(out).write_text("utc,h,c,p,m,mem_avail,power_w,util_pct\n" +
                             "".join(",".join(r) + "\n" for r in rows))
import time
time.sleep(120)   # a sampler that exits is refused, so the fake must stay alive like the real one
'''

SAMPLER_DEAD = "#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n"

CLIENT_OK = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if "--plan" in args:
    print("plan ok"); raise SystemExit(0)
out = pathlib.Path(args[args.index("--out") + 1])
skip = os.environ.get("FAKE_CLIENT_SKIP") == "1"
for rep in (1, 2, 3):
    d = out / "runs" / "prefill" / "c032" / f"r{rep}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.log").write_text("10:00:00.000 INFO starting\nrunning\n10:01:00.000 INFO done\n")
    if not skip:
        (d / "profile_export_aiperf.json").write_text(json.dumps({"v": 1}))
        (d / "server_metrics_export.json").write_text(json.dumps({"v": 1}))
(out / "result.json").write_text(json.dumps({"points": []}))
print("fake client done")
'''


class Engine:
    """A stand-in inference endpoint: /v1/models advertises the model, which is all the
    runner checks before it will spend GPU time."""

    def __enter__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"data":[{"id":"m"}]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.srv.shutdown()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.srv.server_port}"


def exe(path: pathlib.Path, text: str) -> pathlib.Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        exe(self.bin / "nvidia-smi", NVSMI)
        exe(self.bin / "docker", DOCKER)
        proc = self.tmp / "proc"
        proc.mkdir()
        (proc / "meminfo").write_text("MemTotal:  3000000000 kB\nMemAvailable: 1174097772 kB\n")
        (proc / "stat").write_text("cpu  100 2 30 1000 4 5 6 0 7 0\ncpu0 1 2 3 4 5 6 7 0 0 0\n")
        self.proc = proc
        self.sampler = exe(self.tmp / "sampler.py", SAMPLER_OK)
        self.client = exe(self.tmp / "client.py", CLIENT_OK)
        self.aiperf = exe(self.tmp / "aiperf", "#!/usr/bin/env python3\nprint('ok')\n")
        self.tok = self.tmp / "tokenizer"
        self.tok.mkdir()
        self.corpus = self.tmp / "corpus.jsonl"
        self.corpus.write_text('{"input": "a"}\n')
        self.engine = Engine().__enter__()
        self.addCleanup(self.engine.__exit__, None, None, None)

    def env(self, skip_client: bool = False):
        e = dict(os.environ)
        e["PATH"] = f"{self.bin}:{e['PATH']}"
        e["APIKEY"] = "x"
        if skip_client:
            e["FAKE_CLIENT_SKIP"] = "1"
        return e

    def call(self, out_name="step", extra=(), env=None, sampler=None, url=None):
        return subprocess.run(
            [sys.executable, str(RUNNER), "--container", "eng", "--url", url or self.engine.url,
             "--model", "m",
             "--tokenizer", str(self.tok), "--concurrency", "32", "--reps", "3",
             "--book", str(self.corpus), "--aiperf", str(self.aiperf),
             "--url", url or self.engine.url,
             "--proc-root", str(self.proc), "--sampler", str(sampler or self.sampler),
             "--client", str(self.client), "--out", str(self.tmp / out_name), *extra],
            capture_output=True, text=True, env=env or self.env(), timeout=120)


class Preflight(Harness):
    def test_lists_every_missing_capability_at_once(self):
        e = dict(os.environ)
        e["PATH"] = "/usr/bin:/bin"
        e.pop("APIKEY", None)
        p = self.call(extra=["--preflight"], env=e,
                      sampler=self.tmp / "no-sampler.py", url="http://x")
        self.assertEqual(1, p.returncode)
        text = p.stdout.lower()
        # the fake host provides nvidia-smi and docker on PATH; this env hides both, and the
        # sampler path is bogus, so all three must be reported together rather than one at a time
        self.assertIn("nvidia-smi", text)
        self.assertIn("docker", text)
        self.assertIn("telemetry sampler missing", text)
        self.assertIn("blocker(s)", text)

    def test_preflight_passes_when_sources_exist(self):
        p = self.call(extra=["--preflight"])
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        self.assertIn("COMPLETE", p.stdout)


class Completeness(Harness):
    def test_complete_step_writes_completion_and_digests(self):
        p = self.call()
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        out = self.tmp / "step"
        self.assertTrue((out / "STEP_COMPLETE").is_file())
        step = json.loads((out / "step.json").read_text())
        self.assertEqual(12, step["telemetry_samples"])
        self.assertEqual([], step["collection_defects"])
        self.assertTrue(any(k.endswith("telemetry.csv") for k in step["sha256"]))
        self.assertTrue(any(k.endswith("profile_export_aiperf.json") for k in step["sha256"]))

    def test_under_collecting_client_cannot_produce_a_step(self):
        p = self.call(out_name="bad", env=self.env(skip_client=True))
        self.assertEqual(1, p.returncode)
        self.assertIn("STEP INCOMPLETE", p.stderr)
        self.assertTrue((self.tmp / "bad" / "STEP_INCOMPLETE").is_file())

    def test_dead_sampler_refuses_before_measurement(self):
        p = self.call(out_name="dead", sampler=exe(self.tmp / "dead-sampler.py", SAMPLER_DEAD))
        self.assertEqual(2, p.returncode)
        self.assertIn("telemetry sampler exited", p.stderr)

    def test_engine_not_serving_the_model_refuses(self):
        e = self.env()
        p = subprocess.run(
            [sys.executable, str(RUNNER), "--container", "eng", "--url", "http://127.0.0.1:1",
             "--model", "m", "--tokenizer", str(self.tok), "--concurrency", "32", "--reps", "3",
             "--book", str(self.corpus), "--aiperf", str(self.aiperf),
             "--proc-root", str(self.proc), "--sampler", str(self.sampler),
             "--client", str(self.client), "--out", str(self.tmp / "noengine")],
            capture_output=True, text=True, env=e, timeout=120)
        self.assertEqual(2, p.returncode)
        self.assertIn("does not serve model", p.stderr)



class CorpusMustExist(Harness):
    def test_a_corpus_path_that_is_not_a_file_is_refused(self):
        """Naming a pool is not having one: the point of the corpus is that it exists and is
        non-overlapping, so a typo must stop the step instead of falling back to a default pool."""
        p = self.call(extra=["--preflight"])
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        p = subprocess.run(
            [sys.executable, str(RUNNER), "--container", "eng", "--url", self.engine.url,
             "--model", "m", "--tokenizer", str(self.tok), "--concurrency", "32", "--reps", "3",
             "--book", str(self.tmp / "does-not-exist.txt"), "--aiperf", str(self.aiperf),
             "--proc-root", str(self.proc), "--sampler", str(self.sampler),
             "--client", str(self.client), "--out", str(self.tmp / "nocorpus"), "--preflight"],
            capture_output=True, text=True, env=self.env(), timeout=120)
        self.assertEqual(1, p.returncode)
        self.assertIn("pool source", p.stdout.lower())


if __name__ == "__main__":
    unittest.main()
