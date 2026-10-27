#!/usr/bin/env python3
from __future__ import annotations
import pathlib
"""Execute a declarative, resumable benchmark campaign.

Specs are YAML (PyYAML) or JSON. Commands are argv arrays with explicit
placeholders and are never passed through a shell.
"""
import argparse, datetime as dt, json, os, pathlib, random, re, shutil, signal, socket, subprocess, sys, tempfile, time, urllib.request, uuid
try:
    import yaml
except ImportError:
    yaml = None
ROOT = next(_a for _a in pathlib.Path(__file__).resolve().parents
            if (_a / '.git').exists())

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+".",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(data,f,indent=2,sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)
def load(path):
    text=path.read_text()
    if path.suffix==".json": return json.loads(text)
    if yaml is None: raise SystemExit("PyYAML is required for YAML specs; use JSON or install bootstrap requirements")
    return yaml.safe_load(text)
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
def expand(argv,values):
    def replace(value):
        def one(match):
            key=match.group(1)
            if key not in values: raise ValueError(f"unknown command placeholder {key!r}")
            return str(values[key])
        return PLACEHOLDER.sub(one,str(value))
    return [replace(x) for x in argv]
def health(url,timeout):
    if not url: return
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(url,timeout=5) as r:
                if 200 <= r.status < 300: return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError(f"health endpoint did not become ready: {url}")
def stop_processes(processes):
    for _,p in processes:
        if p.poll() is None: p.send_signal(signal.SIGTERM)
    deadline=time.monotonic()+10
    for _,p in processes:
        if p.poll() is None:
            try: p.wait(max(0,deadline-time.monotonic()))
            except subprocess.TimeoutExpired: p.kill(); p.wait()
def run_command(command,cwd,env,log):
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open("wb") as f: return subprocess.run(command,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
def validate(spec):
    for key in ("campaign","model","deployment","benchmark","profiles"):
        if key not in spec: raise ValueError(f"missing top-level key: {key}")
    if spec.get("schema_version") != 1: raise ValueError("schema_version must be 1")
    if not spec["benchmark"].get("command"): raise ValueError("benchmark.command must be a nonempty argv array")
    seen=set()
    for profile in spec["profiles"]:
        if not profile.get("concurrency"): raise ValueError(f"empty concurrency grid: {profile.get('name')}")
        if profile["name"] in seen: raise ValueError(f"duplicate profile: {profile['name']}")
        seen.add(profile["name"])
def plan(spec):
    jobs=[]
    reps=spec["campaign"]["repetitions"]
    for repetition in range(1,reps+1):
        points=[(p,c) for p in spec["profiles"] for c in p["concurrency"]]
        random.Random(spec["campaign"]["order_seed"]+repetition).shuffle(points)
        for profile,concurrency in points: jobs.append((repetition,profile,concurrency))
    return jobs
def imported_runs(spec):
    expected={(p["name"],c,r) for r,p,c in plan(spec)}; seen=set(); rows=[]
    for item in spec["campaign"].get("imported_runs",[]):
        source=pathlib.Path(item["manifest"]).expanduser().resolve()
        if not source.is_file(): raise ValueError(f"imported run manifest is missing: {source}")
        data=json.loads(source.read_text())
        key=(item["profile"],item["concurrency"],item["repetition"])
        if key not in expected: raise ValueError(f"imported run is outside campaign plan: {key}")
        if key in seen: raise ValueError(f"duplicate imported run: {key}")
        if data.get("status") != "complete": raise ValueError(f"imported run is not complete: {source}")
        if (data.get("profile"),data.get("concurrency"),data.get("repetition")) != key: raise ValueError(f"imported run identity mismatch: {source}")
        result=pathlib.Path(data.get("artifacts",{}).get("result",""))
        if not result.is_file(): raise ValueError(f"imported run result is missing: {result}")
        seen.add(key); rows.append({"run_id":data["run_id"],"profile":key[0],"concurrency":key[1],"repetition":key[2],"status":"complete","manifest":str(source),"imported":True})
    return rows
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("spec",type=pathlib.Path); ap.add_argument("--results-root",type=pathlib.Path); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--resume",action="store_true"); ap.add_argument("--health-timeout",type=int,default=30); a=ap.parse_args()
    spec=load(a.spec); validate(spec); campaign=spec["campaign"]; model=spec["model"]; deployment=spec["deployment"]
    root=(a.results_root or pathlib.Path(os.environ.get("LLM_BENCH_RESULTS_ROOT",pathlib.Path.home()/"llm-benchmark-results"))).expanduser().resolve()
    revision=model["revision"][:12]; out=root/socket.gethostname().lower()/model["slug"]/revision/deployment["id"]/campaign["id"]
    if out.exists() and not a.resume: raise SystemExit(f"campaign exists; use --resume: {out}")
    out.mkdir(parents=True,exist_ok=True); spec_copy=out/f"campaign-spec{a.spec.suffix.lower()}"
    if spec_copy.exists() and spec_copy.read_bytes()!=a.spec.read_bytes(): raise SystemExit("refusing resume: campaign spec changed")
    if not spec_copy.exists(): shutil.copyfile(a.spec,spec_copy)
    cm_path=out/"campaign-manifest.json"
    cm=json.loads(cm_path.read_text()) if cm_path.exists() else {"schema_version":1,"campaign_id":campaign["id"],"status":"planned","host":socket.gethostname(),"created_at":now(),"spec_path":str(a.spec.resolve()),"campaign_path":str(out),"model":model,"deployment":deployment,"runs":imported_runs(spec)}
    completed={(x["profile"],x["concurrency"],x["repetition"]) for x in cm["runs"] if x["status"] == "complete"}
    cm["status"]="dry_run" if a.dry_run else "running"; cm["updated_at"]=now(); atomic_json(cm_path,cm)
    if not a.dry_run: health(deployment.get("health_endpoint"),a.health_timeout)
    for repetition,profile,concurrency in plan(spec):
        key=(profile["name"],concurrency,repetition)
        if key in completed: continue
        stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"); run_id=f"{profile['name']}-c{concurrency:04d}-r{repetition:02d}-{uuid.uuid4().hex[:12]}"
        run_dir=out/"runs"/profile["name"]/f"c{concurrency:04d}"/f"run-r{repetition:02d}-{stamp}-{run_id[-12:]}"
        measured=run_dir/"measured"; telemetry=run_dir/"telemetry"; warmup=run_dir/"warmup"; measured.mkdir(parents=True); telemetry.mkdir(); warmup.mkdir()
        seed=campaign["order_seed"]+repetition*100000+concurrency
        uncapped_warmup=max(4,profile.get("warmup_requests_multiplier",2)*concurrency)
        warmup_cap=profile.get("warmup_requests_cap")
        warmup_requests=min(uncapped_warmup,warmup_cap) if warmup_cap is not None else uncapped_warmup
        values={"campaign_dir":str(out),"run_dir":str(run_dir),"artifact_dir":str(measured),"warmup_dir":str(warmup),"telemetry_dir":str(telemetry),"endpoint":deployment["endpoint"],"served_name":model["served_name"],"profile":profile["name"],"concurrency":concurrency,"repetition":repetition,"random_seed":seed,"input_tokens_mean":profile["input_tokens_mean"],"input_tokens_stddev":profile.get("input_tokens_stddev",0),"output_tokens_mean":profile["output_tokens_mean"],"output_tokens_stddev":profile.get("output_tokens_stddev",0),"benchmark_duration":profile.get("benchmark_duration",120),"warmup_requests":warmup_requests,"collector_interval":1}
        command=expand(spec["benchmark"]["command"]+profile.get("extra_args",[]),values)
        warm_values={**values,"artifact_dir":str(warmup)}
        warm_template=spec["benchmark"].get("warmup_command")
        if warm_template:
            warm_command=expand(warm_template+profile.get("extra_args",[]),warm_values)
        else:
            raise ValueError("benchmark.warmup_command is required; do not derive a warm-up by appending conflicting stop conditions")
        manifest={"schema_version":1,"campaign_id":campaign["id"],"run_id":run_id,"status":"planned","profile":profile["name"],"concurrency":concurrency,"repetition":repetition,"random_seed":seed,"command":command,"warmup_command":warm_command,"start_time":None,"end_time":None,"return_code":None,"error":None,"artifacts":{"run_dir":str(run_dir),"result":str(measured/spec["benchmark"]["result_file"])},"events":[{"state":"planned","at":now()}]}
        mp=run_dir/"manifest.json"; atomic_json(mp,manifest)
        if a.dry_run:
            manifest["status"]="dry_run"; manifest["events"].append({"state":"dry_run","at":now()}); atomic_json(mp,manifest)
        else:
            env=os.environ.copy(); env.update(spec["benchmark"].get("environment",{})); collectors=[]
            try:
                manifest["status"]="warming"; manifest["events"].append({"state":"warming","at":now()}); atomic_json(mp,manifest)
                rc=run_command(warm_command,ROOT,env,warmup/"console.log")
                if rc: raise RuntimeError(f"warmup exited {rc}")
                manifest["status"]="settling"; manifest["events"].append({"state":"settling","at":now()}); atomic_json(mp,manifest); time.sleep(campaign.get("settle_seconds",20))
                for c in spec.get("telemetry",{}).get("collectors",[]):
                    argv=expand(c["command"],values); log=(telemetry/f"{c['name']}.log").open("wb"); p=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT); collectors.append((log,p))
                manifest["status"]="measuring"; manifest["start_time"]=now(); manifest["events"].append({"state":"measuring","at":manifest["start_time"]}); atomic_json(mp,manifest)
                rc=run_command(command,ROOT,env,measured/"console.log"); manifest["return_code"]=rc; manifest["end_time"]=now(); stop_processes(collectors)
                for log,_ in collectors: log.close()
                if rc: raise RuntimeError(f"benchmark exited {rc}")
                if not (measured/spec["benchmark"]["result_file"]).exists(): raise RuntimeError("configured benchmark result file is missing")
                vm=spec.get("telemetry",{})
                if vm.get("victoriametrics_url") and vm.get("query_file"):
                    manifest["status"]="exporting"; manifest["events"].append({"state":"exporting","at":now()}); atomic_json(mp,manifest)
                    time.sleep(campaign.get("telemetry_delay_seconds",60))
                    export=[sys.executable,str(ROOT/"harness/2-preflight-conformance/code/victoriametrics/export-run-window.py"),"--url",vm["victoriametrics_url"],"--start",manifest["start_time"],"--end",manifest["end_time"],"--step",vm.get("step","1s"),"--query-file",str((ROOT/vm["query_file"]).resolve()),"--output",str(telemetry/"victoriametrics")]
                    rc=run_command(export,ROOT,env,telemetry/"victoriametrics-export.log")
                    if rc: raise RuntimeError(f"VictoriaMetrics export exited {rc}")
                manifest["status"]="complete"; manifest["events"].append({"state":"complete","at":now()})
            except BaseException as e:
                stop_processes(collectors)
                for log,_ in collectors:
                    if not log.closed: log.close()
                manifest["status"]="failed"; manifest["error"]=f"{type(e).__name__}: {e}"; manifest["end_time"]=manifest["end_time"] or now(); manifest["events"].append({"state":"failed","at":now()})
            atomic_json(mp,manifest)
        cm["runs"].append({"run_id":run_id,"profile":profile["name"],"concurrency":concurrency,"repetition":repetition,"status":manifest["status"],"manifest":str(mp.relative_to(out))}); cm["updated_at"]=now(); atomic_json(cm_path,cm)
        if manifest["status"]=="failed": break
    statuses=[x["status"] for x in cm["runs"]]; expected_jobs=plan(spec); expected=len(expected_jobs)
    complete_keys={(x["profile"],x["concurrency"],x["repetition"]) for x in cm["runs"] if x["status"] == "complete"}
    expected_keys={(p["name"],c,r) for r,p,c in expected_jobs}
    cm["counts"]={"expected":expected,"recorded":len(statuses),"complete_operating_points":len(complete_keys & expected_keys),"failed_attempts":statuses.count("failed"),"dry_run_attempts":statuses.count("dry_run")}
    if a.dry_run: cm["status"]="dry_run"
    elif complete_keys >= expected_keys: cm["status"]="complete"
    elif statuses.count("failed"): cm["status"]="complete_with_failures"
    else: cm["status"]="interrupted"
    cm["updated_at"]=now(); atomic_json(cm_path,cm)
    if cm["status"]=="complete":
        cm["status"]="runs_complete"; cm["updated_at"]=now(); atomic_json(cm_path,cm)
        atomic_json(out/"RUNS_COMPLETE",{"campaign_id":campaign["id"],"completed_at":now()})
    print(out); return 0 if cm["status"] in {"runs_complete","dry_run"} else 1
if __name__=="__main__": raise SystemExit(main())
