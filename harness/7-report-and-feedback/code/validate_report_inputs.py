#!/usr/bin/env python3
"""Validate comparable-report inputs and enforce cross-document invariants.

JSON Schema validation is performed when jsonschema is installed. The semantic
checks below are dependency-free and always run.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def schema_errors(document: dict, schema_path: Path) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return []
    schema = load(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    ]


def semantic_errors(config: dict, data: dict) -> list[str]:
    errors: list[str] = []
    measured = config.get("axis", {}).get("measured_concurrency", [])
    maximum = config.get("axis", {}).get("maximum")
    ticks = config.get("axis", {}).get("major_ticks", [])
    if measured != sorted(measured):
        errors.append("axis.measured_concurrency must be sorted")
    if ticks != sorted(ticks):
        errors.append("axis.major_ticks must be sorted")
    if maximum is not None and measured and maximum < max(measured):
        errors.append("axis.maximum must include the highest measured concurrency")
    if maximum is not None and any(tick > maximum for tick in ticks):
        errors.append("axis.major_ticks must lie inside axis.maximum")

    for kind in ("decode", "prefill"):
        series = data.get("series", {}).get(kind, {})
        points = series.get("points", [])
        concurrencies = [point.get("concurrency") for point in points]
        if concurrencies != sorted(concurrencies):
            errors.append(f"series.{kind}.points must be sorted by concurrency")
        if len(concurrencies) != len(set(concurrencies)):
            errors.append(f"series.{kind}.points contains duplicate concurrency")
        if not set(concurrencies).issubset(set(measured)):
            errors.append(
                f"series.{kind} concurrency {concurrencies} is not a subset of configured axis {measured}"
            )
        if not concurrencies:
            errors.append(f"series.{kind}.points must contain at least one measured point")
        for point in points:
            for name, statistic in point.items():
                if name == "concurrency" or statistic is None:
                    continue
                if not isinstance(statistic, dict):
                    errors.append(f"series.{kind}.{name} must be a statistic object or null")
                    continue
                low, median, high = (
                    statistic.get("minimum"), statistic.get("median"), statistic.get("maximum")
                )
                if all(isinstance(x, (int, float)) and math.isfinite(x) for x in (low, median, high)):
                    if not low <= median <= high:
                        errors.append(
                            f"series.{kind} C{point.get('concurrency')} {name}: minimum <= median <= maximum violated"
                        )

    selection = data.get("selection", {})
    for kind in ("decode", "prefill"):
        source = data.get("series", {}).get(kind, {}).get("source_id")
        selected = selection.get(f"{kind}_source_id")
        if source != selected:
            errors.append(f"selection.{kind}_source_id does not match series.{kind}.source_id")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("data", type=Path)
    parser.add_argument("--schema-dir", type=Path, default=Path(__file__).resolve().parents[1] / "schemas")
    args = parser.parse_args()
    config, data = load(args.config), load(args.data)
    errors = []
    errors += [f"config {x}" for x in schema_errors(config, args.schema_dir / "report-config.schema.json")]
    errors += [f"data {x}" for x in schema_errors(data, args.schema_dir / "normalized-report-data.schema.json")]
    errors += semantic_errors(config, data)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"valid comparable report inputs: {args.config} + {args.data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
