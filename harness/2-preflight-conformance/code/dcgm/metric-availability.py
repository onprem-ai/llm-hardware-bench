#!/usr/bin/env python3
"""Build a machine-readable DCGM metric availability and change report.

This parser intentionally uses only the Python standard library. It compares two
Prometheus text snapshots without interpreting a missing series as zero.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
from pathlib import Path

SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>.*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|NaN|[+-]Inf)"
    r"(?:\s+\d+)?$"
)
LABEL_RE = re.compile(r'(\w+)="((?:\\.|[^"\\])*)"')



def parse_collector(path: Path) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(line for line in f if not line.lstrip().startswith("#")):
            if not row or not row[0].strip():
                continue
            if len(row) < 3:
                raise ValueError(f"invalid collector row: {row!r}")
            fields.append({"name": row[0].strip(), "prometheus_type": row[1].strip(),
                           "help": ",".join(row[2:]).strip()})
    return fields


def parse_prometheus(path: Path) -> tuple[dict[str, str], dict[str, list[dict]]]:
    types: dict[str, str] = {}
    samples: dict[str, list[dict]] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("# TYPE "):
            parts = line.split()
            if len(parts) >= 4:
                types[parts[2]] = parts[3]
            continue
        if not line or line.startswith("#"):
            continue
        match = SAMPLE_RE.match(line)
        if not match:
            continue
        value_text = match.group("value")
        try:
            value = float(value_text)
        except ValueError:
            continue
        labels = {k: bytes(v, "utf-8").decode("unicode_escape")
                  for k, v in LABEL_RE.findall(match.group("labels") or "")}
        samples.setdefault(match.group("name"), []).append({"labels": labels, "value": value})
    return types, samples


def series_key(sample: dict) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(sample["labels"].items()))


def comparable(before: list[dict], after: list[dict]) -> tuple[int, int, float | None]:
    left = {series_key(s): s["value"] for s in before}
    right = {series_key(s): s["value"] for s in after}
    common = left.keys() & right.keys()
    changed = 0
    max_delta: float | None = None
    for key in common:
        a, b = left[key], right[key]
        if math.isfinite(a) and math.isfinite(b):
            delta = abs(b - a)
            if delta > 0:
                changed += 1
            max_delta = delta if max_delta is None else max(max_delta, delta)
    return len(common), changed, max_delta


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--collector", required=True, type=Path)
    p.add_argument("--before", required=True, type=Path)
    p.add_argument("--after", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--endpoint")
    p.add_argument("--discovery", type=Path)
    p.add_argument("--load-executed", action="store_true")
    args = p.parse_args()

    requested = parse_collector(args.collector)
    before_types, before = parse_prometheus(args.before)
    after_types, after = parse_prometheus(args.after)
    discovery_text = (args.discovery.read_text(encoding="utf-8", errors="replace")
                      if args.discovery and args.discovery.exists() else "")
    records = []
    for field in requested:
        name = field["name"]
        b, a = before.get(name, []), after.get(name, [])
        emitted = bool(b or a)
        common, changed, max_delta = comparable(b, a)
        if not emitted:
            availability = "not_emitted"
            validation = "unavailable"
        elif not b or not a:
            availability = "intermittent"
            validation = "inconclusive"
        elif args.load_executed and changed:
            availability = "emitted"
            validation = "changed_under_load"
        elif args.load_executed:
            availability = "emitted"
            validation = "static_under_load"
        else:
            availability = "emitted"
            validation = "not_tested_under_load"
        records.append({
            **field,
            "exported_type": after_types.get(name, before_types.get(name)),
            "availability": availability,
            "validation": validation,
            "before_series": len(b),
            "after_series": len(a),
            "comparable_series": common,
            "changed_series": changed,
            "maximum_absolute_delta": max_delta,
            "mentioned_in_discovery_output": name in discovery_text if discovery_text else None,
        })

    document = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "endpoint": args.endpoint,
        "load_executed": args.load_executed,
        "inputs": {
            "collector": {"path": str(args.collector.resolve())},
            "before": {"path": str(args.before.resolve())},
            "after": {"path": str(args.after.resolve())},
            "discovery": ({"path": str(args.discovery.resolve())}
                          if args.discovery and args.discovery.exists() else None),
        },
        "summary": {
            "requested": len(records),
            "emitted": sum(r["availability"] == "emitted" for r in records),
            "not_emitted": sum(r["availability"] == "not_emitted" for r in records),
            "intermittent": sum(r["availability"] == "intermittent" for r in records),
            "changed_under_load": sum(r["validation"] == "changed_under_load" for r in records),
        },
        "metrics": records,
        "interpretation": {
            "not_emitted": "The endpoint did not emit the requested field; this is not a zero value.",
            "static_under_load": "The field was emitted but did not change; support is not disproved.",
            "mentioned_in_discovery_output": "Textual evidence only; runtime emission remains authoritative.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
