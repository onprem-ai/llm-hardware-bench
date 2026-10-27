#!/usr/bin/env python3
"""Run a provenance-preserving NCCL topology/CPU-affinity matrix in Docker."""
from __future__ import annotations
import argparse,datetime as dt,json,os,pathlib,subprocess,tempfile

def atomic(path,data):
 fd,name=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
 try:
  with os.fdopen(fd,'w') as f: json.dump(data,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
  os.replace(name,path)
 finally:
  if os.path.exists(name): os.unlink(name)
def run(argv,path,dry):
 path.parent.mkdir(parents=True,exist_ok=True)
 if dry: path.write_text('DRY RUN\n'+'\n'.join(argv)+'\n'); return 0
 with path.open('wb') as f:return subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT).returncode

def resolve_policy(policy,dry_run=False):
 resolved=dict(policy)
 node=policy.get('cpu_node')
 if node is not None:
  cpulist=pathlib.Path(f'/sys/devices/system/node/node{node}/cpulist')
  if not cpulist.exists():
   if not dry_run: raise RuntimeError(f'NUMA node CPU list unavailable: {cpulist}')
   resolved['cpus']=f'<node{node}-cpulist>'
  else: resolved['cpus']=cpulist.read_text().strip()
  resolved['mems']=str(node)
 return resolved
def main():
 p=argparse.ArgumentParser(); p.add_argument('config',type=pathlib.Path); p.add_argument('--output',required=True,type=pathlib.Path); p.add_argument('--dry-run',action='store_true'); a=p.parse_args(); cfg=json.loads(a.config.read_text()); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True)
 image=cfg['runtime_image']; root=pathlib.Path(cfg['nccl_tests_root']).resolve(); tools_root=pathlib.Path(cfg.get('tools_root',root.parent)).resolve(); rng=cfg['message_range']; records=[]
 for group in cfg['groups']:
  gpus=','.join(map(str,group['gpus']))
  for policy_config in cfg['cpu_policies']:
   # Run all declared policies, including deliberately remote CPU/memory
   # placement; resolved host CPU lists remain in every record.
   policy=resolve_policy(policy_config,a.dry_run)
   for collective in cfg['collectives']:
    binary=root/'build'/collective; name=f"{group['name']}--{policy['name']}--{collective}"; raw=out/'raw'/f'{name}.log'
    argv=['docker','run','--rm','--gpus','all','--ipc=host','--cap-add','SYS_NICE','-e',f'CUDA_VISIBLE_DEVICES={gpus}','-e',f'LD_LIBRARY_PATH={tools_root}/nccl-prefix/lib:/usr/local/lib/python3.12/dist-packages/nvidia/nccl/lib']
    if policy.get('mems') is not None: argv.insert(3,'--privileged')
    argv += ['-v',f'{tools_root}:{tools_root}:ro']
    for k,v in sorted(cfg.get('environment',{}).items()): argv += ['-e',f'{k}={v}']
    test_args=[str(binary),'-b',rng['begin'],'-e',rng['end'],'-f',rng['factor'],'-g',str(len(group['gpus'])),'-n',str(rng['iterations']),'-w',str(rng['warmups']),'-c','1']
    if policy.get('cpus') is not None:
     # Apply affinity in-container. Docker --cpuset triggers an NVIDIA OCI hook
     # failure on some hosts before the process starts.
     argv += ['--entrypoint','numactl',image,'--physcpubind',policy['cpus'],'--membind',policy['mems'],*test_args]
    else:
     argv += ['--entrypoint',str(binary),image,*test_args[1:]]
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    rc=run(argv,raw,a.dry_run)
    ended=dt.datetime.now(dt.timezone.utc).isoformat()
    records.append({'name':name,'group':group,'cpu_policy':policy,'collective':collective,'command':argv,'started_at':started,'ended_at':ended,'return_code':rc,'raw_output':str(raw.relative_to(out))})
    if rc: break

 doc={'schema_version':1,'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'dry_run':a.dry_run,'config':cfg,'config_path':str(a.config.resolve()),'records':records,'status':'dry_run' if a.dry_run else ('passed' if all(x['return_code']==0 for x in records) else 'failed')}
 atomic(out/'manifest.json',doc); print(out); return 0 if doc['status'] in {'dry_run','passed'} else 1
if __name__=='__main__': raise SystemExit(main())
