#!/usr/bin/env python3
"""Parse nccl-tests rows and summarize large-message plateaus."""
import argparse,csv,json,pathlib,re,statistics
ROW=re.compile(r'^\s*(\d+)\s+(\d+)\s+\S+\s+\S+\s+-?\d+\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(\d+)\s*$')
def main():
 p=argparse.ArgumentParser(); p.add_argument('matrix',type=pathlib.Path); a=p.parse_args(); root=a.matrix.resolve(); m=json.loads((root/'manifest.json').read_text()); rows=[]
 for rec in m['records']:
  path=root/rec['raw_output']
  for line in path.read_text(errors='replace').splitlines():
   x=ROW.match(line)
   if x:
    size,count,t1,a1,b1,w1,t2,a2,b2,w2=x.groups(); rows.append({'test':rec['name'],'group':rec['group']['name'],'cpu_policy':rec['cpu_policy']['name'],'collective':rec['collective'],'size_bytes':int(size),'element_count':int(count),'out_of_place_time_us':float(t1),'out_of_place_algbw_gbps':float(a1),'out_of_place_busbw_gbps':float(b1),'out_of_place_wrong':int(w1),'in_place_time_us':float(t2),'in_place_algbw_gbps':float(a2),'in_place_busbw_gbps':float(b2),'in_place_wrong':int(w2)})
 summaries=[]
 for key in sorted({(r['test'],r['collective'],r['group'],r['cpu_policy']) for r in rows}):
  group=[r for r in rows if (r['test'],r['collective'],r['group'],r['cpu_policy'])==key]; large=sorted(group,key=lambda r:r['size_bytes'])[-3:]
  summaries.append({'test':key[0],'collective':key[1],'group':key[2],'cpu_policy':key[3],'rows':len(group),'largest_size_bytes':max(r['size_bytes'] for r in group),'wrong_total':sum(r['out_of_place_wrong']+r['in_place_wrong'] for r in group),'large_message_busbw_median_gbps':statistics.median(r['out_of_place_busbw_gbps'] for r in large),'large_message_algbw_median_gbps':statistics.median(r['out_of_place_algbw_gbps'] for r in large)})
 out=root/'summary.csv'
 if summaries:
  with out.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=summaries[0]);w.writeheader();w.writerows(summaries)
 (root/'parsed.json').write_text(json.dumps({'schema_version':1,'rows':rows,'summaries':summaries},indent=2)+'\n'); print(f'parsed {len(rows)} rows')
if __name__=='__main__':main()
