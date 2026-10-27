#!/usr/bin/env python3
from __future__ import annotations
import pathlib
"""Render a self-contained comparable report from validated normalized data."""
import argparse, html, json, shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = next(_a for _a in pathlib.Path(__file__).resolve().parents
            if (_a / '.git').exists())

def h(value): return html.escape(str(value))
def number(value,digits=0):
    if value is None:return "unavailable"
    return f"{value:,.{digits}f}"
def point_value(point,metric):
    value=point.get(metric)
    return value.get("median") if isinstance(value,dict) else None
def best(series):
    return max(series["points"],key=lambda p:point_value(p,"throughput") if point_value(p,"throughput") is not None else float('-inf'))
def compact(data):
    output=[]
    aliases={"throughput":"decode_tps"} # corrected per kind below
    for kind,series in data["series"].items():
        for point in series["points"]:
            row={"kind":kind,"concurrency":point["concurrency"],"n":point["throughput"]["n"],"errors":0}
            mapping={
              "throughput":"decode_tps" if kind=="decode" else "input_tps",
              "per_user_throughput":"per_user_tps","ttft_p50":"ttft_p50_ms","ttft_p95":"ttft_p95_ms",
              "itl_average":"itl_avg_ms","itl_p95":"itl_p95_ms","gpu_board_power":"gpu_power_w",
              "joules_per_token":"gpu_j_per_output_token" if kind=="decode" else "gpu_j_per_input_token",
              "host_cpu_busy":"cpu_busy_pct","host_ram_used":"ram_used_gib","gpu_utilization":"gpu_util_pct",
              "gpu_temperature":"gpu_temp_c","gpu_vram_used":"gpu_vram_used_gib","running_requests":"running_requests",
              "waiting_requests":"waiting_requests","kv_cache_usage":"kv_cache_pct","mamba_usage":"mamba_usage_pct","speculative_acceptance":"mtp_acceptance_pct",
              "cpu_user":"cpu_user_pct","cpu_system":"cpu_system_pct","cpu_iowait":"cpu_iowait_pct","host_load1":"load1",
              "gpu_memory_copy":"gpu_memcopy_pct","gpu_sm_clock":"gpu_sm_clock_mhz","gpu_memory_clock":"gpu_mem_clock_mhz",
              "container_cpu":"container_cpu_cores","container_memory":"container_memory_gib","container_tx":"container_tx_mib_s",
              "process_rss":"process_rss_gib","process_pss":"process_pss_gib","process_private":"process_private_gib",
              "process_shared":"process_shared_gib","process_swap":"process_swap_gib",
              "disk_write":"disk_write_mib_s","preemptions":"preemptions_s","server_decode_rate":"generation_rate",
              "server_prompt_rate":"prompt_rate","pcie_rx":"pcie_rx_gbps","pcie_tx":"pcie_tx_gbps",
              "pcie_replay_delta":"pcie_replay_delta",
              "haproxy_frontend_ingress":"haproxy_frontend_ingress_mib_s","haproxy_frontend_egress":"haproxy_frontend_egress_mib_s",
              "haproxy_backend_ingress":"haproxy_backend_ingress_mib_s","haproxy_backend_egress":"haproxy_backend_egress_mib_s",
              "haproxy_ingress_per_request":"haproxy_ingress_kib_request","haproxy_egress_per_request":"haproxy_egress_kib_request",
              "haproxy_queue":"haproxy_queue","haproxy_retries":"haproxy_retries","haproxy_errors":"haproxy_errors",
              "haproxy_backend_imbalance":"haproxy_backend_imbalance_pct"
            }
            for src,dst in mapping.items():
                stat=point.get(src)
                if stat:
                    row[dst+"_median"]=stat.get("median");row[dst+"_min"]=stat.get("minimum");row[dst+"_max"]=stat.get("maximum");row[dst+"_mean"]=stat.get("mean");row[dst+"_sd"]=stat.get("standard_deviation")
            output.append(row)
    return output

def range_kpi(item,unit,label,digits=2,suffix=""):
    if not item or item.get("minimum") is None or item.get("maximum") is None:
        return f'<div class="kpi"><div class="n">unavailable</div><div class="u">{h(label)}</div></div>'
    low,high=item["minimum"],item["maximum"];central=(low+high)/2
    display_suffix=suffix or (f' {unit}' if unit else '')
    return f'<div class="kpi"><div class="n">{central:.0f}{h(display_suffix)}</div><div class="u">{h(label)}</div><p>Observed variation: {low:.{digits}f}-{high:.{digits}f}{h(display_suffix)}</p></div>'

def grouped_bar_svg(groups,series,y_label,theoretical_max=None,theoretical_label=None):
    width,height=700,340;left,right,top,bottom=72,18,48,58
    values=[value for group in groups for value in group["values"] if value is not None]
    if not values:return '<div class="unavailable">Unavailable - no fabric measurements</div>'
    maximum=max(values)*1.15 or 1;plot_w=width-left-right;plot_h=height-top-bottom;colors=["#086c83","#d36b32","#7557a5"]
    parts=[f'<svg class="fabric-svg" viewBox="0 0 {width} {height}" role="img">']
    if theoretical_max is not None:maximum=max(maximum,theoretical_max*1.08)
    for tick in range(5):
        value=maximum*tick/4;y=top+plot_h-(value/maximum)*plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e9eeeb"/><text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-size="10" font-weight="700" fill="#45535b">{value:.0f}</text>')
    group_width=plot_w/len(groups);bar_width=min(34,group_width/(len(series)+1))
    for group_index,group in enumerate(groups):
        center=left+group_width*(group_index+.5)
        for index,value in enumerate(group["values"]):
            if value is None:continue
            x=center+(index-(len(series)-1)/2)*bar_width-bar_width*.38;y=top+plot_h-(value/maximum)*plot_h;height_value=top+plot_h-y
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width*.76:.1f}" height="{height_value:.1f}" fill="{colors[index]}"/><text x="{x+bar_width*.38:.1f}" y="{y-5:.1f}" text-anchor="middle" font-size="9" font-weight="700">{value:.1f}</text>')
        parts.append(f'<text x="{center:.1f}" y="{height-bottom+22}" text-anchor="middle" font-size="10">{h(group["label"])}</text>')
    if theoretical_max is not None:
        y=top+plot_h-(theoretical_max/maximum)*plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#aa4050" stroke-width="1.5" stroke-dasharray="6 4"/><text x="{width-right}" y="{y-5:.1f}" text-anchor="end" font-size="9" fill="#aa4050">{h(theoretical_label or theoretical_max)}</text>')
    legend_x=left
    for index,name in enumerate(series):
        x=legend_x+index*150;parts.append(f'<rect x="{x}" y="15" width="12" height="12" fill="{colors[index]}"/><text x="{x+18}" y="25" font-size="10" font-weight="700">{h(name)}</text>')
    parts.append(f'<text x="14" y="{top+plot_h/2:.1f}" transform="rotate(-90 14 {top+plot_h/2:.1f})" text-anchor="middle" font-size="11" font-weight="700">{h(y_label)}</text></svg>')
    return ''.join(parts)

def p2p_heatmap_svg(rows,direction):
    selected=[row for row in rows if row.get("direction")==direction];lookup={(row["source_gpu"],row["destination_gpu"]):row["value"] for row in selected};off=[value for (source,destination),value in lookup.items() if source!=destination]
    if not off:return '<div class="unavailable">Unavailable - no P2P matrix</div>'
    low,high=min(off),max(off);cell=43;left=45;top=38;width=left+8*cell+12;height=top+8*cell+42;parts=[f'<svg class="fabric-svg" viewBox="0 0 {width} {height}" role="img">']
    for index in range(8):
        parts.append(f'<text x="{left+index*cell+cell/2}" y="24" text-anchor="middle" font-size="10" font-weight="700">GPU {index}</text><text x="{left-6}" y="{top+index*cell+cell/2+4}" text-anchor="end" font-size="10" font-weight="700">GPU {index}</text>')
    for source in range(8):
        for destination in range(8):
            value=lookup.get((source,destination));diagonal=source==destination
            if diagonal:color="#d8dfdc";text="self"
            elif value is None:color="#f5f7f6";text="-"
            else:
                ratio=(value-low)/(high-low) if high>low else .5;color=f'rgb({int(225-150*ratio)},{int(240-130*ratio)},{int(240-105*ratio)})';text=f'{value:.1f}'
            x=left+destination*cell;y=top+source*cell;parts.append(f'<rect x="{x}" y="{y}" width="{cell-1}" height="{cell-1}" fill="{color}"/><text x="{x+(cell-1)/2:.1f}" y="{y+cell/2+4:.1f}" text-anchor="middle" font-size="9">{text}</text>')
    theoretical=63 if direction=="unidirectional" else 126
    parts.append(f'<text x="{left+4*cell}" y="{height-18}" text-anchor="middle" font-size="10">Destination GPU - off-diagonal range {low:.2f}-{high:.2f} GB/s</text><text x="{left+4*cell}" y="{height-5}" text-anchor="middle" font-size="9" fill="#aa4050">Theoretical Gen5 x16 payload ceiling: about {theoretical} GB/s per pair</text></svg>')
    return ''.join(parts)

def fabric_section(data):
    fabric=data.get("host_fabric")
    if not fabric:
        return '<section id="fabric"><div class="eyebrow">Host fabric qualification</div><h2>PCIe, NCCL, P2P, and NUMA</h2><div class="callout"><b>Unavailable.</b> No host-fabric qualification input was supplied.</div></section>'
    uni=fabric.get("p2p_unidirectional_gbps") or {};bi=fabric.get("p2p_bidirectional_gbps") or {};comparisons=fabric.get("nccl_comparisons",[])
    collective_names=[("all_reduce_perf","All-reduce"),("all_gather_perf","All-gather"),("reduce_scatter_perf","Reduce-scatter")]
    bandwidth_groups=[];penalty_groups=[]
    for key,label in collective_names:
        rows=[row for row in comparisons if row.get("collective")==key]
        median=lambda field: sorted(row[field] for row in rows)[len(rows)//2] if len(rows)%2 else sum(sorted(row[field] for row in rows)[len(rows)//2-1:len(rows)//2+1])/2
        bandwidth_groups.append({"label":label,"values":[median("local_busbw_gbps"),median("cross_numa_busbw_gbps"),median("remote_cpu_busbw_gbps")]})
        penalty_groups.append({"label":label,"values":[median("cross_numa_penalty_pct"),median("remote_cpu_penalty_pct")]})
    limitations="".join(f"<li>{h(x)}</li>" for x in fabric.get("limitations",[]));upi=fabric.get("upi") or {};matrix=fabric.get("p2p_bandwidth_matrix",[])
    return f'''<section id="fabric"><div class="eyebrow">Host fabric qualification</div><h2>PCIe, NCCL, P2P, and NUMA</h2>
<p class="sub">Active host-level microbenchmarks are separate from inference-window endpoint telemetry.</p>
<div class="kpis">{range_kpi(fabric.get("same_numa_all_reduce_busbw_gbps"),"GB/s","NCCL TP4 all-reduce bus bandwidth, same NUMA")}
{range_kpi(fabric.get("cross_numa_all_reduce_busbw_gbps"),"GB/s","NCCL TP4 all-reduce bus bandwidth, cross NUMA")}
{range_kpi(fabric.get("cross_numa_penalty_pct"),"","Cross-NUMA all-reduce penalty",1,"%")}
{range_kpi(fabric.get("remote_cpu_penalty_pct"),"","Remote CPU/memory placement penalty",1,"%")}</div>
<div class="grid2"><div class="panel"><h3>NCCL bandwidth by collective and placement</h3>{grouped_bar_svg(bandwidth_groups,["Same NUMA","Cross NUMA","Remote CPU"],"BUS BANDWIDTH (GB/s)")}</div>
<div class="panel"><h3>NUMA and placement penalties</h3>{grouped_bar_svg(penalty_groups,["Cross NUMA","Remote CPU"],"PENALTY (%)")}</div>
<div class="panel"><h3>CUDA P2P unidirectional bandwidth</h3>{p2p_heatmap_svg(matrix,"unidirectional")}<p><b>Unidirectional:</b> {number(uni.get("min"),2)}-{number(uni.get("max"),2)} GB/s; median {number(uni.get("median"),2)} GB/s.</p></div>
<div class="panel"><h3>CUDA P2P bidirectional bandwidth</h3>{p2p_heatmap_svg(matrix,"bidirectional")}<p><b>Bidirectional:</b> {number(bi.get("min"),2)}-{number(bi.get("max"),2)} GB/s; median {number(bi.get("median"),2)} GB/s.</p></div>
<div class="panel"><h3>Negotiated PCIe link</h3><div class="link-state"><div><span>Idle</span><b>Gen1 x16</b><small>{h(fabric.get("link_idle") or "unavailable")}</small></div><div class="link-arrow">-></div><div><span>Sustained load</span><b>Gen5 x16</b><small>{h(fabric.get("link_under_load") or "unavailable")}</small></div></div></div></div>
<div class="callout"><b>Interpretation boundary.</b> Per-run DCGM PCIe RX/TX values are aggregate GPU-endpoint rates, not direct internal PCIe-switch port counters. UPI telemetry: {h(upi.get("status") or "unavailable")}.</div>
<div class="note"><b>Fabric limitations</b><ul>{limitations}</ul><p class="foot">Source: <code>{h(fabric.get("source"))}</code></p></div></section>'''

def main():
    p=argparse.ArgumentParser();p.add_argument("config",type=Path);p.add_argument("data",type=Path);p.add_argument("--output-dir",type=Path);p.add_argument("--runs-csv",type=Path);p.add_argument("--aggregate-csv",type=Path);p.add_argument("--template",type=Path,default=ROOT/"harness/7-report-and-feedback/code/templates/comparable-report.html");a=p.parse_args()
    config=json.loads(a.config.read_text());data=json.loads(a.data.read_text())
    # Reuse the semantic validator; schema checks run when jsonschema is installed.
    import importlib.util
    vp=ROOT/"harness/7-report-and-feedback/code/validate_report_inputs.py";spec=importlib.util.spec_from_file_location("report_validate",vp);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    errors=mod.semantic_errors(config,data)
    if errors:raise SystemExit("invalid report inputs:\n"+"\n".join(errors))
    out=(a.output_dir or a.config.parent).resolve();out.mkdir(parents=True,exist_ok=True)
    decode=best(data["series"]["decode"]);prefill=best(data["series"]["prefill"]);axis=config["axis"];dep=config["deployment"];hardware=config["hardware"]
    repetition_counts=sorted({point["throughput"]["n"] for series in data["series"].values() for point in series["points"]})
    if repetition_counts==[1]:
        statistic_text="Each point is one qualification measurement; no repetition variance is established."
    else:
        statistic_text="Central values are medians; bands show the observed repetition range."
    provenance_notes="".join(f"<li>{h(note)}</li>" for note in config.get("provenance_notes",[]))
    ceiling=dep.get("active_sequence_ceiling");maximum=axis["maximum"]
    if ceiling and ceiling<=maximum:
        ceiling_js=f"let ceil=x({ceiling});s.append(E('line',{{x1:ceil,y1:m.t,x2:ceil,y2:H-m.b,stroke:'#7557a5','stroke-dasharray':'4 4'}}));s.append(E('text',{{x:ceil-3,y:m.t+12,'text-anchor':'end',fill:'#7557a5','font-size':8}},'{ceiling} ACTIVE-SEQUENCE CEILING'));"
        overload=[x for x in axis["measured_concurrency"] if x>ceiling]
        callout=(f'<div class="callout"><b>Overload coverage.</b> Measured concurrency '
                 f'{", ".join("C"+str(x) for x in overload)} exceeds the configured C{ceiling} active-sequence ceiling.</div>') if overload else ''
    else:
        ceiling_js='';callout=(f'<div class="callout"><b>Capacity coverage.</b> Measurements extend through C{max(axis["measured_concurrency"])}. '
                               f'The configured C{ceiling} active-sequence ceiling lies outside the measured range.</div>' if ceiling else '')
    short_topology=f'{dep["replicas"]}×TP{dep["tensor_parallel_per_replica"]}'
    diagram='AIPerf → load balancer\n'+"\n".join(f'  {"├" if i<dep["replicas"]-1 else "└"}─ Replica {chr(65+i)} · TP{dep["tensor_parallel_per_replica"]}' for i in range(dep["replicas"]))
    method='Each operating point uses repeated measurements, warm-up, settling, streaming output, and closed-loop global concurrency. Exact details remain in campaign manifests.'
    selected=compact(data)
    replacements={
      '__REPORT_DATA_JSON__':json.dumps(selected,separators=(',',':')),'__AXIS_TICKS__':json.dumps(axis['major_ticks']),'__AXIS_MAX__':str(maximum),'__AXIS_MAX_TEXT__':str(maximum),
      '__CEILING_JS__':ceiling_js,'__CEILING_CALLOUT__':callout,'__REPORT_TITLE__':h(config['report']['title']),'__REPORT_SUBTITLE__':h(config['report'].get('subtitle') or ''),'__STATISTIC_TEXT__':h(statistic_text),'__PROVENANCE_NOTES__':provenance_notes,'__CAMPAIGN_DATE__':h(config['report'].get('campaign_date') or 'campaign record'),
      '__MODEL_DISPLAY__':h(config['model']['display_name']),'__HOST__':h(hardware['host']),'__TOPOLOGY_SHORT__':h(short_topology),'__GPU_SUMMARY__':h(f'{hardware["gpu_count"]}× {hardware["gpu_model"]}'),
      '__RUNS__':number(data['source_counts']['runs']),'__REQUESTS__':number(data['source_counts']['requests']),'__ERRORS__':number(data['source_counts']['errors']),
      '__DECODE__':number(point_value(decode,'throughput')),'__DECODE_C__':str(decode['concurrency']),'__PREFILL__':number(point_value(prefill,'throughput')),'__PREFILL_C__':str(prefill['concurrency']),
      '__POWER__':number(point_value(decode,'gpu_board_power')),'__TEMP__':number(point_value(decode,'gpu_temperature'),1),'__TOPOLOGY_DIAGRAM__':h(diagram),'__METHOD_TEXT__':h(method),
      '__REVISION_SHORT__':h(config['model']['revision'][:12]+'…'),'__TOPOLOGY_DISPLAY__':h(dep['topology_display']),'__KV_DTYPE__':h(dep.get('kv_cache_dtype') or 'unavailable'),'__SPECULATION__':h(dep.get('speculative_decoding') or 'unavailable'),
      '__MAX_MODEL_LEN__':number(dep.get('max_model_len')),'__SEQS_PER_REPLICA__':number(dep.get('max_num_seqs_per_replica')),'__SEQUENCE_CEILING__':number(ceiling),'__BATCHED_TOKENS__':number(dep.get('max_num_batched_tokens_per_replica')),
      '__CPU_AFFINITY__':h(dep.get('cpu_numa_affinity') or 'unavailable'),'__SOURCE_PATH__':h(config['source']['campaign_path']),'__POINTS__':str(len(axis['measured_concurrency'])),'__FABRIC_SECTION__':fabric_section(data)
    }
    rendered=a.template.read_text()
    for key,value in replacements.items():rendered=rendered.replace(key,value)
    leftovers=sorted({x for x in rendered.split() if x.startswith('__') and x.endswith('__')})
    if '__' in rendered and leftovers:raise SystemExit(f'unresolved template placeholders: {leftovers}')
    report=out/config['report']['output_filename'];report.write_text(rendered)
    def copy_if_needed(source, destination):
        if source.resolve() != destination.resolve(): shutil.copy2(source,destination)
    copy_if_needed(a.config,out/'report-config.json');copy_if_needed(a.data,out/'normalized-report-data.json');copy_if_needed(ROOT/'harness/7-report-and-feedback/REPORT_SPEC.md',out/'REPORT_SPEC.md')
    runs_csv=a.runs_csv or a.data.parent/'campaign-summary-runs.csv'
    aggregate_csv=a.aggregate_csv or a.data.parent/'campaign-summary-aggregate.csv'
    if not runs_csv.is_file() or not aggregate_csv.is_file():
        raise SystemExit('renderer requires campaign-summary-runs.csv and campaign-summary-aggregate.csv; pass --runs-csv/--aggregate-csv or place them beside normalized data')
    copy_if_needed(runs_csv,out/'campaign-summary-runs.csv');copy_if_needed(aggregate_csv,out/'campaign-summary-aggregate.csv')
    (out/'generator-version.txt').write_text(f"renderer_path {Path(__file__).resolve()}\ntemplate_path {a.template.resolve()}\ngenerated_utc {datetime.now(timezone.utc).isoformat()}\n")
    files=[report,out/'report-config.json',out/'normalized-report-data.json',
           out/'campaign-summary-runs.csv',out/'campaign-summary-aggregate.csv',
           out/'REPORT_SPEC.md',out/'generator-version.txt']
    missing=[x.name for x in files if not x.is_file()]
    if missing: raise SystemExit(f"refusing incomplete report bundle; missing: {missing}")
    print(report)
if __name__=='__main__':main()
