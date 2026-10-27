#!/usr/bin/env python3
"""Derive what a report needs from what a campaign actually collected.

Two defects made empty charts possible, and both are this file's reason for existing:

1. Report configs carried hand-authored capability flags (``temperature: false``,
   ``pcie: false``, ``energy_method: ...``). A cloned config silently declared capabilities the
   new campaign never measured, and nobody re-read them.
2. The renderer drew a panel whenever its name appeared, regardless of whether any data for it
   existed. A missing measurement therefore appeared on the page as an empty box instead of as
   a failure.

Capability is not a declaration; it is a fact about evidence. This module computes the facts
from normalized report data and the run artifacts, and reports a deficit for every panel the
report intends to render. A deficit is an error to fix by collecting, never by deleting a panel.
"""
from __future__ import annotations

import pathlib
import sys

# panel -> evidence that must exist for it to be renderable. Each source is either a key of
# normalized metric_availability, or "artifact:<path relative to a run dir>".
PANEL_SOURCES: dict[str, list[str]] = {
    "throughput": ["throughput", "artifact:profile_export_aiperf.json"],
    "ttft": ["ttft_p50", "ttft_p95"],
    "itl": ["itl_p50", "itl_p99"],
    "e2e": ["e2e_p50", "e2e_p99"],
    "server_decode_rate": ["server_decode_rate"],
    "gpu_power": ["gpu_board_power", "artifact:telemetry/gpu.csv"],
    "gpu_energy": ["gpu_board_power", "artifact:telemetry/gpu.csv"],
    "gpu_utilisation": ["gpu_util_pct", "artifact:telemetry/gpu.csv"],
    "gpu_vram": ["gpu_mem_used_gib", "artifact:telemetry/gpu.csv"],
    "gpu_temperature": ["gpu_temperature_c", "artifact:telemetry/gpu.csv"],
    "host_ram": ["host_ram_available", "artifact:telemetry/gpu.csv"],
    "host_cpu": ["host_cpu_util_pct", "artifact:telemetry/gpu.csv"],
    "fabric": ["fabric_qualification"],
}


def deficits(panels: list[str], availability: dict, run_dirs: list[pathlib.Path]) -> list[str]:
    """Every panel whose evidence is absent. Empty list means the report can be rendered whole."""
    problems: list[str] = []
    for panel in panels:
        for src in PANEL_SOURCES.get(panel, []):
            if src.startswith("artifact:"):
                rel = src.split(":", 1)[1]
                if run_dirs and not any((d / rel).is_file() for d in run_dirs):
                    problems.append(f"{panel}: no run contains {rel}")
            elif not availability.get(src):
                problems.append(f"{panel}: metric {src} was not sampled")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(__doc__)
        return 2
    import json
    data = json.load(open(argv[0]))
    panels = data.get("panels") or list(PANEL_SOURCES)
    runs = [pathlib.Path(p) for p in (data.get("run_dirs") or [])]
    problems = deficits(panels, data.get("metric_availability") or {}, runs)
    for p in problems:
        print(f"  PANEL UNBACKED  {p}")
    print(f"  {len(problems)} deficit(s) across {len(panels)} panel(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
