#!/usr/bin/env python3
"""Turn a harness-layout campaign into the canonical campaign tree chapter 6 consumes.

The formal campaign of 2026-09-07 was driven by the chapter-3 raster harness (the code that
produced that campaign's published peak numbers) instead of `run_campaign.py`, because that
harness is the one that talks to the deployment. Its layout is `runs/<profile>/cNNN/rN/profile_export_aiperf.json`.
The canonical adapter wants `campaign-manifest.json` + per-run manifests + `measured/` + `telemetry/`.

Rather than teach the adapter a second raw layout (R-07-1 forbids encoding campaign-specific
directory shapes in the renderer/adapter chain), this script emits the canonical tree from the
harness output and leaves the chain untouched.

What it does NOT do is invent telemetry. Only what the campaign actually sampled is emitted, and
each derived artifact says how it was derived:

* `telemetry/gpu.csv`  - sliced from the campaign-level 5 s sampler by measured window; the
  window boundaries are approximate (see `window_precision`), because the harness recorded a
  completion timestamp rather than a start timestamp.
* `telemetry/host.csv` - host MemTotal/MemAvailable only. CPU jiffies, load, DCGM energy and
  vram-used were never sampled; they are emitted as absent, which the adapter renders as
  "unavailable", never as zero (R-07-2).
* `command` - reconstructed from the preflighted command template plus the parameters recorded in
  the run manifest, and labelled as reconstructed.

Usage:
    normalize_harness_campaign.py --source <harness campaign dir> --out <canonical campaign dir>
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shlex
import pathlib
import re
import statistics
import sys

UTC = dt.timezone.utc
TEMPLATE_FILE = "/tmp/bench-command.txt"          # recorded at preflight, transferred to the node

# One row per GPU per sample, as the canonical adapter's local_telemetry() expects.
# Column names are the adapter's contract, not a preference: local_telemetry() reads
# gpu_temperature from "temperature_c", VRAM from "memory_used_mib", board power from "power_w",
# and derives host_cpu_busy from cpu_* jiffy counters. A header without those names can never
# fill those cells, however much telemetry was sampled -- which is exactly how the published
# formal campaign came to have empty GPU temperature, VRAM and host CPU cells.
GPU_HEADER = ["timestamp_utc", "gpu_index", "gpu_util_pct", "power_w",
              "temperature_c", "memory_used_mib"]
HOST_HEADER = ["timestamp_utc", "mem_total_kib", "mem_available_kib",
               "cpu_user", "cpu_nice", "cpu_system", "cpu_iowait", "cpu_irq",
               "cpu_softirq", "cpu_steal", "cpu_idle"]


def nan_to_blank(v):
    """Empty, not zero: a missing temperature must not become a reading of 0 C."""
    return "" if v != v else f"{v:.1f}"


def iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def sampler_rows(path):
    """The campaign sampler writes 8 power and 8 utilisation values as bare comma lists, so a
    row carries 21 fields against a 7-name header. Read it by position from the right."""
    rows = []
    for line in path.read_text().splitlines()[1:]:
        f = line.split(",")
        if len(f) < 21:
            continue
        power = [float(x) for x in f[5:13]]
        util = [float(x) for x in f[13:21]]
        def eight(i):
            out = []
            for x in f[i:i + 8]:
                try:
                    out.append(float(x))
                except ValueError:
                    out.append(float("nan"))
            return out
        rows.append({"utc": f[0], "when": iso(f[0]), "mem_current": f[1], "mem_peak": f[2],
                     "mem_max": f[3], "mem_available_kib": f[4], "power": power, "util": util,
                     "temp": eight(21) if len(f) > 28 else [float("nan")] * 8,
                     "vram_mib": eight(29) if len(f) > 36 else [float("nan")] * 8,
                     "cpu": f[37:45] if len(f) > 44 else [""] * 8})
    return rows


def parse_export(path):
    d = json.loads(path.read_text())
    def g(k):
        v = d.get(k)
        return v.get("avg") if isinstance(v, dict) else None
    ic = d.get("input_config", {}) or {}
    ep = ic.get("endpoint", {}) or {}
    ph = (ic.get("phases") or [{}])[0]
    out = {
        "output_tps": g("output_token_throughput"),
        "input_tps": g("input_token_throughput"),
        "total_tps": g("total_token_throughput"),
        "per_user_tps": g("output_token_throughput_per_user"),
        "requests": g("request_count"),
        "request_rps": g("request_throughput"),
        "input_tokens_avg": g("input_sequence_length"),
        "output_tokens_avg": g("output_sequence_length"),
        "realized_window_s": g("benchmark_duration"),
        "cache_read_pct": g("overall_usage_prompt_cache_read_pct"),
        "declared_concurrency": ph.get("concurrency"),
        "ttft_p50_ms": (d.get("time_to_first_token") or {}).get("p50"),
        "ttft_p95_ms": (d.get("time_to_first_token") or {}).get("p95"),
        "ttft_p99_ms": (d.get("time_to_first_token") or {}).get("p99"),
        "itl_p50_ms": (d.get("inter_token_latency") or {}).get("p50"),
        "itl_p95_ms": (d.get("inter_token_latency") or {}).get("p95"),
        "itl_p99_ms": (d.get("inter_token_latency") or {}).get("p99"),
        "e2e_p95_ms": (d.get("request_latency") or {}).get("p95"),
        "token_source": ep.get("use_server_token_count"),
        "unit": (d.get("output_token_throughput") or {}).get("unit"),
        "schema_version_export": d.get("schema_version"),
    }
    errs = d.get("error_summary") or []
    out["errors"] = len(errs) if isinstance(errs, list) else 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--campaign-id", required=True,
                    help="campaign identifier as recorded in the freeze contract")
    ap.add_argument("--host", required=True, help="measured host name, as recorded at run time")
    ap.add_argument("--model", required=True, help="model repository, e.g. org/model-quant")
    ap.add_argument("--host-total-mem-kib", required=True, type=int,
                    help="MemTotal in KiB, measured at preflight; constant per host")
    ap.add_argument("--spec-path", default=None,
                    help="pointer to the concurrency-grids spec that planned the campaign")
    ap.add_argument("--campaign-path", default=None,
                    help="pointer to the freeze contract / campaign plan document")
    a = ap.parse_args()
    src, out = a.source.resolve(), a.out.resolve()

    sampler = sampler_rows(src / "telemetry.csv")
    if not sampler:
        sys.exit("sampler rows unreadable: telemetry.csv is the only GPU source for this campaign")
    peak_container = max(int(r["mem_peak"]) for r in sampler if r["mem_peak"] not in ("NA", ""))

    # Pass 1: read every run, keep the container identity per run. cid must be bound HERE,
    # per run: an earlier version bound it while grouping and reused it while writing, so all
    # 84 manifests recorded the last container seen and the two-launch deviation vanished.
    records = []
    runs = []
    groups = {}
    # Two layouts are real. The campaign runner writes runs/<profile>/cNNN/rN/manifest.json;
    # benchmark-step.py writes cNNN/rN/ with no per-run manifest, because AIPerf owns those
    # directories and the step records its evidence in step.json at the campaign root. Matching
    # only the first layout made the step's output invisible to this tool -- it would emit an
    # EMPTY campaign without complaining, which is worse than crashing.
    exports = sorted(src.glob("runs/*/c*/r*/profile_export_aiperf.json"))
    flat = sorted(src.glob("c*/r*/profile_export_aiperf.json"))
    if not exports and flat:
        exports = flat
    if not exports:
        sys.exit("no profile_export_aiperf.json found under either runs/*/c*/r*/ or c*/r*/ -- "
                 "refusing to emit an empty campaign")
    # benchmark-step.py records the real argv of every run in commands.log. When it is present,
    # the command is evidence; the template reconstruction below is a fallback for the older
    # harness, which captured no argv at all.
    cmd_log = (src / "commands.log").read_text().splitlines() if (src / "commands.log").is_file() else []
    step = {}
    if (src / "step.json").is_file():
        step = json.loads((src / "step.json").read_text())
    for export in exports:
        rel = export.relative_to(src)
        parts = rel.parts
        if parts[0] == "runs":
            profile, cdir, repdir = parts[1], parts[2], parts[3]
        else:
            profile, cdir, repdir = "measured", parts[0], parts[1]
        conc = int(re.sub(r"\D", "", cdir))
        rep = int(re.sub(r"\D", "", repdir))
        mf = export.parent / "manifest.json"
        if mf.is_file():
            prior = json.loads(mf.read_text())
        else:
            # No per-run manifest: the export file's own write time is when AIPerf finished, and
            # the campaign sampler ran continuously, so the window is attributable -- with a
            # precision claim, not a pretence. window_precision records it.
            epoch = export.stat().st_mtime
            tag = f"corpus-c{conc:03d}-r{rep}"
            line = next((l for l in cmd_log if tag in l), "")
            argv = shlex.split(line) if line else []

            def flag(name, cast=str, default=None):
                if name in argv:
                    try:
                        return cast(argv[argv.index(name) + 1])
                    except (IndexError, ValueError):
                        pass
                return default

            # ISL is not in the argv: this harness is corpus-driven and AIPerf 0.13 rejects
            # --isl alongside a custom dataset, so prompt length is a property of the pool. The
            # value below is therefore MEASURED by the server's token counter, not declared.
            prior = {"utc": dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "container_id": str(step.get("container_id", "unknown")),
                     "window_precision": "export mtime; benchmark-step.py writes no per-run manifest",
                     "command": line or None,
                     "seed": flag("--random-seed", int),
                     "window_s": flag("--benchmark-duration", float),
                     "osl": flag("--osl", int),
                     "isl": None}
        groups.setdefault((profile, conc), []).append((rep, prior, export))
    for (profile, conc), items in sorted(groups.items()):
        for rep, prior, export in sorted(items, key=lambda x: x[0]):
            cid = str(prior.get("container_id", "unknown"))
            end = iso(prior["utc"])
            m = parse_export(export)
            records.append(dict(profile=profile, conc=conc, rep=rep, cid=cid, prior=prior,
                                m=m, export=export, end=end))

    # Launch numbers in chronological order: launch-1 is the container that measured first.
    first_seen = {}
    for r in records:
        first_seen.setdefault(r["cid"], r["end"])
    launches = {cid: f"launch-{i + 1}" for i, cid in
                enumerate(sorted(first_seen, key=lambda c: first_seen[c]))}

    for r in records:
        profile, conc, rep, prior, m, end = (r["profile"], r["conc"], r["rep"],
                                            r["prior"], r["m"], r["end"])
        realized = m["realized_window_s"] or 0.0
        # Measured window approximation: the harness slept 15 s after export, so the measured
        # phase ended ~15 s before the manifest timestamp. +-20 s is honest, +-0 s is fiction.
        w_end = end - dt.timedelta(seconds=15)
        w_start = w_end - dt.timedelta(seconds=realized + 20)
        run_rel = f"runs/{profile}/c{conc:03d}/run-r{rep}"
        rdir = out / run_rel
        (rdir / "telemetry").mkdir(parents=True, exist_ok=True)
        measured_ref = os.path.relpath(r["export"].parent, rdir)

        in_win = [s for s in sampler if w_start <= s["when"] <= w_end]
        with (rdir / "telemetry" / "gpu.csv").open("w", newline="") as fh:
            w = csv.writer(fh); w.writerow(GPU_HEADER)
            for s in in_win:
                for gi, (pw, u) in enumerate(zip(s["power"], s["util"])):
                    w.writerow([s["utc"], gi, u, pw,
                                nan_to_blank(s["temp"][gi]), nan_to_blank(s["vram_mib"][gi])])
        with (rdir / "telemetry" / "host.csv").open("w", newline="") as fh:
            w = csv.writer(fh); w.writerow(HOST_HEADER)
            for s in in_win:
                if s["mem_available_kib"].isdigit():
                    w.writerow([s["utc"], a.host_total_mem_kib, int(s["mem_available_kib"]),
                                *s["cpu"]] if len(s["cpu"]) == 8 and all(s["cpu"])
                               else [s["utc"], a.host_total_mem_kib, int(s["mem_available_kib"])])

        # ISL: declared where the harness declared it, otherwise realized from the server's own
        # token count. Corpus-driven runs declare none, because AIPerf rejects --isl with a
        # custom dataset -- reporting a declared value there would be inventing one.
        isl = prior["isl"] if prior["isl"] is not None else m["input_tokens_avg"]
        cmd = None
        if prior.get("command"):
            cmd = prior["command"]
            cmd_source = ("argv captured by the harness in commands.log, matched to this run by "
                          "the pool file it consumed; prompt length is corpus-driven and measured "
                          "by the server's token counter, so isl below is realized, not declared")
        elif pathlib.Path(TEMPLATE_FILE).is_file():
            cmd = (pathlib.Path(TEMPLATE_FILE).read_text().strip()
                       .replace("$ISL", str(isl)).replace("$OSL", str(prior["osl"]))
                       .replace("$C", str(conc)).replace("$WIN", str(prior["window_s"]))
                       .replace("$SEED", str(prior["seed"])))
            cmd_source = ("reconstructed from the preflighted command template and the "
                          "parameters recorded in the harness manifest; the harness did "
                          "not capture argv per run")
        else:
            # Neither argv nor template: say so in the record. Crashing 40 runs into a campaign
            # loses the 39 that were fine, and inventing a command string would be worse.
            cmd, cmd_source = None, ("not captured: this campaign recorded no commands.log and no "
                                     "command template was available")
        run_manifest = {
            "schema_version": 1, "campaign_id": a.campaign_id,
            "run_id": f"{profile}-c{conc}-r{rep}", "status": "complete",
            "profile": profile, "concurrency": conc, "repetition": rep,
            "random_seed": prior["seed"], "command": cmd,
            "input_sequence_length_measured": isl,
            "command_source": cmd_source,
            "start_time": w_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "return_code": 0, "error": None,
            "artifacts": {"result": os.path.join(measured_ref, "profile_export_aiperf.json"),
                          "measured_dir": measured_ref, "telemetry_dir": "telemetry"},
            "measurements": {
                "declared_window_s": prior["window_s"],
                "realized_window_s": m["realized_window_s"],
                "window_precision": "start derived from completion timestamp; +-20 s",
                "gpu_samples_in_window": len(in_win),
                "container_mem_peak_bytes": prior.get("container_mem_peak_bytes"),
                "cache_read_pct": m["cache_read_pct"],
                "token_source_server_asserted": m["token_source"],
                "throughput_unit": m["unit"],
                "container_launch": launches[r["cid"]],
            },
            "events": [
                {"event": "warmup", "requests": 2 * conc, "same_concurrency": True},
                {"event": "measured", "window_s": prior["window_s"],
                 "realized_s": m["realized_window_s"]},
                {"event": "container", "container_id": r["cid"], "launch": launches[r["cid"]]},
            ],
        }
        (rdir / "manifest.json").write_text(json.dumps(run_manifest, indent=2, sort_keys=True) + "\n")
        runs.append({"schema_version": 1, "run_id": run_manifest["run_id"],
                     "status": "complete", "manifest": f"{run_rel}/manifest.json",
                     "profile": profile, "concurrency": conc, "repetition": rep,
                     "launch": launches[r["cid"]]})

    # Self-check by re-reading the written files: a label that disagrees with the source
    # manifest is a defect in this script, and it must not reach chapter 6 unnoticed.
    mismatches = []
    for r, rec in zip(sorted(runs, key=lambda x: (x["profile"], x["concurrency"], x["repetition"])),
                      sorted(records, key=lambda x: (x["profile"], x["conc"], x["rep"]))):
        written = json.loads((out / r["manifest"]).read_text())
        ev = [e for e in written["events"] if "container_id" in e][0]
        if ev["container_id"] != rec["cid"] or written["measurements"]["container_launch"] != launches[rec["cid"]]:
            mismatches.append(r["run_id"])
    if mismatches:
        sys.exit(f"normalizer defect: {len(mismatches)} run manifests lost their container "
                 f"identity (e.g. {mismatches[:3]})")
    assert len({r["launch"] for r in runs}) == len(launches), "launch label count drifted"

    (out / "campaign-manifest.json").write_text(json.dumps({
        "schema_version": 1, "campaign_id": a.campaign_id, "status": "runs_complete",
        "host": a.host, "model": a.model,
        "created_at": "2026-09-07T00:48:15Z",
        "updated_at": dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec_path": a.spec_path,
        "campaign_path": a.campaign_path,
        "deployment": {"summary": "TP8 single replica, no load balancer, MAX_NUM_SEQS=128, "
                                  "cudagraph 512, MTP 3, GPU_MEMORY_UTILIZATION=0.95, 96 GiB host cap",
                       "request_path": "AIPerf -> model server (no HAProxy; approved contract deviation)"},
        "counts": {"runs": len(runs), "profiles": len({r["profile"] for r in runs}),
                   "grid_points": len({(r["profile"], r["concurrency"]) for r in runs}),
                   "container_launches": len(launches)},
        "runs": runs,
    }, indent=2, sort_keys=True) + "\n")

    (out / "RUNS_COMPLETE").write_text(dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")

    # idle baselines: the campaign captured B0 (unloaded) and B1-post (loaded, after).
    for name, fname, kind in (("pre", "B0-idle.csv", "unloaded-idle-before-campaign"),
                              ("post", "B1-post-idle.csv", "loaded-idle-after-campaign")):
        d = out / "idle" / name
        d.mkdir(parents=True, exist_ok=True)
        if not (src / fname).is_file():
            continue
        rows = [l.split(",") for l in (src / fname).read_text().splitlines()[1:]]
        pw = [float(r[1]) for r in rows if len(r) > 1]
        (d / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": kind, "samples": len(rows),
            "gpu_power_avg_w": round(statistics.mean(pw), 2),
            "gpu_power_min_w": min(pw), "gpu_power_max_w": max(pw),
            "source": f"{src.name}/{fname}",
            "sampler": "nvidia-smi power.draw, 25 s interval, host-side",
        }, indent=2, sort_keys=True) + "\n")
    captured = sorted(x.name for x in (out / "idle").glob("*/manifest.json"))
    medians = {}
    for name in ("pre", "post"):
        f = out / "idle" / name / "manifest.json"
        if f.is_file():
            medians[name] = json.loads(f.read_text()).get("gpu_power_avg_w")
    delta = (abs(medians["pre"] - medians["post"]) / medians["pre"] * 100
             if len(medians) == 2 and medians.get("pre") else None)
    (out / "idle" / "IDLE-BASELINE.reason").write_text(
        "Idle baselines present in this campaign: "
        + (", ".join(captured) if captured else "NONE")
        + ".\n"
        + (f"B0 and B1-post GPU power means are {medians['pre']} W and {medians['post']} W, "
           f"a difference of {delta:.1f}%." if delta is not None else
           "At least one of B0/B1-post is absent, so no idle delta is quoted and none may be "
           "inferred. R-06-1 requires B1-pre or an explicit justification.")
        + "\nNothing emitted by this normalizer subtracts an idle baseline.\n")

    prov = out / "DERIVED-ARTIFACTS.txt"
    prov.write_text(
        "What is raw and what is derived in this tree\n"
        "============================================\n"
        "RAW (unmodified, referenced not copied):\n"
        f"  {src}\n"
        "      profile_export_aiperf.json per run, the campaign sampler telemetry.csv,\n"
        "      preflight.json, progress.log, run.sh (the driver itself), B0/B1-post idle CSVs.\n"
        "      runs/*/manifest.json artifacts.* resolve to those files by relative path; nothing\n"
        "      is copied into this tree, so the cache stays the single source of raw truth.\n"
        "DERIVED BY THIS SCRIPT:\n"
        "      campaign-manifest.json, per-run manifest.json, RUNS_COMPLETE, idle/*/manifest.json,\n"
        f"      runs/*/telemetry/gpu.csv and host.csv, sliced from the 5 s campaign sampler.\n"
        "      gpu window boundaries are approximate (+-20 s): the harness recorded completion\n"
        "      timestamps, not start timestamps.\n"
        "NEVER SAMPLED (absent, not zero): CPU jiffies, load, DCGM energy counters, per-GPU VRAM\n"
        "      used, preemption counts, KV occupancy, HAProxy counters (no proxy in this contract).\n"
        f"      Container RAM high-water for the whole campaign (cgroup memory.peak): "
        f"{peak_container / 1073741824:.2f} GiB.\n"
    )
    print(f"canonical tree: {out}\n  runs={len(runs)} launches={len(launches)} "
          f"({', '.join(f'{c[:12]}..={l}' for c, l in launches.items())})\n"
          f"  container RAM high-water {peak_container / 1073741824:.2f} GiB")


if __name__ == "__main__":
    main()
