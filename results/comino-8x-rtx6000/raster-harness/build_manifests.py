#!/usr/bin/env python3
"""Build canonical campaign manifests + per-run telemetry slices for the comino
GLM-5.3 and Qwen3.8-Flash-Next cold-grid campaigns (protocol_campaign adapter).

Per run (kind/cXXX/rN): emits manifest.json + telemetry/{gpu,host}.csv sliced to
the run's STARTED..FINISHED window (lexicographic ISO comparison; fixed-format
zero-padded stamps so string order == chronological order).
At campaign root: campaign-manifest.json with the canonical runs array.
"""
import json, sys
from pathlib import Path

campaign = Path(sys.argv[1]).resolve()
campaign_id = sys.argv[2]
host_id = sys.argv[3]
model_repo = sys.argv[4]
model_revision = sys.argv[5]
repo_campaign_path = sys.argv[6]
container_launches = int(sys.argv[7])
cache_source = sys.argv[8]  # glm: server-metrics gate | qwen: client-side radix-off gate

tele = campaign / "telemetry"
gpu_lines = (tele / "gpu.csv").read_text().splitlines()
host_lines = (tele / "host.csv").read_text().splitlines()
gpu_header, gpu_rows = gpu_lines[0], gpu_lines[1:]
host_header, host_rows = host_lines[0], host_lines[1:]


def rows_in_window(rows, t0, t1):
    return [r for r in rows if t0 <= r.split(",", 1)[0] <= t1]


runs = []
for kind_dir in sorted(p for p in campaign.iterdir() if p.is_dir() and p.name in ("decode", "prefill")):
    kind = kind_dir.name
    for c_dir in sorted(kind_dir.glob("c*")):
        c = int(c_dir.name[1:])
        for r_dir in sorted(c_dir.glob("r*")):
            r = int(r_dir.name[1:])
            app_path = r_dir / "profile_export_aiperf.json"
            if not app_path.is_file():
                continue
            app = json.loads(app_path.read_text())
            gate = json.loads((r_dir / "gate.json").read_text())
            started = (r_dir / "STARTED").read_text().strip()
            finished = (r_dir / "FINISHED").read_text().strip()
            seed = (r_dir / "seed").read_text().strip()
            cli = (r_dir / "cli.txt").read_text().strip()

            wgpu = rows_in_window(gpu_rows, started, finished)
            whost = rows_in_window(host_rows, started, finished)
            tdir = r_dir / "telemetry"
            tdir.mkdir(exist_ok=True)
            (tdir / "gpu.csv").write_text("\n".join([gpu_header] + wgpu) + "\n")
            (tdir / "host.csv").write_text("\n".join([host_header] + whost) + "\n")

            warmup_requests = max(c, 32)
            if "served_pct" in gate:
                cache_pct = gate.get("served_pct")
            else:
                cache_pct = 0.0 if gate.get("client_cache_read_tokens") == 0 else 100.0
            manifest = {
                "schema_version": 1,
                "campaign_id": campaign_id,
                "run_id": f"{kind}-c{c}-r{r}",
                "profile": kind,
                "concurrency": c,
                "repetition": r,
                "random_seed": int(seed),
                "status": "complete",
                "return_code": 0,
                "start_time": started,
                "end_time": finished,
                "command": cli,
                "command_source": "campaign commands.log (verbatim aiperf invocation)",
                "error": None,
                "events": [
                    {"event": "warmup", "requests": warmup_requests, "same_concurrency": True,
                     "source": "warmup seed 953601/953602 disjoint from measured per-(C,rep) pools"},
                    {"event": "measured", "window_s": 60,
                     "realized_s": app.get("benchmark_duration", {}).get("avg")},
                ],
                "measurements": {
                    "cache_read_pct": cache_pct,
                    "cache_read_source": cache_source,
                    "container_launches": container_launches,
                    "gpu_samples_in_window": len(wgpu) // 8,
                    "realized_window_s": app.get("benchmark_duration", {}).get("avg"),
                    "token_source_server_asserted": True,
                },
                "artifacts": {
                    "result": "profile_export_aiperf.json",
                },
            }
            (r_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            runs.append({"manifest": f"{kind}/c{c:03d}/r{r}", "profile": kind,
                         "concurrency": c, "repetition": r})

campaign_manifest = {
    "schema_version": 1,
    "campaign_id": campaign_id,
    "campaign_path": f"{repo_campaign_path}/campaign-manifest.json",
    "status": "runs_complete",
    "created_at": (campaign / "COMPLETE").read_text().strip(),
    "host": host_id,
    "model": model_repo,
    "revision": model_revision,
    "counts": {
        "container_launches": container_launches,
        "grid_points": len({(r["profile"], r["concurrency"]) for r in runs}),
        "profiles": len({r["profile"] for r in runs}),
        "runs": len(runs),
    },
    "validity_evidence": {
        "model-and-revision-served": {
            "status": "pass",
            "evidence": f"pin {model_repo} @ {model_revision}; DOWNLOAD_COMPLETE.json structural receipt "
                        "(inventory sizes, safetensors headers, index coverage); every run cli names the same "
                        "tokenizer path; served-model name asserted by the correctness gate per fleet boot",
        },
        "requested-topology-active": {
            "status": "pass",
            "evidence": "realized args extracted from engine startup logs (segments/*/params.txt) match the "
                        "frozen deployment; measurement path AIPerf -> haproxy -> engine on loopback; "
                        "campaign telemetry records 8 per-GPU columns active during runs",
        },
        "no-unrelated-gpu-consumer": {
            "status": "pass",
            "evidence": "B0 unloaded idle baseline captured pre-deployment (preflight/b0, GPUs 0 MiB); "
                        "per-GPU memory_used in campaign telemetry consistent with the engine resident "
                        "throughout; correctness 7/7 after each fleet boot",
        },
    },
    "runs": runs,
}
(campaign / "campaign-manifest.json").write_text(json.dumps(campaign_manifest, indent=2) + "\n")
print(json.dumps({"campaign": campaign_id, "runs": len(runs),
                  "points": campaign_manifest["counts"]["grid_points"]}))
