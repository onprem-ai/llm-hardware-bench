#!/usr/bin/env python3
"""Campaign telemetry sampler -- speaks the format normalize_harness_campaign.sampler_rows reads.

Wire format (one row per sample, fixed field positions; the header names only the first seven):

    0  utc                      ISO8601 Z
    1  memory_current_bytes     inference container cgroup (NA when unavailable)
    2  memory_peak_bytes        container peak (NA when unavailable)
    3  memory_max_bytes         container limit (NA when unavailable)
    4  host_mem_available_kb    /proc/meminfo MemAvailable
    5..12   power_w             per GPU, 8 devices
    13..20  util_pct            per GPU, 8 devices
    21..28  temperature_c       per GPU      (appended: older readers stop at 21)
    29..36  memory_used_mib     per GPU
    37..44  cpu jiffies         user,nice,system,iowait,irq,softirq,steal,idle (host aggregate).
    45  engine_ram_anon_bytes     summed over --container: the part the kernel cannot reclaim
    46  engine_ram_file_bytes     page cache -- reclaimable, so NOT a cost when sizing a machine
    47  engine_ram_shmem_bytes    shared buffers between engine processes
    48  engine_ram_current_bytes  summed cgroup current, same instant as 45..47
    49  engine_ram_peak_bytes     running maximum of 48 as observed by this sampler
    50  engine_container_count    how many containers 45..48 describe
            The adapter derives host_cpu_busy from these counters as a delta ratio, so raw
            jiffies are written and busy percentages are not: a percentage computed here could
            not be differenced across a window.

Fields are appended, never reordered, because readers take slices by position: existing
campaigns keep parsing, new campaigns gain temperature and CPU. GPU count is fixed at 8 as in
the campaigns this reproduces; a host with fewer devices pads with NA rather than shifting
positions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import os
import subprocess
import sys

PROC = pathlib.Path(os.environ.get("PROC_ROOT", "/proc"))
import time

GPUS = 8


def sh(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


def query(field: str) -> list[float]:
    out = sh("nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits")
    vals = []
    for line in out.strip().splitlines():
        try:
            vals.append(float(line.strip()))
        except ValueError:
            vals.append(float("nan"))
    while len(vals) < GPUS:
        vals.append(float("nan"))
    return vals[:GPUS]


def resolve(name: str) -> str:
    """Container id, resolved once at start. Per-sample `docker inspect` would put client
    latency inside the measurement loop and report NA the moment docker is briefly busy."""
    return sh("docker", "inspect", "--format", "{{.Id}}", name).strip()


def cgroup_dir(cid: str) -> pathlib.Path:
    return pathlib.Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope")


def cgroup_bytes(cid: str, kind: str) -> str:
    try:
        return cgroup_dir(cid).joinpath(f"memory.{kind}").read_text().strip()
    except Exception:
        return "NA"


# memory.stat keys that separate "RAM the inference really holds" from "RAM the kernel could
# take back". current - anon - file - slab is mostly kernel/page-table overhead; publishing
# current alone cannot distinguish a 56 GiB heap from 56 GiB of reclaimable weight cache, and
# those two mean completely different things to a reader sizing a machine.
RAM_STAT_KEYS = ("anon", "file", "shmem")


def cgroup_stat(cid: str, key: str) -> str:
    try:
        for line in cgroup_dir(cid).joinpath("memory.stat").read_text().splitlines():
            if line.startswith(key + " "):
                return line.split()[1]
    except Exception:
        pass
    return "NA"


def engine_ram(cids) -> dict:
    """Summed RAM of every inference container, plus the per-container detail."""
    detail, sums = [], {k: 0 for k in ("current",) + RAM_STAT_KEYS}
    ok = False
    for cid in cids:
        cur = cgroup_bytes(cid, "current")
        vals = {"current": cur, **{k: cgroup_stat(cid, k) for k in RAM_STAT_KEYS}}
        if cur != "NA":
            ok = True
            for k, v in vals.items():
                if v != "NA":
                    sums[k] += int(v)
        detail.append(dict(cid=cid, **vals))
    return {"ok": ok, "sums": sums if ok else None, "detail": detail}


def mem_available_kb() -> str:
    for line in PROC.joinpath("meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return line.split()[1]
    return "NA"


CPU_FIELDS = ["user", "nice", "system", "iowait", "irq", "softirq", "steal", "idle"]


def cpu_counters() -> list[str]:
    """Aggregate jiffies in the order the adapter's delta_ratio expects."""
    parts = [int(x) for x in PROC.joinpath("stat").read_text().splitlines()[0].split()[1:]]
    want = [parts[0], parts[1], parts[2], parts[4] if len(parts) > 4 else 0,
            parts[5] if len(parts) > 5 else 0, parts[6] if len(parts) > 6 else 0,
            parts[8] if len(parts) > 8 else 0, parts[3]]
    return [str(v) for v in want]


def fmt(v: float) -> str:
    return "NA" if v != v else f"{v:.2f}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--container", default="",
                    help="engine container name(s), comma-separated; for 4xTP2 pass all four replicas,\n                         RAM fields then describe the sum and each replica is logged separately")
    ap.add_argument("--interval", type=float, default=5.0)
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not sh("nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits").strip():
        print("REFUSED: nvidia-smi returned no GPU power; the sampling contract cannot be met.",
              file=sys.stderr)
        return 2
    new = not out.is_file() or out.stat().st_size == 0

    names = [n.strip() for n in args.container.split(",") if n.strip()]
    cids = [c for c in (resolve(n) for n in names) if c]
    if names and not cids:
        sys.exit("none of the requested containers resolved: " + ",".join(names))
    peak_agg = 0
    ram_log = out.parent / (out.stem + "-ram.csv")
    if not ram_log.exists():
        ram_log.write_text("utc,container,container_id,memory_current_bytes,"
                           "memory_anon_bytes,memory_file_bytes,memory_shmem_bytes\n")
    with out.open("a") as fh:
        if new:
            fh.write("utc,memory_current_bytes,memory_peak_bytes,memory_max_bytes,"
                     "host_mem_available_kb,power_w,util_pct\n")
        while True:
            pw = query("power.draw")
            ut = query("utilization.gpu")
            tp = query("temperature.gpu")
            mm = query("memory.used")
            now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ram = engine_ram(cids)
            sums = ram["sums"] or {}
            # Running aggregate peak, measured rather than summed from per-container highs:
            # summing four replicas' memory.peak would report a spike none of them had at the
            # same instant.
            if sums:
                agg = sums["current"]
                peak_agg = max(peak_agg, agg)
            row = ([now,
                    cgroup_bytes(cids[0], "current") if cids else "NA",
                    cgroup_bytes(cids[0], "peak") if cids else "NA",
                    cgroup_bytes(cids[0], "max") if cids else "NA",
                    mem_available_kb()] + [fmt(v) for v in pw] + [fmt(v) for v in ut]
                    + [fmt(v) for v in tp] + [fmt(v) for v in mm] + cpu_counters()
                    + [str(sums.get(k, "NA")) for k in ("anon", "file", "shmem", "current")]
                    + [str(peak_agg) if sums else "NA", str(len(cids))])
            fh.write(",".join(row) + "\n")
            with ram_log.open("a") as rf:
                for j, d in enumerate(ram["detail"]):
                    rf.write(f'{now},{names[j] if j < len(names) else "?"},{d["cid"][:12]},'
                           f'{d["current"]},{d["anon"]},{d["file"]},{d["shmem"]}\n')
            fh.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
