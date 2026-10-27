import re,sys
a,b=sys.argv[1],sys.argv[2]
def load(p):
 out={}
 for line in open(p):
  if line.startswith('#') or not line.strip(): continue
  m=re.match(r'^(\S+?)(\{[^}]*\})?\s+(\S+)$',line.strip())
  if not m: continue
  n=m.group(1).replace(':','_'); v=float(m.group(3))
  out[n]=out.get(n,0.0)+v
 return out
x,y=load(a),load(b)
keys=[k for k in y if 'spec' in k or k.startswith('vllm_num_') or 'prefix_cache' in k]
print('delta')
for k in sorted(keys):
 d=y[k]-x.get(k,0.0)
 if d: print(' ',k,d)
if 'vllm_spec_decode_num_accepted_tokens_total' in y:
 acc=y.get('vllm_spec_decode_num_accepted_tokens_total',0)-x.get('vllm_spec_decode_num_accepted_tokens_total',0)
 dr=y.get('vllm_spec_decode_num_draft_tokens_total',0)-x.get('vllm_spec_decode_num_draft_tokens_total',0)
 ns=y.get('vllm_spec_decode_num_drafts_total',0)-x.get('vllm_spec_decode_num_drafts_total',0)
 if dr: print(' accept_rate',acc/dr,'accepted_per_step',(acc+ns)/ns if ns else 0)
