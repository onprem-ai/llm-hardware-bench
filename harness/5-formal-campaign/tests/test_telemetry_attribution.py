"""Per-run telemetry attribution for a benchmark-step campaign.

The cold campaign that got hollow panels was not missing data, it was missing ATTRIBUTION: the
normalizer wrote columns the adapter never reads, so GPU temperature and host CPU could not be
filled however much was sampled. These tests pin the two things that make a panel real:

  * a run's telemetry/gpu.csv contains samples drawn DURING that run's window, and the
    temperature / VRAM cells carry values;
  * a campaign whose runs this tool cannot see is REFUSED, not normalised into an empty
    directory that looks like a finished campaign.
"""
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1] / "code" / "normalize_harness_campaign.py"

FIELDS = (["utc", "mem_current", "mem_peak", "mem_max", "mem_available_kib"]
          + [f"power_{i}" for i in range(8)] + [f"util_{i}" for i in range(8)]
          + [f"temperature_c_{i}" for i in range(8)] + [f"memory_used_mib_{i}" for i in range(8)]
          + ["cpu_user", "cpu_nice", "cpu_system", "cpu_iowait", "cpu_irq", "cpu_softirq",
             "cpu_steal", "cpu_idle"])


def sampler_line(when):
    """One 45-field row in the sampler's wire order."""
    return ",".join([when.strftime("%Y-%m-%dT%H:%M:%SZ"), "9000000", "9500000", "max", "528000000"]
                    + ["340.5"] * 8 + ["100"] * 8 + ["52.0"] * 8 + ["94074"] * 8
                    + ["2884130213", "0", "120000000", "300000", "10", "900000", "0",
                       "56256642674"])


def export(window_s=60.0):
    return {"schema_version": "1.0", "aiperf_version": "0.13",
            "benchmark_duration": {"unit": "sec", "avg": window_s},
            "input_token_throughput": {"unit": "tokens/sec", "avg": 6271.4},
            "output_token_throughput": {"unit": "tokens/sec", "avg": 1233.88},
            "total_token_throughput": {"unit": "tokens/sec", "avg": 7505.3},
            "output_token_throughput_per_user": {"unit": "tokens/sec", "avg": 38.5},
            "request_count": {"unit": "requests", "avg": 224},
            "input_sequence_length": {"unit": "tokens", "avg": 2048},
            "output_sequence_length": {"unit": "tokens", "avg": 1},
            "time_to_first_token": {"p50": 12.0, "p95": 20.0, "p99": 25.0},
            "inter_token_latency": {"p50": 1.0, "p95": 2.0, "p99": 3.0},
            "request_latency": {"p95": 30.0},
            "overall_usage_prompt_cache_read_pct": {"unit": "percent", "avg": 0.0},
            "input_config": {"endpoint": {"use_server_token_count": True},
                             "phases": [{"concurrency": 32}]}}


def campaign(root: Path, *, with_exports=True, with_telemetry=True):
    root.mkdir(parents=True, exist_ok=True)
    end = dt.datetime(2026, 9, 11, 15, 0, 0, tzinfo=dt.timezone.utc)
    if with_telemetry:
        lines = [",".join(FIELDS)]
        for sec in range(0, 400):           # 400 s of samples covering both runs
            lines.append(sampler_line(end - dt.timedelta(seconds=400 - sec)))
        (root / "telemetry.csv").write_text("\n".join(lines) + "\n")
    if with_exports:
        # Sampler covers [end-400s, end]. Place both measured windows inside it and apart:
        # r1 finishing at end-300s (window end end-315s, start end-395s) and r2 at end-100s.
        for conc, rep, finish in ((32, 1, 300), (32, 2, 100)):
            rdir = root / f"c{conc:03d}" / f"r{rep}"
            rdir.mkdir(parents=True, exist_ok=True)
            f = rdir / "profile_export_aiperf.json"
            f.write_text(json.dumps(export()))
            when = end - dt.timedelta(seconds=finish)
            os.utime(f, (when.timestamp(), when.timestamp()))
    (root / "step.json").write_text(json.dumps({"container_id": "abc123",
                                                "concurrency_points": [32], "repetitions": 2}))
    if with_exports:
        # The harness records real argv per run; the normalizer must use it, not reconstruct.
        (root / "commands.log").write_text("\n".join(
            f"/opt/aiperf/.venv/bin/aiperf profile --model m --url http://127.0.0.1:8080 "
            f"--concurrency {c} --benchmark-duration 60 --osl 8 --random-seed {600000 + c} "
            f"--input-file {root}/corpus-c{c:03d}-r{r}.jsonl"
            for c, r in ((32, 1), (32, 2))) + "\n")


class TestTelemetryAttribution(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())

    def run_normalizer(self, src, out):
        # The normalizer carries no host defaults: every campaign-specific value
        # is an explicit argument (instrument code, host-free by construction).
        return subprocess.run([sys.executable, str(CODE), "--source", str(src), "--out", str(out),
                               "--campaign-id", "20260907-toy-formal",
                               "--host", "toyhost-1x-gpu9000",
                               "--model", "toyorg/toy-model-fp8",
                               "--host-total-mem-kib", "1000000"],
                              capture_output=True, text=True)

    def test_step_layout_runs_receive_samples_from_their_own_window(self):
        src, out = self.tmp / "camp", self.tmp / "norm"
        campaign(src)
        r = self.run_normalizer(src, out)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        gpu = out / "runs/measured/c032/run-r1/telemetry/gpu.csv"
        self.assertTrue(gpu.is_file(), f"no per-run gpu.csv written; tree: {sorted(p.name for p in (out / 'runs/measured/c032/run-r1').iterdir()) if (out / 'runs/measured/c032/run-r1').is_dir() else 'run dir absent'}")
        rows = list(csv.DictReader(gpu.read_text().splitlines()))
        self.assertGreaterEqual(len(rows), 10, "run window too thin to render a panel")
        # r1 measured ~60 minutes before the sampler's last sample; r2 ~200. Rows must not
        # bleed between them, or the two repetitions share one curve.
        stamps = sorted({dt.datetime.strptime(r["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ")
                         for r in rows})
        # The campaign sampler ran 400 s. r1 measured ~60 min into it; if slicing leaked the whole
        # campaign into one run, the two repetitions would share a curve and the panel would lie.
        self.assertLess((stamps[-1] - stamps[0]).total_seconds(), 120.0,
                        f"run window spans {(stamps[-1]-stamps[0]).total_seconds():.0f}s of a "
                        f"400s campaign: samples are bleeding between runs")
        other = list((self.tmp / "norm/runs").glob("*/c032/run-r2/telemetry/gpu.csv"))
        self.assertTrue(other, "r2 telemetry missing")
        o_stamps = [dt.datetime.strptime(r["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ")
                    for r in csv.DictReader(other[0].read_text().splitlines())]
        self.assertFalse(set(stamps) & set(o_stamps),
                         "r1 and r2 share telemetry samples: they would render one curve")
        for row in rows:
            self.assertNotEqual(row["gpu_index"], "")
            self.assertNotEqual(row["temperature_c"], "",
                                "empty temperature: the panel the reader draws would be hollow")
            self.assertNotEqual(row["memory_used_mib"], "")
            self.assertGreater(float(row["temperature_c"]), 0.0)

    def test_host_cpu_jiffies_are_carried_not_dropped(self):
        src, out = self.tmp / "camp", self.tmp / "norm"
        campaign(src)
        self.assertEqual(self.run_normalizer(src, out).returncode, 0)
        host = next((out / "runs").glob("*/c032/run-r1/telemetry/host.csv"))
        header = host.read_text().splitlines()[0].split(",")
        for name in ("cpu_user", "cpu_idle", "cpu_steal"):
            self.assertIn(name, header,
                          f"{name} absent: local_telemetry() differences these to fill the panel")

    def test_invisible_runs_are_refused_not_normalised_to_empty(self):
        src, out = self.tmp / "camp", self.tmp / "norm"
        campaign(src, with_exports=False)
        r = self.run_normalizer(src, out)
        self.assertNotEqual(r.returncode, 0, "an empty campaign must not be emitted silently")
        self.assertIn("profile_export_aiperf.json", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
