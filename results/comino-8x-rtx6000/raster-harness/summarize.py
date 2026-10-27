#!/usr/bin/env python3
"""Interim/final summary of the comino GLM-5.3 cold grid: medians per point from aiperf artifacts."""
import json, glob, sys, statistics as st

state = sys.argv[1]
rows = {}
for f in sorted(glob.glob(state + "/prefill/c*/r*/profile_export_aiperf.json") +
                glob.glob(state + "/decode/c*/r*/profile_export_aiperf.json")):
    parts = f.split("/")
    kind, c, r = parts[-4], int(parts[-3][1:]), parts[-2]
    d = json.load(open(f))
    rows.setdefault((kind, c), []).append({
        "in": d["input_token_throughput"]["avg"],
        "out": d["output_token_throughput"]["avg"],
        "cache_rd": d.get("usage_prompt_cache_read_tokens", {}).get("avg", 0),
        "reqs": d["request_count"]["avg"],
        "ttft": d["time_to_first_token"]["p50"],
        "itl": d["inter_token_latency"]["p50"],
    })

hdr = f"{'kind':8} {'C':>3} {'reps':>4} {'in_tok_s':>9} {'out_tok_s':>9} {'cache_rd':>8} {'reqs':>6} {'ttft_p50':>9} {'itl_p50':>8}"
print(hdr)
for (kind, c), v in sorted(rows.items()):
    med = lambda k: st.median(x[k] for x in v)
    print(f"{kind:8} {c:>3} {len(v):>4} {med('in'):>9.0f} {med('out'):>9.1f} "
          f"{max(x['cache_rd'] for x in v):>8.0f} {med('reqs'):>6.0f} {med('ttft'):>9.0f} {med('itl'):>8.1f}")

if "--json" in sys.argv:
    out = {f"{k}-c{c}": {"reps": len(v), **{m: st.median(x[m] for x in v) for m in ("in", "out", "ttft", "itl")}}
           for (k, c), v in rows.items()}
    json.dump(out, open(state + "/interim-summary.json", "w"), indent=2)
    print("wrote", state + "/interim-summary.json")
