#!/usr/bin/env python3
"""Decide from measured server counters whether a run was cold (R-05-2).

Prefix caching makes prefill throughput cheap rather than fast, so "prefill
throughput" is only comparable when the served prompt fraction is known. This
tool never infers cache state from configuration: it reads the run's own
`server_metrics_export.json` and reports what the engine actually did.

Exit codes (consumed by shell harnesses and by acceptance):
  0  cold      -- served fraction at or below the limit
  1  warm      -- served fraction above the limit; the number is cache-served
  2  unknown   -- counters absent; the run may not be labelled cold either
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HITS = "vllm:prefix_cache_hits"
QUERIES = "vllm:prefix_cache_queries"
SGLANG_PREFILL = "sglang:prefill_effective_tokens"
SGLANG_HIT_MODES = ("device_hit", "host_hit", "storage_hit")


def total(metrics: dict, name: str):
    """Counter total for `name`, or None when the metric is absent."""
    series = (metrics.get(name, {}) or {}).get("series") or []
    if not series:
        return None
    return (series[0].get("stats") or {}).get("total")


def sglang_totals(metrics: dict):
    """(hits, queries) from sglang's mode-labelled prefill counter, or (None, None).

    `sglang:prefill_effective_tokens_total` (exported without the `_total`
    suffix) counts effective prefill tokens per mode; the metric's own HELP
    defines the windowed hit rate as rate(hits)/rate(all modes), where hits are
    device_hit/host_hit/storage_hit and the uncached remainder is `input`.
    One series per TP rank, so the counter is summed across ranks.
    """
    series = (metrics.get(SGLANG_PREFILL, {}) or {}).get("series") or []
    hits = inputs = 0.0
    seen = False
    for s in series:
        mode = (s.get("labels") or {}).get("mode")
        v = (s.get("stats") or {}).get("total")
        if v is None:
            continue
        seen = True
        if mode in SGLANG_HIT_MODES:
            hits += v
        elif mode == "input":
            inputs += v
    if not seen:
        return None, None
    return hits, hits + inputs


def served_fraction(run_dir: pathlib.Path):
    """(served_fraction, requests_issued, reason) measured for one run."""
    # Artifact names drift between releases (0.13 writes profile_export.jsonl and no longer
    # emits *_aiperf.json), so locate the export by role rather than by one literal name.
    path = run_dir / "server_metrics_export.json"
    if not path.is_file():
        candidates = sorted(run_dir.glob("server_metrics_export*.json*"))
        if not candidates:
            return None, None, ("no server-metrics export in "
                                f"{run_dir.name}; look for a `--server-metrics` flag in the "
                                "benchmark command and check the tool version's artifact names")
        path = candidates[0]
    metrics = json.loads(path.read_text()).get("metrics", {})
    hits, queries = total(metrics, HITS), total(metrics, QUERIES)
    if hits is None or not queries:
        hits, queries = sglang_totals(metrics)
    if hits is None or not queries:
        return None, None, "prefix-cache counters absent from the export"
    requests = None
    export = run_dir / "profile_export_aiperf.json"
    if export.is_file():
        e = json.loads(export.read_text())
        r = e.get("request_count")
        requests = r.get("avg") if isinstance(r, dict) else r
    return float(hits) / float(queries), requests, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=pathlib.Path)
    ap.add_argument("--max-served-pct", type=float, default=2.0)
    ap.add_argument("--expect-cold", action="store_true",
                    help="exit non-zero unless the run is cold")
    args = ap.parse_args()

    fraction, requests, reason = served_fraction(args.run_dir)
    if fraction is None:
        print(f"{args.run_dir}: cache state unknown ({reason}); "
              "the run may not be labelled cold")
        return 2
    pct = 100.0 * fraction
    verdict = "cold" if pct <= args.max_served_pct else "warm"
    print(f"  {args.run_dir.name}: served_prompt_pct={pct:.3f} "
          f"requests={requests if requests is not None else 'n/a'} "
          f"limit={args.max_served_pct:.2f}% verdict={verdict}")
    if not args.expect_cold:
        return 0
    return 0 if verdict == "cold" else 1


if __name__ == "__main__":
    sys.exit(main())
