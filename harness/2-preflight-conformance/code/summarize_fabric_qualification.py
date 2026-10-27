#!/usr/bin/env python3
import argparse,csv,datetime as dt,json,pathlib,statistics

import pathlib
def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);a=p.parse_args();root=a.root.resolve()
 rows=list(csv.DictReader((root/'nccl-matrix/summary.csv').open()))
 for r in rows:
  for k in ('large_message_busbw_median_gbps','large_message_algbw_median_gbps'):r[k]=float(r[k])
 def vals(group,policy):return {r['collective']:r['large_message_busbw_median_gbps'] for r in rows if r['group']==group and r['cpu_policy']==policy}
 comparisons=[]
 for local,local_policy in [('tp4-numa0','numa0'),('tp4-numa1','numa1')]:
  base=vals(local,local_policy);remote=vals(local,'numa1' if local_policy=='numa0' else 'numa0');cross=vals('tp4-cross-numa',local_policy)
  for c in sorted(base):
   comparisons.append({'collective':c,'local_group':local,'local_policy':local_policy,'local_busbw_gbps':base[c],'remote_cpu_busbw_gbps':remote[c],'remote_cpu_penalty_pct':100*(base[c]-remote[c])/base[c],'cross_numa_busbw_gbps':cross[c],'cross_numa_penalty_pct':100*(base[c]-cross[c])/base[c]})
 dcgm=json.loads((root/'dcgm-controlled-load/validation/metric-availability.json').read_text())
 selected={x['name']:{k:x[k] for k in ('availability','validation','changed_series','maximum_absolute_delta')} for x in dcgm['metrics'] if x['name'] in ('DCGM_FI_PROF_PCIE_RX_BYTES','DCGM_FI_PROF_PCIE_TX_BYTES','DCGM_FI_DEV_PCIE_REPLAY_COUNTER')}
 p2p=json.loads((root/'p2p/parsed/summary.json').read_text())
 uncore=json.loads((root/'uncore-probe-v2/availability.json').read_text())
 report={'schema_version':1,'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'root':str(root),'nccl':{'cases':len(rows),'parsed_rows':sum(int(r['rows']) for r in rows),'wrong_total':sum(int(r['wrong_total']) for r in rows),'comparisons':comparisons},'p2p':p2p['summaries'],'dcgm':selected,'uncore':uncore,'upi':{'status':'unavailable','reason':'UPI PMUs exist but expose no named sysfs events; pinned Intel PCM detected four UPI ports/socket but could not acquire occupied/restricted PMUs. Destructive PCM -r was not used.','evidence':'pcm-probe/'},'limitations':['DCGM PCIe rates are GPU endpoint rates, not internal switch counters.','CUDA sample P2P output warns it is not a formal performance benchmark.','NCCL uses the pinned serving-image NCCL version and NCCL_IB_DISABLE=1.']}
 (root/'qualification-summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 with (root/'numa-comparison.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=comparisons[0]);w.writeheader();w.writerows(comparisons)
 print(json.dumps(report['nccl'],indent=2))
if __name__=='__main__':main()
