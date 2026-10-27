#!/usr/bin/env python3
"""Normalize protocol campaigns into the comparable-report data contract.

Canonical campaigns are manifest-driven. The adapter enumerates
``campaign-manifest.json:runs`` (including imported absolute manifests), follows
each run manifest's artifact references, and reads the canonical ``measured/``
and ``telemetry/`` trees. A legacy layout is supported only when explicitly
requested or when no canonical run list exists.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

APP = {
    "input_tps": ("input_token_throughput", "avg", "input tokens/s"),
    "decode_tps": ("output_token_throughput", "avg", "output tokens/s"),
    "per_user_tps": ("output_token_throughput_per_user", "avg", "output tokens/s/user"),
    "prefill_per_user_tps": ("prefill_throughput_per_user", "avg", "input tokens/s/user"),
    "ttft_p50": ("time_to_first_token", "p50", "ms"),
    "ttft_p95": ("time_to_first_token", "p95", "ms"),
    "ttft_p99": ("time_to_first_token", "p99", "ms"),
    "itl_average": ("inter_token_latency", "avg", "ms"),
    "itl_p95": ("inter_token_latency", "p95", "ms"),
    "e2e_p50": ("request_latency", "p50", "ms"),
    "e2e_p95": ("request_latency", "p95", "ms"),
}
# Legacy VictoriaMetrics summary mappings. Canonical campaigns can derive
# primary host/GPU metrics from telemetry/{host,gpu}.csv without a summary.
VM = {
    "host_cpu_busy": ("node_cpu_busy_ratio", 100, "%"),
    "cpu_user": ("node_cpu_user_ratio", 100, "%"),
    "cpu_system": ("node_cpu_system_ratio", 100, "%"),
    "cpu_iowait": ("node_cpu_iowait_ratio", 100, "%"),
    "host_load1": ("node_load1", 1, "load"),
    "host_ram_used": ("node_memory_used_bytes", 1 / 2**30, "GiB"),
    "host_ram_available": ("node_memory_available_bytes", 1 / 2**30, "GiB"),
    "swap_used": ("node_swap_used_bytes", 1 / 2**30, "GiB"),
    "gpu_utilization": ("gpu_utilization", 1, "%"),
    "gpu_memory_copy": ("gpu_memory_copy_utilization", 1, "%"),
    "gpu_temperature": ("gpu_temperature", 1, "°C"),
    "gpu_sm_clock": ("gpu_sm_clock", 1, "MHz"),
    "gpu_memory_clock": ("gpu_memory_clock", 1, "MHz"),
    "kv_cache_usage": ("vllm_kv_cache_usage", 100, "%"),
    "disk_write": ("disk_write_bytes_rate", 1 / 2**20, "MiB/s"),
}
SUM_VM = {
    "running_requests": ("vllm_running_requests", 1, "requests"),
    "waiting_requests": ("vllm_waiting_requests", 1, "requests"),
    "preemptions": ("vllm_preemptions_rate", 1, "preemptions/s"),
    "server_prompt_rate": ("vllm_prompt_tokens_rate", 1, "input tokens/s"),
    "server_decode_rate": ("vllm_generation_tokens_rate", 1, "output tokens/s"),
    "container_cpu": ("container_cpu_rate", 1, "cores"),
    "container_memory": ("container_memory", 1 / 2**30, "GiB"),
    "container_tx": ("container_network_tx_rate", 1 / 2**20, "MiB/s"),
}
UNITS = (
    {name: unit for name, (_, _, unit) in APP.items()}
    | {name: unit for name, (_, _, unit) in VM.items()}
    | {name: unit for name, (_, _, unit) in SUM_VM.items()}
    | {
        "gpu_vram_used": "GiB", "gpu_board_power": "W",
        "process_rss": "GiB", "process_pss": "GiB", "process_private": "GiB",
        "process_shared": "GiB", "process_swap": "GiB",
        "joules_per_input_token": "J/input token",
        "joules_per_output_token": "J/output token",
        "speculative_acceptance": "%", "mamba_usage": "%",
        "haproxy_frontend_ingress": "MiB/s", "haproxy_frontend_egress": "MiB/s",
        "haproxy_backend_ingress": "MiB/s", "haproxy_backend_egress": "MiB/s",
        "haproxy_frontend_ingress_total": "MiB", "haproxy_frontend_egress_total": "MiB",
        "haproxy_backend_ingress_total": "MiB", "haproxy_backend_egress_total": "MiB",
        "haproxy_ingress_per_request": "KiB/request", "haproxy_egress_per_request": "KiB/request",
        "haproxy_queue": "requests", "haproxy_retries": "retries", "haproxy_errors": "errors",
        "haproxy_backend_imbalance": "%",
        "pcie_rx": "GB/s", "pcie_tx": "GB/s", "pcie_replay_delta": "replays",
    }
)


def finite(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def scalar(document, name, key="avg"):
    value = document.get(name, {})
    return finite(value.get(key) if isinstance(value, dict) else None)


def series_sum(document, name):
    values = [finite(x.get("avg")) for x in document.get(name, {}).get("series", [])]
    values = [x for x in values if x is not None]
    return sum(values) if values else None


def server_metric_sum(document, name, statistic):
    values=[]
    for series in document.get("metrics",{}).get(name,{}).get("series",[]):
        value=finite(series.get("stats",{}).get(statistic))
        if value is not None:values.append(value)
    return sum(values) if values else None


def server_metric_mean(document, name, statistic):
    values=[]
    for series in document.get("metrics",{}).get(name,{}).get("series",[]):
        value=finite(series.get("stats",{}).get(statistic))
        if value is not None:values.append(value)
    return st.fmean(values) if values else None


def sglang_server_metrics(document):
    """Normalize AIPerf-exported SGLang metrics from one metrics endpoint."""
    running=server_metric_sum(document,"sglang:num_running_reqs","avg")
    waiting=server_metric_sum(document,"sglang:num_queue_reqs","avg")
    kv=server_metric_mean(document,"sglang:token_usage","avg")
    if kv is None:
        used=server_metric_sum(document,"sglang:kv_used_tokens","avg")
        available=server_metric_sum(document,"sglang:kv_available_tokens","avg")
        kv=used/(used+available) if used is not None and available is not None and used+available else None
    mamba=server_metric_mean(document,"sglang:mamba_usage","avg")
    spec=server_metric_mean(document,"sglang:spec_accept_rate","avg")
    return {
        "running_requests":running,"waiting_requests":waiting,
        "kv_cache_usage":100*kv if kv is not None else None,
        "mamba_usage":100*mamba if mamba is not None else None,
        "speculative_acceptance":100*spec if spec is not None else None,
        "server_prompt_rate":server_metric_sum(document,"sglang:prompt_tokens","rate"),
        "server_decode_rate":server_metric_sum(document,"sglang:generation_tokens","rate"),
    }


PROM_LINE=re.compile(r'^([A-Za-z_:][A-Za-z0-9_:]*)(?:\{([^}]*)\})?\s+([^ ]+)$')
LABEL=re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="((?:\\.|[^"])*)"')


def prometheus_samples(text):
    rows=[]
    for raw in text.splitlines():
        if not raw or raw.startswith("#"):continue
        match=PROM_LINE.match(raw.strip())
        if not match:continue
        try:value=float(match.group(3))
        except ValueError:continue
        if not math.isfinite(value):continue
        rows.append((match.group(1),dict(LABEL.findall(match.group(2) or "")),value))
    return rows


def promjsonl(path: Path):
    rows=[]
    if not path.is_file():return rows
    with path.open() as stream:
        for raw in stream:
            try:
                item=json.loads(raw);rows.append((item.get("timestamp_utc"),prometheus_samples(item.get("prometheus_text", ""))))
            except (json.JSONDecodeError,TypeError):continue
    return rows


def metric_values(samples,name,label_filter=None):
    label_filter=label_filter or {}
    return [value for metric,labels,value in samples if metric==name and all(labels.get(k)==v for k,v in label_filter.items())]


def multi_backend_telemetry(telemetry: Path):
    """Aggregate timestamped SGLang Prometheus snapshots across backend ports."""
    snapshots=promjsonl(telemetry/"backends.promjsonl")
    if not snapshots:return {}
    gauges={
      "running_requests":("sglang:num_running_reqs","sum",1),
      "waiting_requests":("sglang:num_queue_reqs","sum",1),
      "kv_cache_usage":("sglang:token_usage","mean",100),
      "mamba_usage":("sglang:mamba_usage","mean",100),
      "speculative_acceptance":("sglang:spec_accept_rate","mean",100),
    }
    # Fan-out collectors emit one JSON row per backend at the same timestamp.
    # Group first so request gauges and counters are summed across replicas,
    # while utilization ratios are averaged across replicas rather than ranks.
    grouped={}
    for stamp,sample in snapshots:grouped.setdefault(stamp,[]).extend(sample)
    ordered=sorted(grouped.items())
    out={}
    for output,(metric,mode,multiplier) in gauges.items():
        values=[]
        for _,sample in ordered:
            found=metric_values(sample,metric)
            if found:values.append((sum(found) if mode=="sum" else st.fmean(found))*multiplier)
        if values:out[output]=st.fmean(values)
    for output,metric in (("server_prompt_rate","sglang:prompt_tokens_total"),("server_decode_rate","sglang:generation_tokens_total")):
        totals=[]
        for stamp,sample in ordered:
            values=metric_values(sample,metric)
            if stamp and values:totals.append((datetime.fromisoformat(stamp.replace("Z","+00:00")).timestamp(),sum(values)))
        if len(totals)>1:
            elapsed=totals[-1][0]-totals[0][0];delta=totals[-1][1]-totals[0][1]
            if elapsed>0 and delta>=0:out[output]=delta/elapsed
    return out


def haproxy_telemetry(telemetry: Path, successful_requests):
    """Derive exact-window directional HAProxy counters and backend balance."""
    snapshots=promjsonl(telemetry/"haproxy.promjsonl")
    if len(snapshots)<2:return {}
    start_t,start=snapshots[0];end_t,end=snapshots[-1]
    elapsed=datetime.fromisoformat(end_t.replace("Z","+00:00")).timestamp()-datetime.fromisoformat(start_t.replace("Z","+00:00")).timestamp()
    if elapsed<=0:return {}
    def total(sample,name,labels):return sum(metric_values(sample,name,labels))
    specs={
      "haproxy_frontend_ingress":("haproxy_frontend_bytes_in_total",{}),
      "haproxy_frontend_egress":("haproxy_frontend_bytes_out_total",{}),
      "haproxy_backend_ingress":("haproxy_backend_bytes_in_total",{}),
      "haproxy_backend_egress":("haproxy_backend_bytes_out_total",{}),
    }
    out={};deltas={}
    for output,(metric,labels) in specs.items():
        delta=total(end,metric,labels)-total(start,metric,labels)
        if delta>=0:deltas[output]=delta;out[output]=delta/elapsed/2**20;out[output+"_total"]=delta/2**20
    if successful_requests:
        if "haproxy_frontend_ingress" in deltas:out["haproxy_ingress_per_request"]=deltas["haproxy_frontend_ingress"]/successful_requests/1024
        if "haproxy_frontend_egress" in deltas:out["haproxy_egress_per_request"]=deltas["haproxy_frontend_egress"]/successful_requests/1024
    queue=[sum(metric_values(sample,"haproxy_backend_current_queue")) for _,sample in snapshots]
    if queue:out["haproxy_queue"]=st.fmean(queue)
    retry=total(end,"haproxy_backend_retry_warnings_total",{})-total(start,"haproxy_backend_retry_warnings_total",{})
    errors=sum(total(end,name,{})-total(start,name,{}) for name in ("haproxy_frontend_request_errors_total","haproxy_backend_connection_errors_total","haproxy_backend_response_errors_total"))
    if retry>=0:out["haproxy_retries"]=retry
    if errors>=0:out["haproxy_errors"]=errors
    names=sorted({labels.get("server") for metric,labels,_ in end if metric=="haproxy_server_sessions_total" and labels.get("server")})
    backend=[]
    for name in names:
        labels={"server":name};delta=total(end,"haproxy_server_sessions_total",labels)-total(start,"haproxy_server_sessions_total",labels)
        if delta>=0:backend.append(delta)
    if backend and sum(backend):out["haproxy_backend_imbalance"]=(max(backend)-min(backend))/(sum(backend)/len(backend))*100
    return out


def resolve(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def run_identity(manifest, record):
    workload = manifest.get("workload", {})
    profile = record.get("profile", workload.get("profile", manifest.get("profile")))
    concurrency = record.get("concurrency", workload.get("global_concurrency", manifest.get("concurrency")))
    repetition = record.get("repetition", workload.get("repetition", manifest.get("repetition")))
    if profile is None or concurrency is None or repetition is None:
        raise ValueError(f"incomplete run identity: {manifest.get('run_id')}")
    return str(profile), int(concurrency), int(repetition)


def canonical_records(campaign: Path):
    manifest_path = campaign / "campaign-manifest.json"
    campaign_manifest = json.loads(manifest_path.read_text())
    records = campaign_manifest.get("runs")
    if not isinstance(records, list):
        raise ValueError("canonical campaign-manifest.json has no runs array")
    for record in records:
        if record.get("status") != "complete":
            continue
        manifest_path = resolve(campaign, record.get("manifest"))
        if manifest_path is not None and manifest_path.is_dir():
            manifest_path = manifest_path / "manifest.json"
        if manifest_path is None or not manifest_path.is_file():
            raise ValueError(f"run manifest is missing: {record.get('manifest')}")
        yield record, manifest_path, json.loads(manifest_path.read_text())


def legacy_records(campaign: Path):
    for manifest_path in sorted(campaign.glob("runs/*/c*/run-r*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("status") == "complete":
            yield {}, manifest_path, manifest


def artifact_paths(manifest_path: Path, manifest: dict, layout: str):
    artifacts = manifest.get("artifacts", {})
    result = resolve(manifest_path.parent, artifacts.get("result"))
    measured = resolve(manifest_path.parent, artifacts.get("measured_dir"))
    telemetry = resolve(manifest_path.parent, artifacts.get("telemetry_dir"))
    if result is None:
        if layout == "canonical":
            measured = measured or manifest_path.parent / "measured"
            result = measured / "profile_export_aiperf.json"
        else:
            result = manifest_path.parent / "profile_export_aiperf.json"
    measured = measured or result.parent
    if telemetry is None:
        telemetry = manifest_path.parent / ("telemetry" if layout == "canonical" else "victoriametrics")
    vm_candidates = [
        telemetry / "victoriametrics" / "summary.json",
        telemetry / "summary.json",
        manifest_path.parent / "victoriametrics" / "summary.json",
    ]
    vm_summary = next((x for x in vm_candidates if x.is_file()), None)
    return result, measured, telemetry, vm_summary


def victoriametrics_pcie(telemetry: Path):
    directory=telemetry/"victoriametrics"; manifest_path=directory/"manifest.json"
    if not manifest_path.is_file():return {}
    manifest=json.loads(manifest_path.read_text());out={}
    for record in manifest.get("queries",[]):
        query=record.get("query","");path=directory/record.get("file","")
        if not path.is_file():continue
        result=json.loads(path.read_text()).get("data",{}).get("result",[])
        series=[]
        for item in result:
            values=[finite(float(pair[1])) for pair in item.get("values",[])];values=[x for x in values if x is not None]
            if values:series.append(values)
        if "DCGM_FI_PROF_PCIE_RX_BYTES" in query:
            out["pcie_rx"]=sum(st.fmean(values) for values in series)/1e9 if series else None
        elif "DCGM_FI_PROF_PCIE_TX_BYTES" in query:
            out["pcie_tx"]=sum(st.fmean(values) for values in series)/1e9 if series else None
        elif "DCGM_FI_DEV_PCIE_REPLAY_COUNTER" in query:
            out["pcie_replay_delta"]=sum(max(values)-min(values) for values in series) if series else None
    return out


def host_fabric_summary(path: str | None):
    if not path:return None
    root=Path(path).expanduser().resolve();summary_path=root/"qualification-summary.json";qualification_path=root/"fabric-qualification.json"
    if not summary_path.is_file():raise ValueError(f"fabric qualification summary is missing: {summary_path}")
    summary=json.loads(summary_path.read_text());qualification=json.loads(qualification_path.read_text()) if qualification_path.is_file() else {}
    comparisons=summary.get("nccl",{}).get("comparisons",[])
    all_reduce=[x for x in comparisons if x.get("collective")=="all_reduce_perf"]
    p2p=summary.get("p2p",[])
    p2p_detail_path=root/"p2p/parsed/summary.json"
    p2p_detail=json.loads(p2p_detail_path.read_text()) if p2p_detail_path.is_file() else {}
    p2p_rows=[x for x in p2p_detail.get("rows",[]) if x.get("metric")=="bandwidth" and x.get("p2p_enabled") is True]
    def p2p_row(direction):
        return next((x for x in p2p if x.get("metric")=="bandwidth" and x.get("direction")==direction and x.get("p2p_enabled") is True),None)
    return {
        "source":str(root),
        "nccl_cases":summary.get("nccl",{}).get("cases"),
        "nccl_wrong_values":summary.get("nccl",{}).get("wrong_total"),
        "same_numa_all_reduce_busbw_gbps":{"minimum":min((x["local_busbw_gbps"] for x in all_reduce),default=None),"maximum":max((x["local_busbw_gbps"] for x in all_reduce),default=None)},
        "cross_numa_all_reduce_busbw_gbps":{"minimum":min((x["cross_numa_busbw_gbps"] for x in all_reduce),default=None),"maximum":max((x["cross_numa_busbw_gbps"] for x in all_reduce),default=None)},
        "cross_numa_penalty_pct":{"minimum":min((x["cross_numa_penalty_pct"] for x in all_reduce),default=None),"maximum":max((x["cross_numa_penalty_pct"] for x in all_reduce),default=None)},
        "remote_cpu_penalty_pct":{"minimum":min((x["remote_cpu_penalty_pct"] for x in all_reduce),default=None),"maximum":max((x["remote_cpu_penalty_pct"] for x in all_reduce),default=None)},
        "nccl_comparisons":comparisons,
        "p2p_unidirectional_gbps":p2p_row("unidirectional"),
        "p2p_bidirectional_gbps":p2p_row("bidirectional"),
        "p2p_bandwidth_matrix":p2p_rows,
        "link_idle":qualification.get("link_state",{}).get("idle"),
        "link_under_load":qualification.get("link_state",{}).get("sustained_load"),
        "dcgm":summary.get("dcgm"),"upi":summary.get("upi"),"limitations":summary.get("limitations",[]),
    }


def numeric_rows(path: Path | None):
    if path is None or not path.is_file():
        return []
    rows = []
    with path.open(newline="") as stream:
        reader=csv.reader(stream); header=next(reader,None)
        if not header:return []
        for values in reader:
            # GNU date --iso-8601=ns uses a comma as its fractional-second
            # separator. Collectors write that timestamp as the first CSV field
            # without quoting, so join the first two cells before mapping columns.
            if len(values)==len(header)+1 and header[0]=="timestamp_utc":
                values=[values[0]+","+values[1],*values[2:]]
            if len(values)!=len(header):
                raise ValueError(f"malformed telemetry CSV row in {path}: expected {len(header)} fields, got {len(values)}")
            row=dict(zip(header,values));clean={}
            for key, value in row.items():
                try: clean[key] = float(value.strip())
                except (ValueError, TypeError, AttributeError): clean[key] = value.strip() if isinstance(value,str) else value
            rows.append(clean)
    return rows


def delta_ratio(first, last, numerator_fields, denominator_fields):
    numerator = sum((finite(last.get(x)) or 0) - (finite(first.get(x)) or 0) for x in numerator_fields)
    denominator = numerator + sum((finite(last.get(x)) or 0) - (finite(first.get(x)) or 0) for x in denominator_fields)
    return 100 * numerator / denominator if denominator > 0 else None


def local_telemetry(telemetry: Path, gpu_count: int):
    gpu_rows = numeric_rows(telemetry / "gpu.csv")
    host_rows = numeric_rows(telemetry / "host.csv")
    out = {}
    def average(rows, key):
        values = [finite(x.get(key)) for x in rows]; values = [x for x in values if x is not None]
        return st.fmean(values) if values else None
    if gpu_rows:
        aliases = {
            "gpu_utilization": "gpu_util_pct", "gpu_memory_copy": "memory_util_pct",
            "gpu_temperature": "temperature_c", "gpu_sm_clock": "sm_clock_mhz",
            "gpu_memory_clock": "memory_clock_mhz",
        }
        for name, key in aliases.items(): out[name] = average(gpu_rows, key)
        used = average(gpu_rows, "memory_used_mib")
        power = average(gpu_rows, "power_w")
        out["gpu_vram_used"] = used * gpu_count / 1024 if used is not None else None
        out["gpu_board_power"] = power * gpu_count if power is not None else None
    if host_rows:
        first, last = host_rows[0], host_rows[-1]
        out["host_cpu_busy"] = delta_ratio(first, last,
            ["cpu_user", "cpu_nice", "cpu_system", "cpu_iowait", "cpu_irq", "cpu_softirq", "cpu_steal"],
            ["cpu_idle"])
        out["cpu_user"] = delta_ratio(first, last, ["cpu_user", "cpu_nice"],
            ["cpu_system", "cpu_idle", "cpu_iowait", "cpu_irq", "cpu_softirq", "cpu_steal"])
        out["cpu_system"] = delta_ratio(first, last, ["cpu_system", "cpu_irq", "cpu_softirq"],
            ["cpu_user", "cpu_nice", "cpu_idle", "cpu_iowait", "cpu_steal"])
        out["cpu_iowait"] = delta_ratio(first, last, ["cpu_iowait"],
            ["cpu_user", "cpu_nice", "cpu_system", "cpu_idle", "cpu_irq", "cpu_softirq", "cpu_steal"])
        out["host_load1"] = average(host_rows, "load1")
        total, available = average(host_rows, "mem_total_kib"), average(host_rows, "mem_available_kib")
        out["host_ram_used"] = (total - available) / 2**20 if total is not None and available is not None else None
        out["host_ram_available"] = available / 2**20 if available is not None else None
        swap_total, swap_free = average(host_rows, "swap_total_kib"), average(host_rows, "swap_free_kib")
        out["swap_used"] = (swap_total - swap_free) / 2**20 if swap_total is not None and swap_free is not None else None
    return out


def process_memory_telemetry(telemetry: Path):
    rows = numeric_rows(telemetry / "process-memory.csv")
    if not rows:
        return {}
    by_timestamp = {}
    for row in rows:
        stamp = row.get("timestamp_utc")
        if not isinstance(stamp, str):
            continue
        # A matched PID with unreadable smaps_rollup has blank memory fields.
        # Skip it rather than manufacturing a zero-memory observation.
        if not any(finite(row.get(key)) is not None for key in ("rss_kib", "pss_kib", "private_clean_kib", "private_dirty_kib", "shared_clean_kib", "shared_dirty_kib", "swap_kib")):
            continue
        totals = by_timestamp.setdefault(stamp, {key: 0.0 for key in ("rss_kib", "pss_kib", "private_kib", "shared_kib", "swap_kib")})
        def value(key):
            item = finite(row.get(key))
            return item if item is not None else 0.0
        totals["rss_kib"] += value("rss_kib")
        totals["pss_kib"] += value("pss_kib")
        totals["private_kib"] += value("private_clean_kib") + value("private_dirty_kib")
        totals["shared_kib"] += value("shared_clean_kib") + value("shared_dirty_kib")
        totals["swap_kib"] += value("swap_kib")
    if not by_timestamp:
        return {}
    return {
        "process_rss": st.fmean(x["rss_kib"] for x in by_timestamp.values()) / 2**20,
        "process_pss": st.fmean(x["pss_kib"] for x in by_timestamp.values()) / 2**20,
        "process_private": st.fmean(x["private_kib"] for x in by_timestamp.values()) / 2**20,
        "process_shared": st.fmean(x["shared_kib"] for x in by_timestamp.values()) / 2**20,
        "process_swap": st.fmean(x["swap_kib"] for x in by_timestamp.values()) / 2**20,
    }


def aggregate(values, unit):
    values = [x for x in values if isinstance(x, (int, float)) and math.isfinite(x)]
    if not values:
        return None
    return {"median": st.median(values), "minimum": min(values), "maximum": max(values),
            "mean": st.fmean(values), "standard_deviation": st.stdev(values) if len(values) > 1 else 0,
            "n": len(values), "unit": unit}


def baseline_power(campaign: Path, gpu_count: int):
    values = []
    for phase in ("pre", "post"):
        rows = numeric_rows(campaign / "idle" / phase / "gpu.csv")
        samples = [finite(x.get("power_w")) for x in rows]
        samples = [x for x in samples if x is not None]
        if samples: values.append(st.fmean(samples) * gpu_count)
    return st.fmean(values) if values else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--layout", choices=("auto", "canonical", "legacy"), default="auto")
    args = parser.parse_args()
    campaign = args.campaign.resolve(); config = json.loads(args.config.read_text())
    out = (args.output or campaign / "report"); out.mkdir(parents=True, exist_ok=True)
    campaign_manifest = json.loads((campaign / "campaign-manifest.json").read_text())
    layout = args.layout
    if layout == "auto": layout = "canonical" if isinstance(campaign_manifest.get("runs"), list) else "legacy"
    records = list(canonical_records(campaign) if layout == "canonical" else legacy_records(campaign))
    runs, exclusions = [], []
    for record, manifest_path, manifest in records:
        try:
            result, measured, telemetry, vm_path = artifact_paths(manifest_path, manifest, layout)
            if not result.is_file(): raise ValueError(f"result is missing: {result}")
            app = json.loads(result.read_text()); vm = json.loads(vm_path.read_text()) if vm_path else {}
            server_path=measured/"server_metrics_export.json"
            server=json.loads(server_path.read_text()) if server_path.is_file() else {}
            profile, concurrency, repetition = run_identity(manifest, record)
            row = {"source_id": profile, "concurrency": concurrency, "repetition": repetition,
                   "run_id": manifest.get("run_id", manifest_path.parent.name),
                   "imported": bool(record.get("imported", False)), "manifest": str(manifest_path),
                   "requests": scalar(app, "request_count"), "errors": len(app.get("error_summary") or [])}
            for name, (source, key, _) in APP.items(): row[name] = scalar(app, source, key)
            for name, (source, multiplier, _) in VM.items():
                value = scalar(vm, source); row[name] = value * multiplier if value is not None else None
            for name, (source, multiplier, _) in SUM_VM.items():
                value = series_sum(vm, source); row[name] = value * multiplier if value is not None else None
            server_values={
                "running_requests":server_metric_sum(server,"vllm:num_requests_running","avg"),
                "waiting_requests":server_metric_sum(server,"vllm:num_requests_waiting","avg"),
                "kv_cache_usage":server_metric_sum(server,"vllm:kv_cache_usage_perc","avg"),
                "preemptions":server_metric_sum(server,"vllm:num_preemptions","rate"),
                "server_prompt_rate":server_metric_sum(server,"vllm:prompt_tokens","rate"),
                "server_decode_rate":server_metric_sum(server,"vllm:generation_tokens","rate"),
            }
            if server_values["kv_cache_usage"] is not None:server_values["kv_cache_usage"]*=100
            accepted=server_metric_sum(server,"vllm:spec_decode_num_accepted_tokens","rate")
            drafted=server_metric_sum(server,"vllm:spec_decode_num_draft_tokens","rate")
            server_values["speculative_acceptance"]=100*accepted/drafted if accepted is not None and drafted else None
            # Runtime-aware fallback. Prefer whole-deployment backend snapshots;
            # then use the AIPerf-exported SGLang endpoint when snapshots are absent.
            sglang_values=sglang_server_metrics(server)
            backend_values=multi_backend_telemetry(telemetry)
            for key,value in sglang_values.items():
                if server_values.get(key) is None and value is not None:server_values[key]=value
            server_values.update({key:value for key,value in backend_values.items() if value is not None})
            row.update({key:value for key,value in server_values.items() if value is not None})
            successful_requests=scalar(app,"request_count")
            row.update({key:value for key,value in haproxy_telemetry(telemetry,successful_requests).items() if value is not None})
            # Canonical local telemetry is authoritative when available.
            row.update({k:v for k,v in local_telemetry(telemetry, config["hardware"]["gpu_count"]).items() if v is not None})
            row.update({k:v for k,v in process_memory_telemetry(telemetry).items() if v is not None})
            row.update({k:v for k,v in victoriametrics_pcie(telemetry).items() if v is not None})
            gpu_count = config["hardware"]["gpu_count"]
            value = scalar(vm, "gpu_memory_used")
            if row.get("gpu_vram_used") is None and value is not None: row["gpu_vram_used"] = value * gpu_count / 1024
            value = scalar(vm, "gpu_power")
            if row.get("gpu_board_power") is None and value is not None: row["gpu_board_power"] = value * gpu_count
            duration = scalar(app, "benchmark_duration"); row["duration_s"] = duration
            total_in, total_out = scalar(app, "total_isl"), scalar(app, "total_osl")
            row["joules_per_input_token"] = row.get("gpu_board_power") * duration / total_in if row.get("gpu_board_power") and duration and total_in else None
            row["joules_per_output_token"] = row.get("gpu_board_power") * duration / total_out if row.get("gpu_board_power") and duration and total_out else None
            draft, accepted = series_sum(vm, "vllm_mtp_draft_rate"), series_sum(vm, "vllm_mtp_accepted_rate")
            if draft:
                row["speculative_acceptance"] = 100 * accepted / draft
            runs.append(row)
        except Exception as error:
            exclusions.append({"run_id": record.get("run_id", manifest.get("run_id", manifest_path.parent.name)), "reason": str(error)})
    expected_complete = sum(1 for x in campaign_manifest.get("runs", []) if x.get("status") == "complete") if layout == "canonical" else len(records)
    if exclusions: raise SystemExit("refusing partial report; run exclusions: " + json.dumps(exclusions, indent=2))
    if len(runs) != expected_complete: raise SystemExit(f"manifest lists {expected_complete} complete runs, adapter loaded {len(runs)}")
    if not runs: raise SystemExit("no complete runs found")
    sources = sorted({x["source_id"] for x in runs}); concurrencies = sorted({x["concurrency"] for x in runs})
    grouped = {(source,c):[x for x in runs if x["source_id"]==source and x["concurrency"]==c] for source in sources for c in concurrencies}
    def peak(source, metric):
        values=[st.median([x[metric] for x in group if x.get(metric) is not None]) for (s,_),group in grouped.items() if s==source and any(x.get(metric) is not None for x in group)]
        return max(values) if values else float("-inf")
    decode_source=max(sources,key=lambda source:peak(source,"decode_tps"));prefill_source=max(sources,key=lambda source:peak(source,"input_tps"))
    def make_series(kind, source):
        points=[]
        for concurrency in concurrencies:
            group=grouped[(source,concurrency)];point={"concurrency":concurrency}
            mapping={"throughput":"decode_tps" if kind=="decode" else "input_tps","per_user_throughput":"per_user_tps" if kind=="decode" else "prefill_per_user_tps","ttft_p50":"ttft_p50","ttft_p95":"ttft_p95","itl_average":"itl_average","itl_p95":"itl_p95","gpu_board_power":"gpu_board_power","joules_per_token":"joules_per_output_token" if kind=="decode" else "joules_per_input_token"}
            for output, metric in mapping.items(): point[output]=aggregate([x.get(metric) for x in group],UNITS[metric])
            for metric in ["host_cpu_busy","cpu_user","cpu_system","cpu_iowait","host_load1","host_ram_used","host_ram_available","swap_used","gpu_utilization","gpu_memory_copy","gpu_temperature","gpu_sm_clock","gpu_memory_clock","gpu_vram_used","running_requests","waiting_requests","kv_cache_usage","mamba_usage","speculative_acceptance","preemptions","server_prompt_rate","server_decode_rate","container_cpu","container_memory","container_tx","disk_write","process_rss","process_pss","process_private","process_shared","process_swap","haproxy_frontend_ingress","haproxy_frontend_egress","haproxy_backend_ingress","haproxy_backend_egress","haproxy_frontend_ingress_total","haproxy_frontend_egress_total","haproxy_backend_ingress_total","haproxy_backend_egress_total","haproxy_ingress_per_request","haproxy_egress_per_request","haproxy_queue","haproxy_retries","haproxy_errors","haproxy_backend_imbalance","pcie_rx","pcie_tx","pcie_replay_delta","e2e_p50","e2e_p95"]:
                point[metric]=aggregate([x.get(metric) for x in group],UNITS.get(metric))
            points.append(point)
        return {"source_id":source,"points":points}
    baseline=baseline_power(campaign,config["hardware"]["gpu_count"])
    data={"schema_version":1,"source_campaign":str(campaign),"generated_at":datetime.now(timezone.utc).isoformat(),"source_counts":{"runs":len(runs),"requests":sum(x["requests"] or 0 for x in runs),"errors":sum(x["errors"] for x in runs),"excluded_runs":0},"selection":{"policy":"maximum-median-useful-tps","decode_source_id":decode_source,"prefill_source_id":prefill_source},"idle_baseline":{"aggregate_gpu_board_power_w":baseline,"source":str(campaign/"idle")},"series":{"decode":make_series("decode",decode_source),"prefill":make_series("prefill",prefill_source)},"host_fabric":host_fabric_summary(config.get("fabric_qualification_path")),"metric_availability":{},"exclusions":[]}
    metrics={key for series in data["series"].values() for point in series["points"] for key in point if key!="concurrency"}
    for metric in metrics:data["metric_availability"][metric]="available" if any(point.get(metric) is not None for series in data["series"].values() for point in series["points"]) else "unavailable"
    (out/"normalized-report-data.json").write_text(json.dumps(data,indent=2)+"\n");(out/"report-config.json").write_text(json.dumps(config,indent=2)+"\n")
    run_fields=sorted(set().union(*(x.keys() for x in runs)))
    with (out/"campaign-summary-runs.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=run_fields);writer.writeheader();writer.writerows(runs)
    flat=[]
    for kind,series in data["series"].items():
        for point in series["points"]:
            row={"kind":kind,"source_id":series["source_id"],"concurrency":point["concurrency"]}
            for metric,statistic in point.items():
                if metric=="concurrency" or statistic is None:continue
                for statistic_name,value in statistic.items():row[f"{metric}_{statistic_name}"]=value
            flat.append(row)
    fields=sorted(set().union(*(x.keys() for x in flat)),key=lambda x:(x not in ("kind","source_id","concurrency"),x))
    with (out/"campaign-summary-aggregate.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(flat)
    print(json.dumps({"layout":layout,"manifest_complete_runs":expected_complete,"loaded_runs":len(runs),"imported_runs":sum(x["imported"] for x in runs),"decode_source":decode_source,"prefill_source":prefill_source,"output":str(out/"normalized-report-data.json")},indent=2))

if __name__ == "__main__":
    main()
