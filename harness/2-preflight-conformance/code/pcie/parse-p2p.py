#!/usr/bin/env python3
"""Parse CUDA p2pBandwidthLatencyTest square matrices."""
import argparse,csv,json,pathlib,re,statistics
HEADERS={
 'Unidirectional P2P=Disabled Bandwidth Matrix (GB/s)':('bandwidth','unidirectional',False,'GB/s'),
 'Unidirectional P2P=Enabled Bandwidth (P2P Writes) Matrix (GB/s)':('bandwidth','unidirectional',True,'GB/s'),
 'Bidirectional P2P=Disabled Bandwidth Matrix (GB/s)':('bandwidth','bidirectional',False,'GB/s'),
 'Bidirectional P2P=Enabled Bandwidth Matrix (GB/s)':('bandwidth','bidirectional',True,'GB/s'),
 'P2P=Disabled Latency Matrix (us)':('latency','unidirectional',False,'us'),
 'P2P=Enabled Latency (P2P Writes) Matrix (us)':('latency','unidirectional',True,'us'),
}
def main():
 p=argparse.ArgumentParser(); p.add_argument('log',type=pathlib.Path); p.add_argument('--output',required=True,type=pathlib.Path); a=p.parse_args(); lines=a.log.read_text(errors='replace').splitlines(); rows=[]; current=None; columns=[]
 for line in lines:
  text=line.strip()
  if text in HEADERS: current=HEADERS[text]; columns=[]; continue
  if current and re.match(r'^(D\\D|GPU)\s+',text): columns=[int(x) for x in text.split()[1:]]; continue
  if current and columns and re.match(r'^\d+\s+',text):
   parts=text.split(); src=int(parts[0]); vals=[float(x) for x in parts[1:1+len(columns)]]
   for dst,value in zip(columns,vals): rows.append({'metric':current[0],'direction':current[1],'p2p_enabled':current[2],'unit':current[3],'source_gpu':src,'destination_gpu':dst,'value':value})
   if src==columns[-1]: current=None
 summaries=[]
 for key in sorted({(r['metric'],r['direction'],r['p2p_enabled']) for r in rows}):
  values=[r['value'] for r in rows if (r['metric'],r['direction'],r['p2p_enabled'])==key and r['source_gpu']!=r['destination_gpu']]
  summaries.append({'metric':key[0],'direction':key[1],'p2p_enabled':key[2],'off_diagonal_count':len(values),'min':min(values),'median':statistics.median(values),'max':max(values)})
 a.output.mkdir(parents=True,exist_ok=True)
 with (a.output/'matrix.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 (a.output/'summary.json').write_text(json.dumps({'schema_version':1,'source':str(a.log.resolve()),'rows':rows,'summaries':summaries},indent=2)+'\n')
 print(f'parsed {len(rows)} cells')
if __name__=='__main__':main()
