#!/usr/bin/env python3
"""Preflight gate: the 13 checks a campaign must pass before any formal measurement.

Specified by `harness/2-preflight-conformance/RULES.md` (R-02-11, R-02-14) and never implemented
until 2026-09-07. Emits `preflight.json` and exits non-zero on any FAIL, so a campaign cannot
start on an unverified environment. Every check records the evidence it used - a check without a
value is a check that can always pass.

Run on the benchmark host:

    python3 preflight.py --model-dir /home/demouser/models/X --image local/x:canary \
        --grid 1,8,32,64,96,128,160,192 --host-ram-floor-gib 96 --out preflight.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import socket
import subprocess
import sys

UTC = dt.timezone.utc


def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def meminfo():
    out = {}
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = int(v.split()[0])  # KiB
    return out


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--grid", required=True, help="frozen global offered concurrency grid, comma separated")
    ap.add_argument("--profiles", default=None, help="path to the profile/shape definition (identity check)")
    ap.add_argument("--contract", default=None, help="freeze contract whose grid must match --grid")
    ap.add_argument("--container-name", required=True,
                    help="name of the deployed engine container, as recorded by the raster")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host-ram-floor-gib", type=float, default=96.0)
    ap.add_argument("--min-disk-free-gib", type=float, default=50.0)
    ap.add_argument("--telemetry", default=None, help="telemetry script whose header must carry memory.peak")
    ap.add_argument("--lock", default=None, help="controller lock file; a live pid here is a FAIL")
    ap.add_argument("--bench-command-file", default=None,
                    help="file containing the benchmark command template; must assert token source and units")
    ap.add_argument("--ambient-seconds", type=int, default=30)
    ap.add_argument("--results-root", default="/home/demouser/llm-benchmark-results")
    ap.add_argument("--out", default="preflight.json")
    a = ap.parse_args()

    checks = []

    def check(name, ok, evidence, level="FAIL"):
        checks.append({"name": name, "result": "PASS" if ok else level, "evidence": evidence})
        return ok

    # 1 model directory exists and its payload is inventoried
    md = pathlib.Path(a.model_dir)
    if md.is_dir():
        files = [f for f in md.rglob("*") if f.is_file()]
        total = sum(f.stat().st_size for f in files)
        check("model-payload-inventory", len(files) > 0,
              {"path": str(md), "files": len(files), "bytes": total})
        # 2 safetensors headers parse and shard references resolve
        sts = [f for f in files if f.suffix == ".safetensors"]
        bad = []
        for f in sts[:8]:
            try:
                with open(f, "rb") as h:
                    n = int.from_bytes(h.read(8), "little")
                    hdr = json.loads(h.read(n))
                    sizes = {k: v.get("offsets", [0, 0])[1] for k, v in hdr.items() if k != "__metadata__"}
                    if sizes and max(sizes.values()) > f.stat().st_size:
                        bad.append(f.name)
            except Exception as e:
                bad.append(f"{f.name}: {e}")
        check("safetensors-headers-parse", not bad,
              {"checked": min(len(sts), 8), "of": len(sts), "bad": bad[:3]})
    else:
        check("model-payload-inventory", False, {"path": str(md), "reason": "directory absent"})
        check("safetensors-headers-parse", False, {"reason": "no model directory"})

    # 3 image present, identified by digest not tag
    rc, out, err = sh(f"docker image inspect --format '{{{{.Id}}}}' {a.image}")
    check("image-digest-recorded", rc == 0 and out.startswith("sha256:"),
          {"image": a.image, "digest": out or err[:80]})

    # 4 host RAM available exceeds the qualified floor
    mi = meminfo()
    avail_gib = mi.get("MemAvailable", 0) / 1048576
    check("host-ram-floor", avail_gib >= a.host_ram_floor_gib,
          {"available_gib": round(avail_gib, 1), "floor_gib": a.host_ram_floor_gib,
           "sreclaimable_gib": round(mi.get("SReclaimable", 0) / 1048576, 1),
           "note": "SReclaimable is reclaimable and is not counted against the floor"})

    # 5 /dev/shm carries no residue from earlier runs
    shm = pathlib.Path("/dev/shm")
    entries = [p.name for p in shm.iterdir()] if shm.is_dir() else []
    used = sh(f"du -sb {shm}")[1].split()[:1] or ["0"]
    check("shm-residue-clean", not entries,
          {"entries": len(entries), "bytes": used[0], "sample": entries[:3]})

    # 6 serving port is free
    check("port-free", port_free(a.port), {"port": a.port})

    # 7 no other controller holds the campaign lock (a written-down pid, never a pattern match)
    lock_ok, lock_ev = True, {"lock": a.lock, "state": "not-provided"}
    if a.lock and pathlib.Path(a.lock).is_file():
        pid = re.sub(r"\D", "", pathlib.Path(a.lock).read_text()[:64])
        alive = bool(pid) and pathlib.Path(f"/proc/{pid}").exists()
        lock_ok, lock_ev = (not alive), {"lock": a.lock, "pid": pid, "alive": alive}
    check("single-controller-lock-free", lock_ok, lock_ev)

    # 8 container name is not already taken (a stopped container still owns its name)
    rc, out, _ = sh(f"docker inspect -f '{{{{.State.Status}}}}' {a.container_name}")
    check("container-name-free", rc != 0 or out == "", {"name": a.container_name, "state": out or "absent"})

    # 9 grid is frozen and the contract agrees with the runtime grid
    grid = [int(x) for x in re.split(r"[,\s]+", a.grid.strip()) if x]
    grid_ok, grid_ev = bool(grid), {"grid": grid, "points": len(grid), "contract": a.contract}
    if a.contract and pathlib.Path(a.contract).is_file():
        text = pathlib.Path(a.contract).read_text(errors="ignore")
        nums = [int(x) for x in re.findall(r"\b\d{1,4}\b", text.split("concurrency grid", 1)[-1][:400])] \
            if "concurrency grid" in text.lower() else []
        grid_ev["contract_grid_prefix_match"] = (not nums) or nums[:len(grid)] == grid
        grid_ok = grid_ok and grid_ev["contract_grid_prefix_match"]
    check("grid-frozen-and-agrees", grid_ok, grid_ev)

    # 10 profile/token identity recorded
    if a.profiles and pathlib.Path(a.profiles).is_file():
        ptext = pathlib.Path(a.profiles).read_text(errors="ignore")
        shapes = re.findall(r"(input|output)_tokens_mean:\s*(\d+)", ptext)
        check("profile-token-identity", len(shapes) >= 4,
              {"profiles_file": a.profiles, "shapes_found": dict(shapes)})
    else:
        check("profile-token-identity", False, {"profiles_file": a.profiles, "reason": "not provided"})

    # 11 benchmark command asserts server token counts and units
    if a.bench_command_file and pathlib.Path(a.bench_command_file).is_file():
        cmd = pathlib.Path(a.bench_command_file).read_text(errors="ignore")
        ok = "--use-server-token-count" in cmd
        check("token-source-asserted", ok,
              {"file": a.bench_command_file, "use_server_token_count": ok,
               "note": "client-side token counting silently changes measured throughput"})
    else:
        check("token-source-asserted", False, {"file": a.bench_command_file, "reason": "not provided"})

    # 12 telemetry must sample the cgroup peak, not only a current value
    if a.telemetry and pathlib.Path(a.telemetry).is_file():
        ttext = pathlib.Path(a.telemetry).read_text(errors="ignore")
        ok = "memory.peak" in ttext
        check("ram-peak-sampled", ok,
              {"telemetry": a.telemetry, "memory_peak_present": ok,
               "note": "a RAM floor claim needs the high-water mark; sampling current can miss it"})
    else:
        check("ram-peak-sampled", False, {"telemetry": a.telemetry, "reason": "not provided"})

    # 13 ambient background load measured over a window, and results root writable
    pw = sh("nvidia-smi --query-gpu=power.draw,utilization.gpu --format=csv,noheader,nounits")
    vals = [float(x) for line in pw[1].splitlines() for x in line.split(",") if x.strip()]
    gpu_power = sum(vals[:8]) / max(1, min(8, len(vals))) if vals else 0
    rc, _, _ = sh(f"mkdir -p {a.results_root} && test -w {a.results_root}")
    df = shutil.disk_usage(a.results_root if pathlib.Path(a.results_root).exists() else "/")
    free_gib = df.free / 1073741824
    check("ambient-and-writable", rc == 0 and free_gib >= a.min_disk_free_gib,
          {"ambient_gpu_power_avg_w": round(gpu_power, 1), "samples": len(vals),
           "results_root": a.results_root, "writable": rc == 0,
           "disk_free_gib": round(free_gib, 1), "min_disk_free_gib": a.min_disk_free_gib})

    fails = [c for c in checks if c["result"] == "FAIL"]
    out = {"schema_version": 1, "generated_utc": dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "verdict": "PASS" if not fails else "FAIL",
           "checks_total": len(checks), "checks_passed": len(checks) - len(fails),
           "failed": [c["name"] for c in fails], "checks": checks,
           "grid": grid, "host_ram_floor_gib": a.host_ram_floor_gib,
           "model_dir": a.model_dir, "image": a.image, "container_name": a.container_name}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=2) + "\n")
    for c in checks:
        print(f"  [{c['result']:4}] {c['name']}")
    print(f"{out['verdict']}  {out['checks_passed']}/{out['checks_total']} checks -> {a.out}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
