#!/usr/bin/env python3
"""Finalize a campaign only after required closeout artifacts exist."""
import argparse,datetime as dt,json,os,pathlib,tempfile

def atomic(path,data):
 fd,name=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
 try:
  with os.fdopen(fd,'w') as f: json.dump(data,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
  os.replace(name,path)
 finally:
  if os.path.exists(name): os.unlink(name)
def main():
 p=argparse.ArgumentParser(); p.add_argument('campaign',type=pathlib.Path); p.add_argument('--allow-missing-post-idle',action='store_true'); a=p.parse_args(); root=a.campaign.resolve(); mp=root/'campaign-manifest.json'
 m=json.loads(mp.read_text()); missing=[]
 if m.get('status')!='runs_complete': missing.append('campaign status runs_complete')
 if not (root/'RUNS_COMPLETE').exists(): missing.append('RUNS_COMPLETE')
 for f in ('summaries/runs.csv','summaries/aggregate.csv','summaries/summary.json'):
  if not (root/f).is_file(): missing.append(f)
 if not a.allow_missing_post_idle and not (root/'idle/post/manifest.json').is_file():
  missing.append('idle/post/manifest.json')
 bad=[]
 for run in m.get('runs',[]):
  run_manifest=pathlib.Path(run['manifest'])
  if not run_manifest.is_absolute(): run_manifest=root/run_manifest
  if run.get('status')!='complete': bad.append(run.get('run_id'))
  elif not run_manifest.is_file(): bad.append(run.get('run_id'))
 if bad: missing.append(f'invalid run records: {bad}')
 if missing: raise SystemExit('cannot finalize; missing: '+', '.join(missing))
 m['status']='complete'; m['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(); atomic(mp,m)
 atomic(root/'CAMPAIGN_COMPLETE',{'campaign_id':m['campaign_id'],'completed_at':dt.datetime.now(dt.timezone.utc).isoformat()})
 print(root/'CAMPAIGN_COMPLETE')
if __name__=='__main__': main()
