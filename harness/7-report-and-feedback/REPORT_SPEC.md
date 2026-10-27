---
kind: rule
step: 7
title: Report specification
---

# Comparable Inference Report Specification

**Status:** Approved generic reporting contract
**Visual reference:** [`code/reference/approved-reference.html`](code/reference/approved-reference.html)
**Scope:** Comparable HTML reports generated from future LLM inference campaigns

This document controls report structure and semantics, not every sentence or pixel. A report may adapt explanatory prose to the campaign, but it must not silently alter metric meaning, series selection, statistics, units, chart behavior, or chapter coverage.

## 1. Change control

1. This specification is the single source of truth for comparable reports.
2. The approved reference HTML is the visual baseline.
3. A campaign-specific configuration supplies facts; it must not redefine generic semantics.
4. Changes to generic terminology, sections, charts, statistics, colors, or units require this document to change first.
5. Missing metrics are marked unavailable; they are never rendered as zero.
6. No data is invented, extrapolated, or borrowed from another campaign.
7. Generated reports do not create or require checksums. Version-control history, source paths, generator/template paths, and campaign manifests provide provenance; cryptographic checksums are reserved for downloaded model data.

## 2. Reader-facing terminology

Only two throughput concepts appear in the report:

- **Prefill:** processing input tokens, reported in input tokens/s.
- **Decode:** producing output tokens, reported in output tokens/s.

Internal benchmark profile or request-mix names must not appear in headings, legends, tables, summaries, or explanatory copy. They may remain in machine-readable provenance.

## 3. Source-series selection

Prefill and Decode are selected independently:

- Decode uses the eligible source series whose **maximum median output TPS at any measured concurrency** is highest.
- Prefill uses the eligible source series whose **maximum median input TPS at any measured concurrency** is highest.

Profile-specific deployments are encouraged when independently optimized through
the evolutionary raster. The report must identify the exact Decode, Prefill, and
Balanced deployment IDs. After selection, all latency, power, energy, CPU, RAM,
GPU, scheduler, and load-balancer values remain attached to that same source
series. A report must not combine throughput from one source series with latency
or telemetry from another.

## 4. Statistics and variation

At each operating point:

- central value: median across repetitions;
- variation band: observed minimum–maximum across repetitions;
- tooltip: concurrency, median, minimum, maximum, and repetition count `n`;
- table: median and range;
- machine-readable output: individual runs plus mean, median, standard deviation, minimum, and maximum.

A campaign configuration may request another statistic only by declaring the report non-comparable.

## 5. Concurrency axis

- The x-axis is numeric and proportional to global concurrency, never an equally spaced category axis.
- The domain starts at C1 unless the campaign has no C1 measurement.
- The default maximum is C192.
- If measured data exceeds C192, the domain expands to the highest measured concurrency. It never truncates a measured point.
- Major tick labels may be reduced for readability; every measured point remains visible.
- Decode and Prefill may use different measured subsets of the shared axis when
  separately qualified profile-specific deployments are combined. Provenance
  must identify each source deployment, and missing points are never fabricated.
- Unmeasured areas inside the chosen domain are not interpolated as observations.
- A configured active-sequence ceiling is shown when known and inside the domain.
- Measurements beyond that ceiling are explicitly described as overload coverage.

## 6. Stable visual semantics

- Decode: blue `#086c83`.
- Prefill: orange `#d36b32`.
- Tail/p95: red `#aa4050`.
- Baseline/reference: purple `#7557a5`.
- Median: solid line.
- Repetition range: translucent band.
- Measurements: visible point markers.
- Every chart has a visible legend identifying every line.
- Every chart has an explicit **bold y-axis unit title**.
- Y-axis tick values are bold.
- Axes include units and tooltips do not substitute for labels or legends.
- The HTML is responsive, printable, self-contained, and functional through `file://` without external assets.

## 7. Required chapter order

1. Executive summary
2. Capacity curves
   - Decode throughput
   - Prefill throughput
   - Per-user Decode rate
   - Per-user Prefill rate
   - Throughput variability
3. Responsiveness
   - TTFT p50/p95
   - ITL average/p95
4. Power and efficiency
   - aggregate GPU board power
   - joules/useful token
5. Primary resources
   - GPU utilization
   - GPU temperature
   - allocated VRAM
   - host CPU busy
   - host RAM used
6. GPU memory path, clocks, and PCIe endpoints
   - memory-copy utilization
   - SM and memory clocks
   - aggregate GPU-endpoint PCIe RX/TX rates
   - PCIe replay-counter changes
7. Serving behavior
   - running requests
   - waiting requests
   - KV-cache utilization
   - speculative-token acceptance when available
8. Collapsible diagnostics
9. Host fabric qualification when supplied
10. Method and topology
11. Selected measurement table
12. Limitations and provenance

A missing optional metric leaves a clearly labeled unavailable panel or is omitted with an availability note; required throughput and latency metrics must exist for a report to be called comparable.

When a host-fabric qualification input is supplied, add a distinct section that
summarizes NCCL same-NUMA/cross-NUMA bandwidth, placement penalties, P2P
bandwidth, negotiated link state under load, counter availability, and explicit
limitations. Host-level active microbenchmarks must remain distinct from
passive per-inference-run PCIe endpoint telemetry.

## 8. Metric definitions

### Latency

- TTFT: p50 and p95, milliseconds; logarithmic y-axis permitted and labeled.
- ITL: average and p95, milliseconds.
- End-to-end latency may appear in diagnostics.

### GPU power and energy

- Label as **aggregate GPU board power**, never server or wall power.
- Prefer cumulative DCGM energy-counter deltas over the exact measured interval.
- Otherwise integrate timestamped board-power samples and disclose the fallback.
- Decode efficiency: joules/output token.
- Prefill efficiency: joules/input token.
- B0 unloaded idle, B1-pre loaded idle, and B1-post loaded idle are separate
  deployment-state baselines and must include their source intervals.
- Baselines never appear as C0 on concurrency axes; request throughput and
  latency are not applicable for them.
- Model-residency cost uses B1-pre minus B0; incremental workload energy uses
  the operating point minus B1-pre; B1-post minus B1-pre reports idle drift.

### GPU temperature

- Metric: collected GPU device temperature, not hotspot, ambient, or thermal limit.
- Y-axis: **GPU TEMPERATURE (°C)**.
- Central value: median across repetitions of each run's mean across participating GPUs.

### CPU and RAM

- CPU: measured-window host busy percentage; disclose logical CPU count.
- RAM: `MemTotal − MemAvailable`, GiB.
- Do not label page cache as application RSS.
- Container RAM is diagnostic and shown only when monitored containers are identified.
- Process-memory attribution uses Linux `/proc/<pid>/smaps_rollup` for the
  selected inference processes and reports summed PSS, RSS, private, shared, and
  swap in GiB.
- Summed PSS is the preferred approximately additive attribution. Summed RSS is
  diagnostic only because the same shared pages may appear in multiple worker
  RSS values. The report must state this caveat adjacent to the charts.

### Serving metrics

- Running/waiting request values are aggregated across serving replicas.
- KV-cache percentage states whether it is pooled, mean, or maximum.
- Speculative acceptance is accepted draft-token rate divided by draft-token rate.
- Preemptions are never silently treated as zero when unavailable.

## 9. Collapsible diagnostic sections

Use native `<details>` elements, collapsed by default:

1. **CPU breakdown and host load**
   - user, system, iowait, load, context switches/interrupts when available;
2. **Process memory attribution**
   - inference-process PSS, RSS, private/shared mappings, and swap;
   - PSS is primary; RSS is explicitly non-additive for shared mappings;
3. **Containers, storage, and network**
   - container CPU/RAM/network, disk throughput, host network;
3. **Scheduler anomalies and token counters**
   - preemptions, server-observed prompt/decode rates, request distributions;
4. **Load balancer and application-network diagnostics** (required for all
   future campaigns, including one-backend deployments)
   - frontend ingress/egress MiB/s and exact-window byte totals;
   - backend ingress/egress MiB/s and exact-window byte totals;
   - directional bytes per successful request;
   - sessions, queue depth/time, retries, errors, and replica distribution;
   - explicit metric scope: proxy frontend, proxy backend, container/bridge or
     loopback, or physical NIC.

Never combine RX and TX into one bandwidth value. A same-host load-balancer
measurement is application-traffic accounting, not evidence of physical-NIC
utilization or network-fabric capacity. Legacy direct-backend campaigns render
these metrics as **unavailable — load balancer absent from measured path** and
must disclose the protocol limitation.

The main report remains concise; diagnostics preserve collected evidence without overwhelming readers.

## 10. Executive summary

Show:

- best median Decode TPS and concurrency;
- best median Prefill TPS and concurrency;
- aggregate GPU board power at best Decode;
- GPU temperature at best Decode;
- source run/request/error counts;
- host, GPU count/model, and serving topology.

Every headline identifies its statistic in nearby text.

## 11. Campaign-specific configuration

All variable facts come from a validated report configuration:

- identity and display title;
- source campaign and normalized input paths;
- model repository/revision/served name;
- hardware and serving topology;
- quantization, KV dtype, MTP, context, scheduler, and batching settings;
- measured concurrency points and optional scheduler ceiling;
- metric availability and energy method;
- output filename and provenance notes.

See `harness/7-report-and-feedback/schemas/report-config.schema.json` and `harness/7-report-and-feedback/code/examples/report-config.json`.

## 12. Required artifacts

```text
report/
├── <report-name>.html
├── report-config.json
├── normalized-report-data.json
├── campaign-summary-runs.csv
├── campaign-summary-aggregate.csv
├── REPORT_SPEC.md
└── generator-version.txt
```

Raw campaign artifacts remain authoritative and are not overwritten.

## 13. Pre-publication validation

- [ ] Configuration validates against the schema.
- [ ] Input includes all completed eligible runs and documents exclusions.
- [ ] Only Prefill and Decode appear as reader-facing throughput concepts.
- [ ] Selection policy is applied independently and provenance records selected source IDs.
- [ ] All measured concurrency points fit the numeric domain.
- [ ] Median, min–max band, markers, legends, bold y-axis units, and `n` tooltips are present.
- [ ] Latency remains attached to the selected throughput source.
- [ ] Temperature is present when collected.
- [ ] Power is labeled GPU board power.
- [ ] Missing telemetry is unavailable, not zero.
- [ ] Collapsible diagnostics reflect collected metrics.
- [ ] Headline values match normalized data.
- [ ] HTML works offline.
- [ ] No report or benchmark-output checksums were generated; checksum use is limited to downloaded model data.
