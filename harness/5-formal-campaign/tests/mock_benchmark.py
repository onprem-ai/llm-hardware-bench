#!/usr/bin/env python3
import argparse, datetime as dt, json, pathlib, time
import pathlib
p=argparse.ArgumentParser(); p.add_argument('--artifact-dir',required=True); p.add_argument('--concurrency',type=int,required=True); p.add_argument('--random-seed',type=int,required=True); p.add_argument('--profile',default='test'); p.add_argument('--request-count',type=int); p.add_argument('--benchmark-duration',type=int)
a=p.parse_args(); out=pathlib.Path(a.artifact_dir); out.mkdir(parents=True,exist_ok=True); start=dt.datetime.now(dt.timezone.utc).isoformat(); time.sleep(.01); end=dt.datetime.now(dt.timezone.utc).isoformat()
x={"schema_version":"test","benchmark_id":f"mock-{a.random_seed}","start_time":start,"end_time":end,"request_count":{"avg":a.request_count or a.concurrency},"benchmark_duration":{"avg":.01,"unit":"sec"},"input_token_throughput":{"avg":100*a.concurrency,"unit":"tokens/sec"},"output_token_throughput":{"avg":50*a.concurrency,"unit":"tokens/sec"},"time_to_first_token":{"p50":10,"p95":20,"unit":"ms"},"inter_token_latency":{"avg":5,"p95":8,"unit":"ms"},"error_summary":[],"was_cancelled":False}
(out/'profile_export_aiperf.json').write_text(json.dumps(x,indent=2)+'\n')
