#!/usr/bin/env python3
"""Summarize raw VictoriaMetrics PCIe series without confusing rates/counters."""
from __future__ import annotations
import argparse, json, math, pathlib, statistics

RX="DCGM_FI_PROF_PCIE_RX_BYTES"; TX="DCGM_FI_PROF_PCIE_TX_BYTES"; REPLAY="DCGM_FI_DEV_PCIE_REPLAY_COUNTER"

def percentile(values, q):
    values=sorted(values)
    if not values: return None
    x=(len(values)-1)*q; lo=math.floor(x); hi=math.ceil(x)
    return values[lo] if lo==hi else values[lo]*(hi-x)+values[hi]*(x-lo)

def integrate(samples):
    """Trapezoidal integration of [timestamp, bytes/second] samples."""
    points=sorted((float(t),float(v)) for t,v in samples)
    return sum((b[0]-a[0])*(a[1]+b[1])/2 for a,b in zip(points,points[1:]))

def counter_delta(samples):
    """Increase with reset detection; missing values are never filled with zero."""
    points=sorted((float(t),float(v)) for t,v in samples)
    total=0.0; resets=0
    for (_,a),(_,b) in zip(points,points[1:]):
        if b >= a: total += b-a
        else: resets += 1; total += b
    return total,resets

def load(directory):
    manifest=json.loads((directory/"manifest.json").read_text())
    result={}
    for item in manifest["queries"]:
        doc=json.loads((directory/item["file"]).read_text())
        for series in doc.get("data",{}).get("result",[]):
            name=series.get("metric",{}).get("__name__")
            result.setdefault(name,[]).append(series)
    return manifest,result

def identity(metric):
    return metric.get("UUID") or metric.get("gpu") or metric.get("device") or "unknown"

def summarize_rate(series):
    out=[]
    for s in series:
        values=[float(x[1]) for x in s.get("values",[]) if math.isfinite(float(x[1]))]
        out.append({"gpu":identity(s.get("metric",{})),"labels":s.get("metric",{}),
                    "samples":len(values),"mean_bytes_per_second":statistics.fmean(values) if values else None,
                    "p50_bytes_per_second":percentile(values,.5),"p95_bytes_per_second":percentile(values,.95),
                    "peak_bytes_per_second":max(values) if values else None,
                    "integrated_bytes":integrate(s.get("values",[])) if len(values)>1 else None})
    return out

def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True,type=pathlib.Path); p.add_argument("--output",required=True,type=pathlib.Path)
    p.add_argument("--input-tokens",type=int); p.add_argument("--output-tokens",type=int); a=p.parse_args()
    manifest,data=load(a.input)
    directions={"rx":summarize_rate(data.get(RX,[])),"tx":summarize_rate(data.get(TX,[]))}
    replays=[]
    for s in data.get(REPLAY,[]):
        delta,resets=counter_delta(s.get("values",[])); replays.append({"gpu":identity(s.get("metric",{})),"labels":s.get("metric",{}),"delta":delta,"resets":resets,"samples":len(s.get("values",[]))})
    total_bytes=sum(x["integrated_bytes"] or 0 for direction in directions.values() for x in direction)
    doc={"schema_version":1,"source_manifest":str((a.input/"manifest.json").resolve()),"window":{"start":manifest["start"],"end":manifest["end"],"step":manifest["step"]},
         "semantics":{"pcie":"DCGM PCIe profiling samples are byte-rate gauges integrated by trapezoids.","replay":"Replay is a cumulative counter with reset-aware deltas."},
         "directions":directions,"replay_counters":replays,"aggregate":{"rx_plus_tx_integrated_bytes":total_bytes,
         "bytes_per_input_token":total_bytes/a.input_tokens if a.input_tokens else None,"bytes_per_output_token":total_bytes/a.output_tokens if a.output_tokens else None},
         "limitations":["GPU endpoint traffic is not a direct internal PCIe-switch counter.","Aggregation can double-count traffic observed at multiple endpoints; interpret using topology."]}
    a.output.parent.mkdir(parents=True,exist_ok=True); tmp=a.output.with_name(a.output.name+".tmp"); tmp.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n"); tmp.replace(a.output)
if __name__=="__main__": main()
