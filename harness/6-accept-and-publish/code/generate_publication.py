#!/usr/bin/env python3
from __future__ import annotations
import pathlib
"""Generate a portable, schema-validated benchmark publication JSON."""
import argparse, importlib.util, json
from pathlib import Path

ROOT = next(_a for _a in pathlib.Path(__file__).resolve().parents
            if (_a / '.git').exists())

def load(path):return json.loads(path.read_text())
def schema_validate(document,path):
    try:import jsonschema
    except ImportError as exc:raise SystemExit("jsonschema is required; install harness/2-preflight-conformance/code/bootstrap/requirements.in") from exc
    schema=load(path);normalized=load(ROOT/'harness/7-report-and-feedback/schemas/normalized-report-data.schema.json')
    resolver=jsonschema.RefResolver.from_schema(schema,store={normalized['$id']:normalized})
    errors=sorted(jsonschema.Draft202012Validator(schema,resolver=resolver).iter_errors(document),key=lambda x:list(x.path))
    if errors:raise ValueError("\n".join(f"{'.'.join(map(str,e.path)) or '<root>'}: {e.message}" for e in errors))
def best(series):
    points=[x for x in series['points'] if x.get('throughput') and x['throughput'].get('median') is not None]
    if not points:raise ValueError('series has no throughput observations')
    return max(points,key=lambda x:x['throughput']['median'])
def main():
    p=argparse.ArgumentParser();p.add_argument('report_config',type=Path);p.add_argument('normalized_data',type=Path);p.add_argument('--hardware-model',required=True);p.add_argument('--aggregate-vram-gib',required=True,type=float);p.add_argument('--report-path',help='optional path to an archived standalone HTML report; the site renders reports natively');p.add_argument('--normalized-data-path',help='path to normalized-report-data.json relative to the publication, so the site can publish campaign receipts beside it');p.add_argument('--output',required=True,type=Path);p.add_argument('--id');p.add_argument('--model-name');p.add_argument('--classification',default='repeated benchmark evidence');p.add_argument('--description');a=p.parse_args()
    config,data=load(a.report_config),load(a.normalized_data)
    vp=ROOT/'harness/7-report-and-feedback/code/validate_report_inputs.py';spec=importlib.util.spec_from_file_location('validate_report_inputs',vp);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    errors=mod.schema_errors(config,ROOT/'harness/7-report-and-feedback/schemas/report-config.schema.json')+mod.schema_errors(data,ROOT/'harness/7-report-and-feedback/schemas/normalized-report-data.schema.json')+mod.semantic_errors(config,data)
    if errors:raise ValueError('\n'.join(errors))
    dec,pre=best(data['series']['decode']),best(data['series']['prefill']);model=config['model'];hardware=config['hardware'];deployment=config['deployment'];counts=data['source_counts'];model_name=a.model_name or model['display_name']
    description=a.description or f"Measured Prefill and Decode capacity for {model_name} on {a.hardware_model} with {hardware['gpu_count']} {hardware['gpu_model']} GPUs."
    # Deployment and axis keys keep report-config.json's names so the published
    # document can be read against the campaign config without a translation table.
    report={'kind':'capacity-report','date':config['report'].get('campaign_date'),'subtitle':config['report'].get('subtitle')}
    if a.report_path:report['path']=a.report_path
    doc={
      'schema_version':1,
      'id':a.id or config['report']['id'],
      'title':config['report']['title'],
      'description':description,
      'keywords':[a.hardware_model,model_name,model['repository'],'LLM inference benchmark','GPU server benchmark','Prefill throughput','Decode throughput'],
      'hardware':{'model':a.hardware_model,'host':hardware['host'],'gpu_count':hardware['gpu_count'],'gpu_model':hardware['gpu_model'],'aggregate_vram_gib':a.aggregate_vram_gib},
      'model':{'name':model_name,'repository':model['repository'],'revision':model['revision'],'quantization':model.get('quantization') or 'unspecified'},
      'report':report,
      'deployment':{
        'summary':deployment['topology_display'],
        'request_path':'AIPerf → HAProxy → model server replicas',
        'replicas':deployment.get('replicas'),
        'tensor_parallel_per_replica':deployment.get('tensor_parallel_per_replica'),
        'active_sequence_ceiling':deployment.get('active_sequence_ceiling'),
        'kv_cache_dtype':deployment.get('kv_cache_dtype'),
        'speculative_decoding':deployment.get('speculative_decoding'),
        'max_model_len':deployment.get('max_model_len'),
        'max_num_seqs_per_replica':deployment.get('max_num_seqs_per_replica'),
        'max_num_batched_tokens_per_replica':deployment.get('max_num_batched_tokens_per_replica'),
        'cpu_numa_affinity':deployment.get('cpu_numa_affinity'),
      },
      'source':{'campaign_path':config.get('source',{}).get('campaign_path'),'normalized_data_path':a.normalized_data_path},
      'evidence':{'runs':counts['runs'],'requests':counts['requests'],'errors':counts['errors'],'repetitions':min(x['throughput']['n'] for kind in ('decode','prefill') for x in data['series'][kind]['points']),'classification':a.classification},
      'axis':{'measured_concurrency':config['axis']['measured_concurrency'],'major_ticks':config['axis'].get('major_ticks'),'maximum':config['axis'].get('maximum')},
      'headlines':{
        'decode':{'value':dec['throughput']['median'],'unit':'output tokens/s','concurrency':dec['concurrency'],'statistic':'median'},
        'prefill':{'value':pre['throughput']['median'],'unit':'input tokens/s','concurrency':pre['concurrency'],'statistic':'median'},
      },
      'normalized_data':data,
      'notes':config.get('provenance_notes',[]),
    }
    doc['axis']={k:v for k,v in doc['axis'].items() if v is not None}
    schema_validate(doc,ROOT/'harness/6-accept-and-publish/schemas/benchmark-publication.schema.json');a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
