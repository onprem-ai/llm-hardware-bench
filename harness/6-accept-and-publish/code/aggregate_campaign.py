#!/usr/bin/env python3
"""Aggregate completed AIPerf-compatible run summaries by profile/concurrency."""
from __future__ import annotations
import argparse, csv, json, pathlib, statistics
METRICS={"input_tps":("input_token_throughput","avg"),"output_tps":("output_token_throughput","avg"),"request_rps":("request_throughput","avg"),"ttft_p50_ms":("time_to_first_token","p50"),"ttft_p95_ms":("time_to_first_token","p95"),"itl_avg_ms":("inter_token_latency","avg"),"itl_p95_ms":("inter_token_latency","p95")}
def get(x,path):
    for p in path:
        if not isinstance(x,dict) or p not in x:return None
        x=x[p]
    return x if isinstance(x,(int,float)) else None
def main():
    p=argparse.ArgumentParser(); p.add_argument("campaign",type=pathlib.Path); a=p.parse_args(); campaign=a.campaign.resolve(); rows=[]
    campaign_manifest=json.loads((campaign/"campaign-manifest.json").read_text())
    for run in campaign_manifest.get("runs",[]):
        mp=pathlib.Path(run["manifest"])
        if not mp.is_absolute(): mp=campaign/mp
        m=json.loads(mp.read_text())
        if m.get("status")!="complete": continue
        result=pathlib.Path(m["artifacts"]["result"])
        if not result.is_absolute(): result=mp.parent/result
        if not result.exists(): continue
        data=json.loads(result.read_text()); row={"campaign_id":campaign_manifest["campaign_id"],"run_id":m["run_id"],"profile":m["profile"],"concurrency":m["concurrency"],"repetition":m["repetition"],"start_time":data.get("start_time",m.get("start_time")),"end_time":data.get("end_time",m.get("end_time")),"artifact_directory":str(mp.parent),"imported":bool(run.get("imported",False))}
        for name,path in METRICS.items(): row[name]=get(data,path)
        errors=data.get("error_summary",[]); row["errors"]=len(errors) if isinstance(errors,list) else None; rows.append(row)
    summaries=[]
    for key in sorted({(r["profile"],r["concurrency"]) for r in rows}):
        group=[r for r in rows if (r["profile"],r["concurrency"])==key]; out={"profile":key[0],"concurrency":key[1],"n":len(group),"errors":sum(r["errors"] or 0 for r in group)}
        for metric in METRICS:
            vals=[r[metric] for r in group if r[metric] is not None]
            out[metric+"_median"]=statistics.median(vals) if vals else None; out[metric+"_min"]=min(vals) if vals else None; out[metric+"_max"]=max(vals) if vals else None
        summaries.append(out)
    outdir=campaign/"summaries"; outdir.mkdir(exist_ok=True)
    def write_csv(path,data):
        if not data:return
        tmp=path.with_name(path.name+".tmp")
        with tmp.open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
        tmp.replace(path)
    write_csv(outdir/"runs.csv",rows); write_csv(outdir/"aggregate.csv",summaries)
    tmp=outdir/"summary.json.tmp"; tmp.write_text(json.dumps({"schema_version":1,"source_campaign":str(campaign),"runs":rows,"aggregate":summaries},indent=2)+"\n"); tmp.replace(outdir/"summary.json")
    print(f"aggregated {len(rows)} runs into {len(summaries)} points")
if __name__=="__main__": main()
