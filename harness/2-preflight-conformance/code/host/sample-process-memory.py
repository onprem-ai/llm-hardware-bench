#!/usr/bin/env python3
"""Sample Linux smaps_rollup memory for processes matching a command regex.

RSS is retained for diagnosis but is not additive when mappings are shared.
PSS is the preferred approximately additive attribution metric. Permission-
denied or unavailable fields are left blank, never converted to zero.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
from pathlib import Path
import re
import signal
import time

FIELDS = (
    "Rss", "Pss", "Pss_Anon", "Pss_File", "Pss_Shmem", "Shared_Clean",
    "Shared_Dirty", "Private_Clean", "Private_Dirty", "Swap", "SwapPss",
)
STOP = False


def stop(*_):
    global STOP
    STOP = True


def text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return ""


def command(pid: Path) -> tuple[str, str]:
    comm = text(pid / "comm").strip()
    raw = b""
    try:
        raw = (pid / "cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
    cmdline = raw.replace(b"\0", b" ").decode(errors="replace").strip()
    return comm, cmdline


def smaps(pid: Path) -> dict[str, int | None]:
    values = {key: None for key in FIELDS}
    body = text(pid / "smaps_rollup")
    for line in body.splitlines():
        key, sep, rest = line.partition(":")
        if sep and key in values:
            try:
                values[key] = int(rest.split()[0])
            except (ValueError, IndexError):
                pass
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("interval", nargs="?", type=float, default=1.0)
    parser.add_argument(
        "--match",
        default=r"(^|[/ ])(?:vllm|sglang)(?:[ /.:]|$)|VLLM::|SGLang",
        help="command regex; defaults to vLLM and SGLang inference processes",
    )
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("interval must be positive")
    pattern = re.compile(args.match)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    columns = ["timestamp_utc", "pid", "comm", "cmdline", *[x.lower()+"_kib" for x in FIELDS]]
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader(); stream.flush()
        while not STOP:
            stamp = dt.datetime.now(dt.timezone.utc).isoformat()
            for pid in Path("/proc").iterdir():
                if not pid.name.isdigit():
                    continue
                comm, cmdline = command(pid)
                if not pattern.search(f"{comm} {cmdline}"):
                    continue
                values = smaps(pid)
                row = {"timestamp_utc": stamp, "pid": pid.name, "comm": comm, "cmdline": cmdline}
                row.update({key.lower()+"_kib": "" if value is None else value for key, value in values.items()})
                writer.writerow(row)
            stream.flush()
            deadline = time.monotonic() + args.interval
            while not STOP and time.monotonic() < deadline:
                time.sleep(min(0.1, max(0, deadline-time.monotonic())))


if __name__ == "__main__":
    main()
