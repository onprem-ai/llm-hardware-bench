#!/usr/bin/env python3
"""The collection contract: one declaration of what a campaign must contain.

Written because instruments kept under-collecting: a campaign measured throughput and shipped a
report whose power, temperature and host-CPU cells were empty. Telling a future operator to
"remember to sample telemetry" is not a guarantee; this file is.

The authoritative format is normalize_harness_campaign.sampler_rows(), which reads the campaign
telemetry log by field position. The template's per-point requirement (MeasurementsTable.astro)
is gpu_board_power, gpu_temperature, host_cpu_busy plus the latency percentiles -- so those are
what the contract demands, mapped onto the field positions that carry them.

Use:
    python3 collection_contract.py <campaign_dir>      # validate one campaign
"""
from __future__ import annotations

import pathlib
import sys

# Field positions in the campaign telemetry log (see telemetry-sampler.py).
FIRST_POWER, FIRST_UTIL, FIRST_TEMP, FIRST_VRAM, CPU_JIFFIES = 5, 13, 21, 29, 37
MIN_SAMPLES = 10

REQUIRED_RUNS = {
    "result_export": ("profile_export_aiperf.json", "throughput and latency"),
    "server_counters": ("server_metrics_export.json", "prefix cache, KV, scheduler counters"),
    "tool_log": ("run.log", "benchmark tool log; bounds the measurement window"),
}


def validate_campaign(campaign: pathlib.Path) -> list[str]:
    defects: list[str] = []
    log = campaign / "telemetry.csv"
    if not log.is_file():
        return ["telemetry_log missing: telemetry.csv -- no hardware data exists for this "
                "campaign, so GPU power, GPU temperature and host CPU cells cannot be filled"]
    lines = [ln for ln in log.read_text(errors="replace").splitlines() if ln.strip()]
    body = lines[1:]
    if len(body) < MIN_SAMPLES:
        defects.append(f"telemetry_log under-collected: {len(body)} sample(s), "
                       f"contract requires >= {MIN_SAMPLES}")
    short = [i for i, ln in enumerate(body, start=2) if len(ln.split(",")) < CPU_JIFFIES + 8]
    if short:
        defects.append(f"telemetry_log too narrow: {len(short)} row(s) stop before "
                       f"field {HOST_CPU} (GPU temperature / host CPU busy were not sampled)")
    runs = sorted(p for p in campaign.rglob("run.log") if p.is_file())
    if not runs:
        defects.append("no runs found under the campaign directory")
    for runlog in runs:
        run = runlog.parent
        for key, (rel, meaning) in REQUIRED_RUNS.items():
            if key == "tool_log":
                continue
            if not (run / rel).is_file():
                defects.append(f"{key} missing in {run.name}: {rel} ({meaning})")
    return defects


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    bad = 0
    for arg in argv:
        defects = validate_campaign(pathlib.Path(arg))
        if defects:
            bad += 1
            print(f"  {arg}: COLLECTION FAILURE")
            for d in defects:
                print(f"      - {d}")
        else:
            print(f"  {arg}: collection contract satisfied")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
