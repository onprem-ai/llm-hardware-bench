---
kind: rule
step: 7
title: Report and feedback rules
absorbs:
  - PROCEDURE.md §14 Required Summary Table, §15 Charts, §17 Reporting Conclusions
  - harness/7-report-and-feedback/RULES.md (workflow, contracts, adapter/renderer responsibilities, scope labels)
---

# Chapter 7 — Report and feedback

Pipeline order, budgets and gates: `PIPELINE.md`. This chapter turns accepted numbers into
reader-facing artifacts **and** feeds what it learns back into the owning chapter. It is
separate from chapter 6 because the two fail differently: chapter 6 fails by accepting bad
data, chapter 7 fails by stating claims no validator checks. On 2026-09-06 the fabricated
comparator was a chapter-7 claim, which is why the claims contract now sits in chapter 6
where a validator can reach it.

## What this chapter produces

`normalized-report-data.json`, the required summary table, charts, the report bundle, and
either a PROCEDURE feedback change or an explicit statement that none was needed.

## Reporting pipeline

### R-07-1 The reporting boundary separates ingestion from presentation

```text
raw campaign artifacts
  -> campaign adapter / analysis
  -> normalized-report-data.json
  + report-config.json
  -> comparable renderer
  -> self-contained HTML report bundle
```

Campaigns differ in directory layout and telemetry shape; the report must not encode those
differences. Raw-layout support belongs in adapters, never in the renderer.

| Contract | Owner |
|---|---|
| reader-facing semantics and structure | `harness/7-report-and-feedback/REPORT_SPEC.md` (this chapter) |
| campaign-specific facts | `harness/7-report-and-feedback/schemas/report-config.schema.json` |
| selected Prefill/Decode series and statistics | `harness/7-report-and-feedback/schemas/normalized-report-data.schema.json` |
| visual baseline | `harness/7-report-and-feedback/code/reference/approved-reference.html` |
| schema + semantic invariants | `harness/7-report-and-feedback/code/validate_report_inputs.py` |

### R-07-2 Adapter responsibilities

Enumerate all complete eligible runs and record exclusions; normalise application and
telemetry units; aggregate each internal source series by concurrency; select Decode and
Prefill independently per the report spec; retain source IDs in provenance while hiding them
in reader-facing copy; attach latency and resource metrics to the selected series; mark
unavailable telemetry as unavailable, never zero; normalise load-balancer frontend/backend
directional byte rates, byte totals, bytes per successful request, queue/retry/error metrics
and backend distribution without conflating them with host/NIC traffic; emit per-run and
aggregate CSV plus normalised JSON.

`harness/7-report-and-feedback/code/adapters/protocol_campaign.py` is the canonical adapter (enumerates
`campaign-manifest.json:runs`, follows each run manifest's explicit result path, reads
`measured/` and `telemetry/`, includes imported absolute manifests); an explicit legacy mode
supports the older GLM/Qwen layout **without changing those immutable campaigns**.

### R-07-3 Renderer responsibilities

`harness/7-report-and-feedback/code/render_report.py` is deterministic for a fixed configuration, normalised input,
template and renderer version. It owns chapter order, labels, colours, chart mechanics,
collapsible diagnostics, responsive layout and offline packaging. It does **not** select
profiles or reinterpret raw telemetry.

### R-07-4 Measurement-scope labels survive into reader copy

Keep AIPerf (client-observed), HAProxy (traffic through the common proxy boundary), host/NIC
collectors (named interfaces) and DCGM (GPU PCIe endpoints) distinct. Do not call HAProxy
traffic physical-NIC utilisation when proxy and backend share a host; do not sum RX and TX
into one bandwidth figure (`R-02-3`, `R-02-8`).

## Required summary table

### R-07-5 One row per topology, profile and concurrency

| Field | Description |
|---|---|
| model | Exact model/revision |
| quantization | Weight and activation format |
| topology | Replicas × GPUs per replica and TP/PP/DCP/EP |
| profile | Decode, prefill, balanced, or long-context |
| concurrency_global | Total client concurrency |
| concurrency_per_replica | Average offered concurrency per replica |
| requests | Measured request count |
| input_tokens_avg | Actual average input tokens |
| output_tokens_avg | Actual average output tokens |
| input_tps | Aggregate input-token throughput |
| generation_tps | Aggregate output-token throughput |
| request_rps | Completed requests/s |
| ttft_p50_ms | Median TTFT |
| ttft_p95_ms | p95 TTFT |
| ttft_p99_ms | p99 TTFT |
| itl_p50_ms | Median ITL |
| itl_p95_ms | p95 ITL |
| e2e_p95_ms | p95 end-to-end latency |
| errors | Error count/rate |
| kv_capacity_tokens | Startup-reported capacity |
| kv_peak_pct | Peak KV utilization |
| kv_free_blocks_min | Minimum free blocks |
| preemptions | Preempted/recomputed requests |
| gpu_util_avg_pct | Average across GPUs |
| gpu_util_minmax_pct | GPU imbalance |
| gpu_mem_peak_gib | Peak per GPU |
| gpu_power_avg_w | Average total/per GPU, clearly labeled |
| cpu_avg_pct | Host CPU utilization |
| ram_peak_gib | Peak host RAM |
| network_rx_tx | Benchmark interval traffic |
| gpu_energy_wh | Integrated/counter-delta energy across deployment GPUs |
| joules_per_output_token | Deployment GPU energy divided by actual output tokens |
| output_tokens_per_watt | Generation TPS divided by aggregate average GPU watts |
| cpu_p95_pct | Host CPU p95 over measured window |
| cpu_seconds_per_request | Container/server CPU seconds divided by completions |
| ram_working_set_gib | Application/container working set, excluding page cache where possible |
| haproxy_rx_tx_bytes | HAProxy counter deltas over measured window |
| replica_request_counts | Request count by backend |
| replica_imbalance_pct | Defined imbalance statistic across backends |
| backend_queue_p95_ms | HAProxy backend queue p95 |
| clock_offset_ms | Maximum absolute client/server/telemetry clock offset |
| notes | Throttling, anomalies, configuration changes |

Every figure in this table carries the window class and repetition count of its source point
(`R-02-18`), and any cross-campaign figure in the same table is a claim subject to
`R-06-3`.

## Charts

### R-07-6 Minimum charts

Generation: concurrency on X, aggregate output tokens/s on Y, one line per topology.
Prefill: concurrency on X, aggregate prompt tokens/s from the isolated prefill profile on Y,
one line per topology. Recommended additionally: TTFT p50/p95/p99 vs concurrency; ITL
p50/p95/p99 vs concurrency; goodput vs concurrency; requests/s vs concurrency; KV peak
utilisation vs concurrency; GPU utilisation and power vs concurrency; TPS/GPU vs concurrency;
topology comparison at equal total GPU count.

Interpolated values must be clearly identified; preferably do not interpolate missing
benchmark points. A curve whose line crosses a concurrency axis where no measurement exists is
not evidence about that concurrency.

## Conclusions

### R-07-7 Per model and topology, state

Best single-user generation rate; peak aggregate generation TPS and its concurrency; peak
isolated prefill TPS and its concurrency; highest concurrency satisfying the latency SLO;
saturation point and the evidence for it; peak KV usage and remaining headroom; dominant
observed bottleneck; TPS/GPU and energy/token; PCIe/NVLink traffic per token, collective
bandwidth/latency, same-NUMA vs cross-NUMA penalty, negotiated-link state, and whether fabric
evidence supports the bottleneck conclusion; whether replication or model parallelism is
preferred for interactive latency, maximum throughput, long-context capacity and mixed
production traffic; and any limitation preventing an apples-to-apples comparison, including
unsupported hardware counters or profiling conflicts.

### R-07-8 Do not present theoretical, interpolated, microbenchmark and end-to-end results as interchangeable

They are different measurement scopes (`R-02-3`). A microbenchmark number quoted next to an
end-to-end number without a scope label invites a comparison that was never measured.

### R-07-9 Report the falsified hypotheses, not just the surviving ones

A hypothesis that was tested and rejected is a finding and belongs in the report; "untested"
must never be rendered as "tested and rejected" (`R-RASTER-18`). On 2026-09-06 the rejected
hypotheses (ambient load explaining a gap, deeper speculation winning, admission slack being
universal) were as decision-relevant as the peak itself.

## Feedback into the pipeline

### R-07-10 Executing a step that revealed a missing or ambiguous rule files the fix in that step's `RULES.md`

Not in a journal, not in a chat summary: the owning chapter's rule file gets a new rule ID,
and its `Sources:` section cites the failure that produced it. The journal keeps the narrative
and the raw evidence; the rule file keeps the norm. If nothing was learned, say so explicitly
in the report so the absence of feedback is distinguishable from the absence of review.

This is the mechanism that produced `R-01-10`, `R-02-10`, `R-02-13`..`R-02-18`,
`R-06-3`..`R-06-6` and `R-06-8`/`R-06-9`, and it only works if the reader of a report is the
person who can edit the rule.

## Exit gate — closing a campaign

- [ ] summary table complete per `R-07-5`, with window class and repetition count per figure
- [ ] minimum charts generated, interpolation identified or absent
- [ ] conclusions state all `R-07-7` items, including limitations
- [ ] scope labels preserved; no cross-scope interchange (`R-07-4`, `R-07-8`)
- [ ] falsified hypotheses reported (`R-07-9`)
- [ ] PROCEDURE feedback filed into the owning chapter and cited, or its absence stated (`R-07-10`)

## Sources

`R-07-5`..`R-07-7` and `R-07-8` moved from `PROCEDURE.md` §14/§15/§17; `R-07-1`..`R-07-4` from
`harness/7-report-and-feedback/RULES.md`. `R-07-9` and `R-07-10` are new, both traceable to 2026-09-06: the report
draft that omitted rejected hypotheses while chasing a fabricated comparator, and the fact
that ten rules derived that day had no permanent home until the chapter files existed.

## Sub-step budgets

One budget per sub-step: **wall-clock minutes**. B = blocking, charged in full;
O = off-path, must be scheduled inside a measurement window. Rules and breach protocol: `PIPELINE.md`.

| Sub-step | Owner | Path | Budget |
|---|---|---|---|
| charts, per-GPU and energy-per-token normalisation | mech | O | 15m |
| conclusions, sizing, software-vs-hardware attribution | **agent** | B | 45m |
| reconcile with previously published claims | **agent** | B | 30m |
| pipeline rule changes | **agent** | O | 30m |

### R-07-11: Reader-facing reports carry one prefill series, and it is gate-cold

A report or site page presents input-token throughput as *the* prefill series. No warm/cold
typology, no served-fraction labels, no parallel cache-served series: readers are buying
capacity, not cache behaviour, and the cache question is settled before publication by the
gate (R-03-28, R-05-14, R-06-12) rather than discussed on the page. Therefore a prefill figure
may only come from runs whose verdict is `cold`; warm or unverified measurements are archived
evidence with their verdict recorded in acceptance, and are never rendered as prefill.

### R-07-12: Telemetry column names belong to the reader, not the writer

`local_telemetry()` fills GPU temperature from a column named `temperature_c`, VRAM from
`memory_used_mib`, board power from `power_w`, and derives host CPU busy from `cpu_*` jiffy
counters. The normalizer wrote headers containing none of those names, so those cells could
never be filled however much telemetry was sampled -- empty panels were guaranteed by a schema
mismatch long before any collection failure. Sampling the right quantity under the wrong name
collects nothing.

* Column names in telemetry artifacts are the reader's contract; change them only by changing
  the reader in the same commit.
* Raw counters, not pre-computed percentages, where the reader differences them across a
  window (CPU jiffies). A percentage cannot be differenced and silently becomes a claim.
* Absent readings are written empty, never zero: a missing temperature is not 0 degrees.

