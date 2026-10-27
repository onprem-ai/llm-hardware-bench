#!/usr/bin/env python3
"""One benchmark step, mechanically complete.

    benchmark-step.py --container NAME --url http://127.0.0.1:8080 --model M \
                      --tokenizer DIR --concurrency 32 --reps 3 --book BOOK --out DIR

The point of this file is that an operator -- human or AI -- cannot forget a measurement.
Every metric the report renders is collected by this process, or the step refuses to run:

* GPU power, utilisation, temperature, per-device VRAM and host CPU jiffies come from
  telemetry-sampler.py, which this runner starts before the first request and stops after the
  last, with --container bound so the inference container's cgroup memory is sampled too.
* Throughput and latency come from the benchmark client; prefix-cache counters come from the
  same export and are checked by chapter 3's cold gate.
* Completeness is checked by chapter 3's collection contract, and a step that under-collected
  writes STEP_INCOMPLETE and exits non-zero. There is no flag to skip any of this.

`--preflight` performs every check and starts nothing, so an operator can ask "can this host
produce a complete measurement?" before committing GPU time.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collection_contract as contract  # noqa: E402

CLIENT = HERE / "cold-prefill-client.py"
SAMPLER = HERE / "telemetry-sampler.py"
GATE = HERE / "cold_gate.py"


def sh(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def idle_baseline(out: pathlib.Path, name: str, seconds: int) -> int:
    """Sample idle GPU power into a CSV.

    R-06-1 wants an idle reference so a report can tell its own drift from the machine's. The
    normalizer used to PRINT a claim about B0 and B1-post differing by 1.4% whether or not either
    had been captured; the fix is to capture them here, and to let the normalizer state only what
    it can see. Returns the number of samples written (0 is honest, a fabricated row is not).
    """
    (out / name).write_text("timestamp,power_w\n")
    try:
        r = sh(["timeout", str(seconds), "nvidia-smi", "--query-gpu=timestamp,power.draw",
                "--format=csv,noheader,nounits", "-lms", "500"], timeout=seconds + 20)
    except (OSError, subprocess.SubprocessError) as exc:
        # An empty file plus a reason beats a crash: the campaign's failure to get a baseline is
        # evidence, and it is the reader's right to see it rather than to get a partial run.
        (out / f"{name}.reason").write_text(f"{name} not captured: {type(exc).__name__}: {exc}\n")
        return 0
    lines = [l for l in (r.stdout or "").strip().splitlines() if "," in l]
    if not lines:
        (out / f"{name}.reason").write_text(
            f"{name} not captured: nvidia-smi produced no samples "
            f"(exit {r.returncode}); stderr: {(r.stderr or '').strip()[:200]}\n")
    (out / name).write_text("timestamp,power_w\n" + "\n".join(lines) + "\n")
    return len(lines)


def preflight(a) -> list[str]:
    proc = pathlib.Path(a.proc_root)
    """Every capability the collection contract depends on. Returns reasons to refuse."""
    bad: list[str] = []
    if shutil.which("nvidia-smi") is None:
        bad.append("nvidia-smi absent: GPU power, utilisation, temperature and VRAM are unobtainable")
    elif not sh(["nvidia-smi", "--query-gpu=power.draw,utilization.gpu,temperature.gpu,"
                          "memory.used", "--format=csv,noheader,nounits"]).stdout.strip():
        bad.append("nvidia-smi returned no device rows")
    for path, what in ((proc / "meminfo", "host RAM (MemAvailable)"),
                       (proc / "stat", "host CPU jiffies")):
        if not path.is_file():
            bad.append(f"{path} unreadable: {what} is unobtainable")
    for script, what in ((pathlib.Path(a.client), "benchmark client"),
                         (pathlib.Path(a.sampler), "telemetry sampler"),
                         (GATE, "cold cache gate")):
        if not script.is_file():
            bad.append(f"{what} missing: {script}")
    if shutil.which(a.aiperf) is None and not pathlib.Path(a.aiperf).is_file():
        bad.append(f"benchmark binary not runnable: {a.aiperf}")
    if not shutil.which("docker"):
        bad.append("docker absent: container cgroup memory is unobtainable")
    elif sh(["docker", "inspect", "--format", "{{.Id}}", a.container]).stdout.strip() == "":
        bad.append(f"container not found: {a.container}")
    if not pathlib.Path(a.tokenizer).is_dir():
        bad.append(f"tokenizer directory absent: {a.tokenizer} (token counts would be unfounded)")
    if not pathlib.Path(a.book).is_file() or not pathlib.Path(a.book).stat().st_size:
        bad.append(f"pool source not readable or empty: {a.book} -- without a real text pool the "
                   f"benchmark tool falls back to its default 100-prompt set, recycles prompts "
                   f"across the window and measures the prefix cache instead of the engine")
    return bad


def endpoint_ready(url: str, model: str) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"{url.rstrip('/')}/v1/models", timeout=15) as r:
            return model in r.read().decode()
    except Exception:
        return False


def digest_tree(root: pathlib.Path) -> dict[str, str]:
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--concurrency", type=int)
    ap.add_argument("--grid", default="",
                    help="one concurrency (32) or a grid (8,32,128); a grid runs in one\n                    process so prompt slices stay monotonic across all points")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--input-tokens", type=int, default=2048)
    ap.add_argument("--output-tokens", type=int, default=8)
    ap.add_argument("--metric", choices=("input", "output"), default="input")
    ap.add_argument("--window-s", type=int, default=60)
    ap.add_argument("--dataset-entries", type=int, default=4000)
    ap.add_argument("--max-served-pct", type=float, default=2.0)
    ap.add_argument("--book", required=True,
                    help="text the prompt pool is cut from; one non-overlapping passage per prompt")
    ap.add_argument("--aiperf", default="aiperf")
    ap.add_argument("--token-env", default="APIKEY")
    ap.add_argument("--allow-anonymous", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--proc-root", default="/proc",
                    help="where /proc-equivalent files live (test seam; checks still run)")
    ap.add_argument("--client", default=str(CLIENT))
    ap.add_argument("--sampler", default=str(SAMPLER))
    ap.add_argument("--idle-seconds", type=int, default=12,
                    help="idle reference sampled before the first request and after the last")
    ap.add_argument("--preflight", action="store_true")
    a = ap.parse_args(argv)

    if not a.grid and not a.concurrency:
        print("  REFUSE  pass --concurrency N or --grid 8,32,128", file=sys.stderr)
        return 2
    points = [int(x) for x in (a.grid or str(a.concurrency)).split(",") if x.strip()]
    out = pathlib.Path(a.out)
    reasons = preflight(a)
    if a.preflight:
        for r in reasons:
            print(f"  REFUSE  {r}")
        print(f"  preflight: {'COMPLETE -- a full measurement is possible' if not reasons else str(len(reasons)) + ' blocker(s)'}")
        return 1 if reasons else 0
    if reasons:
        for r in reasons:
            print(f"  REFUSE  {r}", file=sys.stderr)
        return 2
    if not endpoint_ready(a.url, a.model):
        print(f"  REFUSE  engine at {a.url} does not serve model {a.model}; measuring now would "
              f"produce failures reported as throughput", file=sys.stderr)
        return 2

    out.mkdir(parents=True, exist_ok=True)
    telemetry = out / "telemetry.csv"
    env = dict(**__import__("os").environ, PROC_ROOT=a.proc_root)
    # B0: idle reference BEFORE any request touches the engine, taken after the sampler starts so
    # one interval covers both.
    b0 = idle_baseline(out, "B0-idle.csv", a.idle_seconds)
    sampler = subprocess.Popen([sys.executable, str(a.sampler), "--out", str(telemetry),
                               "--container", a.container, "--interval", "1"], env=env)
    time.sleep(6)
    if sampler.poll() is not None:
        print("  REFUSE  telemetry sampler exited before the first sample; collection contract "
              "cannot be met", file=sys.stderr)
        return 2
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        cmd = [sys.executable, str(a.client), "--url", a.url, "--model", a.model,
               "--tokenizer", a.tokenizer, "--aiperf", a.aiperf,
               "--grid", a.grid or str(a.concurrency), "--reps", str(a.reps),
               "--input-tokens", str(a.input_tokens), "--output-tokens", str(a.output_tokens),
               "--metric", a.metric, "--window-s", str(a.window_s),
               "--num-dataset-entries", str(a.dataset_entries),
               "--prompts-needed", str(a.dataset_entries),
               "--warmup-prompts", str(max(200, a.dataset_entries // 2)),
               "--max-served-pct", str(a.max_served_pct), "--out", str(out)]
        if a.book:
            cmd += ["--book", a.book]
        if a.allow_anonymous:
            cmd += ["--allow-anonymous"]
        else:
            cmd += ["--token-env", a.token_env]
        plan = sh(cmd + ["--plan"], timeout=300)
        if plan.returncode != 0:
            (out / "STEP_INCOMPLETE").write_text(
                "the benchmark client rejected these arguments; nothing was measured\n" + plan.stderr)
            print("  REFUSE  benchmark client rejected the measurement arguments:\n"
                  + plan.stderr.strip()[:600], file=sys.stderr)
            return 2
        run = sh(cmd, timeout=86400)
        sys.stdout.write(run.stdout)
        sys.stderr.write(run.stderr)
        client_rc = run.returncode
    finally:
        # B1-post: idle reference after the load, so ambient drift during the campaign is
        # distinguishable from anything the measurements claim.
        b1 = idle_baseline(out, "B1-post-idle.csv", a.idle_seconds)
        sampler.terminate()
        sampler.wait(timeout=30)

    defects = contract.validate_campaign(out)
    sample_rows = len([l for l in telemetry.read_text(errors='replace').splitlines()[1:]
                       if l.strip()]) if telemetry.is_file() else 0
    steps = {"schema_version": 1, "started_utc": started,
             "finished_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "concurrency_points": points, "repetitions": a.reps, "client_exit": client_rc,
             "idle_reference_samples": {"B0": b0, "B1_post": b1},
             "telemetry_samples": sample_rows, "collection_defects": defects,
             "sha256": digest_tree(out)}
    (out / "step.json").write_text(json.dumps(steps, indent=2) + "\n")
    if defects or client_rc != 0:
        (out / "STEP_INCOMPLETE").write_text(
            f"client_exit={client_rc} defects={len(defects)}\n"
            + "".join(f"- {d}\n" for d in defects))
        print(f"  STEP INCOMPLETE: {len(defects)} collection defect(s), client exit {client_rc}",
              file=sys.stderr)
        return 1
    (out / "STEP_COMPLETE").write_text("collection contract satisfied\n")
    print(f"  STEP COMPLETE: {len(points)} points x{a.reps} reps, {sample_rows} telemetry samples, "
          f"contract satisfied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
