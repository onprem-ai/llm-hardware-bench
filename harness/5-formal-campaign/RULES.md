---
kind: rule
step: 5
title: Formal campaign rules
absorbs:
  - PROCEDURE.md §3 Required Test Record, §5 Randomized Inputs and Cache Control, §6 Workload Profiles
  - PROCEDURE.md §8 Resource Telemetry (including §8.7 fabric qualification)
  - PROCEDURE.md §9 KV-Cache Capacity, §10 Deployment Topology Comparison, §11 API examples,
    §12 Manual TTFT verification, §13 Result Artifacts
  - harness/5-formal-campaign/RULES.md (campaign artifact layout; see the note below)
---

# Chapter 5 — Formal campaign

Pipeline order, budgets and gates: `PIPELINE.md`. This chapter runs the frozen campaign: the
record contract, the telemetry contract, capacity and topology analysis, and the artifact
layout. It is the largest chapter because it is where evidence is created, and it is the
cheapest to migrate: its rules were already written down, so they are moved here **verbatim**
rather than rewritten. Rule IDs are assigned in move order, not by importance.

Two ownership problems exist after this move and are deliberately not papered over:

- **Definition vs capture.** Chapter 2 defines B0/B1-pre/B1-post (`R-02-7`); this chapter
  captures them. Where the capture text below restates a definition, chapter 2 wins and the
  local duplicate should become a reference.
- **Artifact layout.** Former §13 and `harness/5-formal-campaign/RULES.md` describe one thing from two
  directions. Both are kept as-is pending consolidation into a single record contract, tracked
  in `harness/MOVED.md`. Restating the same layout twice is how layouts drift.

## R-05-1 — Required Test Record

> Formerly `PROCEDURE.md` §3. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


Create one immutable, machine-readable `manifest.json` for **every measured run** (one profile × concurrency × repetition), plus a campaign manifest that references all run IDs. Generate the run manifest before warm-up, update it atomically at phase boundaries, and finalize it after aggregation. Record:

### Model

Owned by [`harness/1-model-qualification/RULES.md`](harness/1-model-qualification/RULES.md)
**R-01-9**, which lists the mandatory identity fields. Moved 2026-09-06; do not restate
them here.

### Serving stack

- Engine and exact image/version/commit
- CUDA version
- NVIDIA driver version
- PyTorch version
- NCCL version
- ModelOpt or quantization runtime version
- Full launch command and environment variables
- Tensor parallel size (TP)
- Pipeline parallel size (PP)
- Data parallel/replica count (DP)
- Decode context parallel size (DCP)
- Expert parallel size (EP), if applicable
- Maximum model length
- Maximum number of sequences
- Maximum batched tokens
- GPU memory utilization setting
- KV-cache dtype
- Prefix-cache state and configuration
- Chunked-prefill state
- CUDA graph settings
- Scheduler settings
- Tool-call/chat-template flags
- Load-balancer implementation and exact version/image
- Load-balancer listen endpoint and metrics endpoint
- Backend endpoint(s), routing policy, timeouts, and connection settings
- Explicit confirmation that the benchmark client targeted the load balancer,
  never a backend directly

### Hardware

- Hostname
- CPU model, sockets, cores, threads, and NUMA topology
- Total system RAM
- GPU model and count
- GPU VRAM
- GPU PCIe topology and link widths
- NVLink/NVSwitch presence and status
- Storage device/model and filesystem
- Network interface and negotiated speed
- Power limits and clock settings
- MIG configuration, if applicable

### Workload

- Endpoint and model name
- Concurrency
- Number of measured requests
- Warm-up request count and duration
- Input-token target or `num_words`
- Output-token target or `max_tokens`
- Streaming state
- Sampling parameters
- EOS handling
- Random-input generation method and seed policy
- Request arrival mode: closed-loop, fixed rate, or Poisson
- Timeout and retry policy
- Warm-up start/end timestamps
- Settling start/end timestamps
- Measured start/end timestamps and duration
- UTC timestamps in RFC 3339 with nanosecond precision where supported
- Monotonic-clock timestamps for duration calculations
- Benchmark client, server, and telemetry clock offsets/status
- Target and actual input/output token totals
- Success, error, timeout, cancellation, and output-length-mismatch counts
- Stable run ID propagated to artifact names, logs, and telemetry metadata
- Container IDs, replica IDs, GPU allocation, and actual CPU/NUMA affinity

---


## R-05-2 — Randomized Inputs and Cache Control

> Formerly `PROCEDURE.md` §5. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


Use a newly generated random prompt for every measured request. This avoids accidental prefix-cache hits and unrealistic tokenizer repetition.

The benchmark API’s `num_words` mode is preferred when it generates a fresh phrase per request:

```go
func AskOpenAiRandomInput(...) {
    prompt := generateRandomPhrase(numWords)
    return AskOpenAi(client, model, prompt, maxTokens, bar)
}
```

Rules:

- Never use one static prompt for prefill benchmarking.
- Preserve the input-generation method and random seed policy.
- Record actual token counts, not only word counts.
- If testing prefix caching, run it as a separate labeled campaign with defined cache-hit ratios.
- Run a cold-cache and warm-cache test separately when cache behavior matters.

---


## R-05-3 — Workload Profiles

> Formerly `PROCEDURE.md` §6. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


The required primary suite consists of three profiles: decode-focused,
prefill-focused, and balanced. Independently optimize each profile through the
evolutionary deployment raster before running its formal grid. Run each
profile-specific winner at all target concurrency levels selected for that
profile. A study may additionally qualify one shared compromise deployment for
operational simplicity, but it must not replace stronger profile-specific peak
capacity results. Long-context testing is a separate optional qualification and
does not use the full concurrency grid.

### 6.1 Decode-focused profile

Purpose: measure generation speed with minimal prefill cost.

Prioritize raster mutations in decode graph coverage, actual active-request and
Mamba/state admission, speculation method/depth, KV/state allocation, and
replica/parallel topology. Always include a speculation-off control matched for
actual admission and graph width; an unmatched control is not evidence of
speculative-decoding benefit.

```json
{
  "concurrency": "1,2,4,8,16,24,32,40,48,56,64",
  "num_words": 50,
  "max_tokens": 500
}
```

Prefer `ignore_eos=true` or an equivalent mechanism so every request produces the target output length. If unavailable, record actual output-token distributions.

Primary chart:

```text
Generation throughput (output tok/s) vs concurrency
```

Also report TTFT, ITL, E2E latency, request throughput, and errors.

### 6.2 Prefill-focused profile

Purpose: measure prompt ingestion with minimal decode interference.

Run a dedicated Prefill raster. Prioritize chunked-prefill size, maximum prefill
or batched-token budget, concurrent prefill admission, prefill CUDA-graph mode,
KV/state allocation, context limit, and topology. Speculative decoding normally
provides no direct value to near-prefill-only output shapes and must be retained
only if qualification shows that it does not reduce useful Prefill capacity or
is required for an intended shared deployment.

Recommended primary test:

```json
{
  "concurrency": "1,2,4,8,16,24,32,40,48,56,64",
  "num_words": 1500,
  "max_tokens": 5
}
```

A 100-token output may be retained as a compatibility test, but 5–10 output tokens isolate prefill more effectively.

Primary chart:

```text
Prefill throughput (prompt tok/s) vs concurrency
```

For every point record:

- Total prompt tokens
- Aggregate prompt TPS
- TTFT p50/p95/p99
- Actual prompt-token mean/p5/p95
- Output tokens and decode duration
- Cache-hit counters, if available

### 6.3 Balanced profile

Purpose: represent ordinary interactive traffic.

Select this deployment independently after Decode and Prefill winners are known.
Seed its raster from those winners and test a small set of compromises rather
than restarting from conservative defaults. Rank by goodput and latency SLOs as
well as aggregate input/output throughput.

```json
{
  "concurrency": "1,2,4,8,16,24,32,40,48,56,64",
  "num_words": 500,
  "max_tokens": 500
}
```

### 6.4 Optional long-context qualification

Purpose: verify that long context is usable and expose context-length scaling and KV-cache pressure. This is not part of the primary concurrency sweep.

Recommended compact matrix:

```text
Prompt lengths: 8K, 32K, 64K, 128K tokens
Concurrency:    1 and 4
Output:         32 tokens
```

Stop at the deployment’s validated context or practical capacity. Add other context lengths or concurrency points only when investigating a specific capacity limit.

### 6.5 Optional fixed token-shape compatibility profile

A study may define a fixed token-shape profile when comparison with historical
results is required. Freeze its input/output lengths, sampling options,
streaming mode, concurrency grid, and historical source in the study config and
campaign manifest. Keep this profile separate from isolated decode and prefill
tests.

---


## R-05-4 — Resource Telemetry

> Formerly `PROCEDURE.md` §8. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


Collect telemetry continuously from B0 through model startup, B1-pre, all
measured work, and B1-post when practical. Use one-second resolution for normal
runs and sub-second resolution for brief runs. Preserve raw cumulative counters
and timestamps; derive rates and interval totals afterward. Never include model
startup, warm-up, settling, or idle samples in measured-run statistics. Keep B0,
B1-pre, and B1-post as separately bounded and labeled intervals.

### 8.0 VictoriaMetrics correlation and delayed export

The host VictoriaMetrics service is the authoritative historical telemetry source. Correlate each measured run with the exact `start_time` and `end_time` recorded by AIPerf. Do not query immediately when a run ends: allow **at least 60 seconds** for collected samples to be consolidated and become reliably queryable.

Required workflow for every measured run:

1. Preserve AIPerf's exact start and end timestamps.
2. Wait at least 60 seconds after the end timestamp.
3. Query VictoriaMetrics over the measured interval, preferably with a 5–10 second boundary margin.
4. Export the raw range-query response alongside the AIPerf artifacts.
5. Calculate averages, peaks, minima, percentiles, and per-GPU imbalance only from the measured interval, excluding warm-up and settling periods.
6. Record missing scrape intervals and target health. Never silently treat missing samples as zero.

Example:

```bash
sleep 60
curl -G 'http://127.0.0.1:8428/api/v1/query_range' \
  --data-urlencode 'query=<promql-expression>' \
  --data-urlencode "start=$START" \
  --data-urlencode "end=$END" \
  --data-urlencode 'step=2s' \
  > victoria-<metric>.json
```

Available jobs on this host include `node` (CPU/RAM/disk/network), `gpu` (DCGM), `containers` (cAdvisor), and `vllm` (inference metrics). Verify that each relevant target was healthy throughout the benchmark interval.

#### Required per-run VictoriaMetrics snapshot

Every measured run directory must contain a self-contained historical telemetry snapshot so charts can be regenerated later without depending on continued access to the live VictoriaMetrics database:

```text
<run>/victoriametrics/
├── window.json
├── targets.json
├── metric-names.json
├── raw/
│   ├── node_cpu_utilization.json
│   ├── node_memory_available.json
│   ├── node_memory_used.json
│   ├── node_load1.json
│   ├── node_swap_used.json
│   ├── disk_read_bytes.json
│   ├── disk_write_bytes.json
│   ├── network_receive_bytes.json
│   ├── network_transmit_bytes.json
│   ├── gpu_utilization.json
│   ├── gpu_memory_used.json
│   ├── gpu_memory_free.json
│   ├── gpu_temperature.json
│   ├── gpu_power.json
│   ├── gpu_sm_clock.json
│   ├── gpu_memory_clock.json
│   ├── gpu_pcie_rx_bytes_rate.json
│   ├── gpu_pcie_tx_bytes_rate.json
│   ├── gpu_pcie_replay_delta.json
│   ├── gpu_nvlink_rx_bytes_rate.json
│   ├── gpu_nvlink_tx_bytes_rate.json
│   ├── gpu_sm_active.json
│   ├── gpu_sm_occupancy.json
│   ├── gpu_tensor_active.json
│   ├── gpu_dram_active.json
│   ├── gpu_fp16_active.json
│   ├── gpu_fp32_active.json
│   ├── gpu_power_violation_delta.json
│   ├── gpu_thermal_violation_delta.json
│   ├── gpu_xid_errors.json
│   ├── container_cpu.json
│   ├── container_memory.json
│   ├── container_network_receive.json
│   ├── container_network_transmit.json
│   ├── vllm_running_requests.json
│   ├── vllm_waiting_requests.json
│   ├── vllm_kv_cache_usage.json
│   ├── vllm_preemptions.json
│   ├── vllm_prompt_tokens_rate.json
│   ├── vllm_generation_tokens_rate.json
│   ├── vllm_mtp_draft_rate.json
│   └── vllm_mtp_accepted_rate.json
└── summary.json
```

`window.json` must record:

- AIPerf start and end timestamps;
- query start and end timestamps, including any margins;
- query step and VictoriaMetrics URL;
- export timestamp;
- model, profile, concurrency, topology, and benchmark ID.

`targets.json` must capture `/api/v1/targets` after the consolidation delay. `metric-names.json` should preserve the available metric-name inventory or the exact list of queried metrics. Each file under `raw/` must contain the complete unmodified `/api/v1/query_range` response. `summary.json` may contain derived averages, maxima, minima, percentiles, deltas, and per-GPU imbalance, but it must never replace the raw responses.

Counter metrics must be queried using rates or interval increases rather than raw cumulative values. Gauge metrics should be retained as their full time series. Recommended examples include:

```promql
# Host CPU busy fraction
1 - avg(rate(node_cpu_seconds_total{job="node",mode="idle"}[1m]))

# Host memory used bytes
node_memory_MemTotal_bytes{job="node"} - node_memory_MemAvailable_bytes{job="node"}

# GPU metrics
DCGM_FI_DEV_GPU_UTIL{job="gpu"}
DCGM_FI_DEV_MEM_COPY_UTIL{job="gpu"}
DCGM_FI_DEV_FB_USED{job="gpu"}
DCGM_FI_DEV_FB_FREE{job="gpu"}
DCGM_FI_DEV_POWER_USAGE{job="gpu"}
DCGM_FI_DEV_GPU_TEMP{job="gpu"}
DCGM_FI_DEV_SM_CLOCK{job="gpu"}
DCGM_FI_DEV_MEM_CLOCK{job="gpu"}
avg_over_time(DCGM_FI_PROF_PCIE_RX_BYTES{job="gpu"}[30s])
avg_over_time(DCGM_FI_PROF_PCIE_TX_BYTES{job="gpu"}[30s])
increase(DCGM_FI_DEV_PCIE_REPLAY_COUNTER{job="gpu"}[<run-window>])
DCGM_FI_PROF_SM_ACTIVE{job="gpu"}
DCGM_FI_PROF_SM_OCCUPANCY{job="gpu"}
DCGM_FI_PROF_PIPE_TENSOR_ACTIVE{job="gpu"}
DCGM_FI_PROF_DRAM_ACTIVE{job="gpu"}

# vLLM state
vllm:kv_cache_usage_perc{job="vllm"}
vllm:num_requests_running{job="vllm"}
vllm:num_requests_waiting{job="vllm"}
increase(vllm:num_preemptions_total{job="vllm"}[<run-window>])
rate(vllm:prompt_tokens_total{job="vllm"}[30s])
rate(vllm:generation_tokens_total{job="vllm"}[30s])
rate(vllm:spec_decode_num_draft_tokens_total{job="vllm"}[30s])
rate(vllm:spec_decode_num_accepted_tokens_total{job="vllm"}[30s])
```

Because VictoriaMetrics consolidation takes approximately one minute on this deployment, the benchmark runner should enqueue or perform the export only after that delay. A failed inference run must also receive a telemetry snapshot; OOM and saturation failures are important capacity evidence.

### 8.1 GPU metrics

Collect per GPU:

- GPU utilization
- Tensor-core utilization, if exposed
- SM occupancy/activity
- Memory-controller utilization
- HBM/VRAM used and free
- HBM read/write bandwidth
- Power draw and power limit
- Temperature
- Graphics and memory clocks
- PCIe TX/RX throughput
- NVLink TX/RX throughput
- ECC errors and throttling reasons
- Per-process GPU memory
- Cumulative GPU energy, if supported
- Power/thermal/clock throttling reason flags

For power and energy reporting:

- report mean, p50, p95, and peak watts per GPU and in aggregate;
- prefer a cumulative energy counter and calculate its measured-window delta;
- otherwise trapezoid-integrate power using actual sample timestamps rather than assuming fixed one-second intervals;
- use B1-pre loaded idle when reporting incremental workload energy and B0
  unloaded idle when reporting model-residency energy;
- calculate joules per output token, joules per input token for isolated prefill, output tokens/s/watt, and total tokens/s/watt;
- state explicitly whether power is board power, GPU-chip power, or another counter semantic.

Basic collection fallback:

```bash
nvidia-smi dmon -s pucvmet -d 1 -o DT > nvidia-smi-dmon.csv
```

Additional snapshots:

```bash
nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,memory.used,memory.free,power.draw,power.limit,temperature.gpu,clocks.sm,clocks.mem,pcie.link.gen.current,pcie.link.width.current --format=csv -l 1
nvidia-smi pmon -s um -d 1
```

Prefer DCGM/Prometheus counters when available. Record counter names and scrape interval.

### 8.2 CPU metrics

Collect:

- Total and per-core CPU utilization
- User/system/iowait/steal percentages
- Load average
- Context switches and interrupts
- CPU frequency and throttling
- NUMA-local versus remote memory traffic, where possible
- Serving-process CPU utilization, CPU-seconds, and thread/process count
- Per-socket and per-NUMA-node utilization
- Per-container vLLM and HAProxy CPU utilization
- CPU cgroup throttled time and throttling events
- Ambient (non-benchmark) CPU cores and the identity of the largest
  non-benchmark consumers, per run and per baseline (§4.1)

Report average, p95, and peak CPU utilization, CPU-seconds per completed request, and CPU-seconds per million generated tokens. Record actual CPU affinity and NUMA memory policy; do not claim NUMA pinning merely because GPU groups align with NUMA domains.

Examples:

```bash
mpstat -P ALL 1
pidstat -p <server-pid> -u -r -d -w 1
vmstat 1
```

Report background load as a first-class result, not as a footnote. Attribute
measured CPU between the serving stack, the benchmark client, and everything else
over the same window, and state the ambient core count and load average for each
run. When two results are compared, state whether their ambient load matched;
otherwise the comparison inherits that difference. Preserve the raw sampler output
so attribution stays auditable.

### 8.3 System RAM

Collect:

- Used/available RAM
- Serving-process RSS and virtual memory
- Page cache
- Swap use and swap activity
- Major page faults
- NUMA allocation
- Pinned memory, if available
- Per-container RSS and working set
- Per-process `/proc/<pid>/smaps_rollup` RSS, PSS, private clean+dirty,
  shared clean+dirty, and swap for vLLM/API/engine/TP workers
- Memory pressure/OOM events
- Memory-bandwidth counters where supported

Report absolute GiB, model-residency increment above B0, and active-workload
increment above B1-pre. Keep available memory, anonymous/application memory, and
Linux page cache separate; do not describe page cache as application RSS.

Do not sum worker RSS and interpret it as unique physical memory: shared pages
may be counted in every process that maps them. Report summed PSS as the
preferred approximately additive process attribution, with RSS shown only as a
diagnostic. Report private, shared, and swap components separately. Preserve the
process-selection regex and per-PID raw samples so attribution remains auditable.

Any swap activity during a benchmark must be called out prominently.

### 8.4 Network and mandatory load-balancer boundary

Every measured inference campaign **must place a load balancer in the request
path**, including deployments with exactly one model-server instance. The
required path is:

```text
benchmark client → load-balancer frontend → one or more model-server backends
```

The benchmark command must target the load-balancer endpoint. It must never
target a model backend directly. For a single model instance, configure one
backend; do not omit or bypass the load balancer. Keep the same load-balancer
implementation and materially relevant settings across configurations being
compared. A direct-to-backend campaign is incomplete for network-capacity
reporting and must disclose that limitation; it cannot be silently presented as
satisfying the full protocol.

The mandatory proxy boundary provides stable application-traffic accounting
independent of replica count. It also preserves a comparable request path when
a deployment changes from one backend to multiple backends. It does **not** by
itself measure physical-NIC or network-fabric capacity: a same-host proxy may
send traffic over loopback or a container bridge. Report proxy traffic and
physical-interface traffic as separate scopes.

Collect:

- Load-balancer frontend RX and TX byte-counter deltas and directional MiB/s
- Load-balancer backend RX and TX byte-counter deltas and directional MiB/s
- Bytes per successful request, separately by direction
- Requests/responses and response-status counts
- Active and queued sessions, connection/request rates, and maximum sessions
- Per-backend selections, health, queue depth/time, retries, redispatches, and
  connection failures
- Container and host-interface bytes and packets per second
- TCP retransmits, drops, errors, connection count, and socket pressure
- Benchmark-client CPU usage and client-to-load-balancer latency

Enable HAProxy's built-in Prometheus exporter on a dedicated local metrics port
and scrape it as its own VictoriaMetrics job. The preflight must prove that the
expected frontend and backend byte/request counters change under a controlled
request. Missing or static load-balancer counters are a failed required-metric
gate, not zero traffic.

For every measured run, derive from exact-window raw counter deltas and report:

- frontend ingress MiB/s and egress MiB/s;
- backend ingress MiB/s and egress MiB/s;
- total bytes and bytes per successful request for each direction;
- requests per backend and replica imbalance percentage when applicable;
- backend queue p95, retries, and errors.

Do not add ingress and egress and call the result "network bandwidth"; the two
directions represent different payload flows and may also observe the same
logical exchange at different proxy interfaces. AIPerf payload bytes,
HAProxy frontend/backend counters, cAdvisor container counters, loopback/bridge
traffic, and physical-NIC counters have different semantics and must be labeled
separately. This telemetry quantifies traffic used by inference; it is not a
network throughput microbenchmark unless a separate controlled saturation test
is performed.

### 8.5 Disk and filesystem

Model inference should not perform sustained weight reads after startup. Collect:

- Read/write throughput and IOPS
- I/O latency and utilization
- Page faults

Unexpected disk activity may indicate memory pressure, lazy loading, or logging overhead.

### 8.6 Server/runtime metrics

Capture engine metrics such as:

- Running, waiting, and swapped/preempted requests
- Scheduler queue depth
- Prompt and generation tokens processed
- Prefix-cache hits and misses
- KV-cache utilization
- Request preemption/recomputation
- Batch size and batched-token count
- CUDA graph usage
- Speculative/MTP acceptance rate
- Expert load balance, if exposed
- Communication time for TP/EP/DCP collectives

Export the raw metrics, not only screenshots.

### 8.7 PCIe, collective, and NUMA fabric qualification

Treat the interconnect as a first-class component of every multi-GPU campaign. End-to-end inference telemetry and active fabric microbenchmarks answer different questions and must both be retained.

#### 8.7.1 Static topology and negotiated-link record

Before model launch and again after the campaign, save:

```bash
nvidia-smi topo -m
nvidia-smi topo -p2p r
nvidia-smi topo -p2p w
nvidia-smi --query-gpu=index,pci.bus_id,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max --format=csv
lspci -tv
lspci -vv -s <GPU-BDF>
numactl --hardware
lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE
cat /sys/bus/pci/devices/<BDF>/numa_node
cat /sys/bus/pci/devices/<BDF>/current_link_speed
cat /sys/bus/pci/devices/<BDF>/current_link_width
```

Record PCIe switch/bridge ancestry, root complexes, ACS/IOMMU state, GPU P2P read/write capability, BAR1 size/use, NVLink/NVSwitch absence or state, and actual container/process CPU and memory affinity. Do not infer a PCIe generation or lane width from the GPU model specification.

#### 8.7.2 Per-run passive fabric telemetry

During every measured inference window collect, when supported:

- `DCGM_FI_PROF_PCIE_RX_BYTES` and `DCGM_FI_PROF_PCIE_TX_BYTES` per GPU;
- `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` delta and PCIe correctable/uncorrectable errors;
- NVLink RX/TX bytes and link errors when NVLink exists;
- negotiated PCIe generation and width at start/end and any downshift event;
- NCCL/PyNCCL algorithm, protocol, channel count, transport, and topology selection from startup/debug receipts;
- CPU-socket/NUMA memory read/write bandwidth, local versus remote accesses, and inter-socket/UPI traffic using Intel PCM, `perf`, or the platform-equivalent counters;
- per-replica CPU affinity, memory policy, major page faults, and cgroup throttling.

For each run derive total and average PCIe RX/TX GiB/s per GPU and replica, p50/p95/peak rate, bytes per input token, bytes per output token, traffic imbalance, replay-counter delta, and negotiated-link headroom. DCGM's `DCGM_FI_PROF_PCIE_*_BYTES` fields are interval-average byte-rate gauges despite their names; average or integrate their timestamped samples and do not apply `rate()`/`increase()` to them. If a theoretical utilization percentage is reported, show the exact denominator and distinguish per-direction, aggregate, encoding-adjusted, and payload bandwidth. Do not divide NCCL `busbw` by a PCIe headline rate and call it link utilization without documenting the topology and collective correction factor.

DCGM profiling fields are not enabled by default in many exporter images. At campaign preflight run `dcgmi profile --list --entity-id gpu:0` (and representative GPUs on each NUMA node), preserve the supported metric groups, and configure a custom DCGM exporter collector when required. Selecting a field does not guarantee that the GPU/driver exports it. Record unsupported, permission-denied, counter-conflict, and missing-scrape states explicitly. DCGM profiling counters can conflict with CUPTI/Nsight; pause one collector before the other takes ownership.

#### 8.7.3 Campaign-level active microbenchmarks

Run active fabric tests only while inference services are stopped or in a separately labeled qualification window. Pin the exact `nccl-tests` commit, CUDA, NCCL, driver, environment, and GPU set. At minimum run `all_reduce_perf`, `all_gather_perf`, and `reduce_scatter_perf` over small latency-sensitive and large bandwidth-sensitive message sizes for:

- every production TP/EP/DCP group (for example GPUs 0-3 and 4-7);
- representative same-NUMA GPU pairs;
- representative cross-NUMA pairs;
- a deliberately cross-NUMA group of the same size;
- all GPUs;
- pinned and unpinned CPU/NUMA placement when topology sensitivity is under study.

Example shape:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 ./all_reduce_perf -b 8 -e 8G -f 2 -g 4 -n 50 -w 10
CUDA_VISIBLE_DEVICES=4,5,6,7 ./all_gather_perf -b 8 -e 8G -f 2 -g 4 -n 50 -w 10
CUDA_VISIBLE_DEVICES=0,4,1,5 ./reduce_scatter_perf -b 8 -e 8G -f 2 -g 4 -n 50 -w 10
```

Preserve raw output, correctness/error counts, operation time, algorithm bandwidth (`algbw`), and NCCL-corrected bus bandwidth (`busbw`) by message size. Report latency from small messages and sustained bandwidth from the large-message plateau. Also run CUDA `p2pBandwidthLatencyTest` or an equivalent directional peer matrix to expose asymmetric routes hidden by collective averages.

Where practical, compare NCCL algorithm/protocol choices (`Ring`/`Tree`, `LL`/`LL128`/`Simple`), channel counts, P2P enabled/disabled, and CPU pinning. These are qualification experiments, not knobs to cherry-pick independently for each measured production run.

#### 8.7.4 Fabric interpretation rules

- A throughput plateau alone does not prove a PCIe bottleneck.
- Pair high PCIe traffic with SM/DRAM activity, collective timing, queueing, and topology evidence.
- NCCL `algbw`, NCCL `busbw`, directional PCIe payload rate, and theoretical line rate are different quantities.
- Compare same-NUMA and cross-NUMA groups at identical rank count and message sizes.
- Report whether TP collectives remain within each replica's NUMA domain and whether load-balanced replicas exchange any model traffic.
- Keep active microbenchmark results separate from passive inference-window traffic.

### 8.8 Optional deep-compute and scheduler metrics

The following metrics are valuable for root-cause analysis but may require CUPTI, Nsight Systems/Compute, advanced DCGM groups, eBPF, PCM, or runtime instrumentation. Collect them on representative points rather than every run when overhead is material:

- SM active, achieved occupancy, eligible warps, issue-slot utilization, and warp-stall reasons;
- tensor-core/FP4/FP8/FP16/FP32 pipe activity and achieved versus theoretical tensor throughput;
- DRAM active, read/write bytes, L2 hit rate, cache-sector traffic, memory-pipe stalls, and arithmetic intensity;
- kernel launch count, duration distribution, CUDA graph hit/miss/fallback rate, graph recaptures, and CPU launch gaps;
- GEMM/MoE/attention kernel identity, tile choice, autotune selection, workspace size, and fallback frequency;
- NCCL kernel duration and overlap with compute, collective bytes per generated token, synchronization gaps, and straggler rank;
- scheduler batch-size distribution, scheduled tokens/step, active versus padded rows, prefill/decode mixing, chunk counts, and time with an empty batch;
- speculative decoding drafted/accepted/rejected tokens, accepted length distribution, per-position acceptance, verification overhead, and net target-model steps saved;
- MoE expert assignment histogram, load imbalance, dropped/padded tokens, expert hot spots, and communication volume per expert when EP is used;
- attention backend, average attended tokens, sparse-index hit rate, recurrent-state traffic, prefix-cache lookup/hit/eviction bytes, and KV block fragmentation;
- allocator reserved/allocated/inactive-split bytes, allocation retries, CUDA OOM events, KV block churn, and non-torch memory;
- CPU run-queue latency, context switches, IRQ/softirq distribution, scheduler migrations, page faults, NUMA misses, LLC misses, and memory bandwidth;
- network tail latency, TCP retransmits, socket backlog, HAProxy queue time, backend selection imbalance, and client-side event-loop saturation;
- clocks, voltage, power-limit state, thermal/power/reliability throttle duration, energy, temperature gradients, ECC/XID events, and PCIe replays;
- cold-start phase timing: metadata scan, shard reads, direct-I/O/page-cache behavior, weight materialization, JIT/autotune, graph capture, and readiness.

For representative kernel-level studies, capture a low-overhead Nsight Systems trace first, then use Nsight Compute only on selected kernels. Profiler runs must be separately labeled because instrumentation changes timing.

---


## R-05-5 — KV-Cache Capacity and Constraint Analysis

> Formerly `PROCEDURE.md` §9. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


Separate **static deployment capacity** from **runtime KV utilization**. Capture static KV capacity once per deployment/campaign after every replica is ready and before benchmark traffic begins. Do not duplicate the full static record in every run. Runtime KV utilization and capacity events remain mandatory for every measured run.

### 9.1 Static campaign-level capacity record

After all replicas have started and passed readiness checks, create:

```text
<campaign>/deployment-capacity.json
```

Capture per replica:

- replica ID, container ID, GPU allocation, TP/PP/DCP/EP topology, and startup timestamp;
- KV-cache dtype;
- available GPU KV-cache memory in GiB;
- number of GPU and CPU/host KV blocks, if exposed;
- tokens per block;
- startup-reported GPU KV capacity in tokens;
- configured host KV-offload capacity in GiB and tokens, if the runtime reports tokens;
- maximum model length;
- `max_num_seqs`, maximum batched tokens, GPU-memory-utilization, and other memory-affecting settings;
- maximum concurrency reported at representative sequence lengths;
- GPU memory reserved for weights, KV cache, CUDA graphs, and non-torch allocations;
- any linear-attention or recurrent state-cache allocation.

Also calculate campaign-level aggregates across independent replicas, including aggregate GPU KV tokens and aggregate host-offload capacity. Preserve the exact startup-log lines used as evidence and identify whether an aggregate value is directly reported or calculated by summing independent replica capacities. Do not sum capacities across TP ranks within one replica unless the runtime explicitly reports rank-local rather than replica-level capacity.

Example structure:

```json
{
  "captured_after_all_replicas_ready": true,
  "replicas": {
    "a": {
      "container_id": "...",
      "gpu_allocation": [0, 1],
      "gpu_kv_tokens": 823935,
      "available_gpu_kv_memory_gib": 8.69,
      "max_model_len": 524288,
      "max_num_seqs": 16,
      "kv_cache_dtype": "fp8",
      "host_kv_offload_gib": 48.5
    }
  },
  "aggregate_gpu_kv_tokens": 3296310,
  "aggregate_host_kv_offload_gib": 194.0
}
```

Every run-level `manifest.json` must contain a relative `deployment_capacity_reference` pointing to this campaign file. A new capacity snapshot is mandatory whenever any capacity-affecting deployment property changes, including model/checkpoint or quantization, replica topology, TP/PP/DCP/EP size, GPU allocation, `max_num_seqs`, maximum model length, maximum batched tokens, GPU-memory utilization, KV dtype, KV offload, CUDA-graph configuration, or another memory-affecting runtime flag. Such a change defines a new deployment configuration and must not silently reuse an old capacity record.

### 9.2 Runtime KV metrics

For every concurrency point capture:

- KV-cache usage average and peak
- Free KV blocks minimum
- Number of preemptions or recomputations
- Number of rejected requests due to capacity
- Queue depth and waiting requests
- Active sequence count
- Prefix-cache occupancy and hit rate

### 9.3 Capacity calculations

For a homogeneous request shape, estimate peak token occupancy:

```text
estimated live KV tokens = active sequences × (prompt tokens + generated tokens so far)
```

A conservative upper bound is:

```text
concurrency × (input tokens + max output tokens)
```

Headroom:

```text
KV headroom tokens = total KV capacity - peak live KV tokens
KV utilization     = peak live KV tokens / total KV capacity
```

For hybrid/linear-attention models, separately account for fixed per-sequence state caches and any layers that use conventional KV cache. Do not assume a standard transformer KV formula applies unchanged.

### 9.4 Identifying KV constraints

Suspect KV capacity as a limiting factor if:

- KV utilization approaches 90–100%;
- free blocks approach zero;
- preemption/recomputation appears;
- requests are rejected despite available compute;
- achievable concurrency changes sharply with context length;
- reducing maximum model length increases throughput or concurrency;
- lowering KV precision materially increases sustainable concurrency.

A throughput plateau by itself does not prove a KV constraint. Pair it with cache telemetry and queue behavior.

---


## R-05-6 — Deployment Topology Comparison

> Formerly `PROCEDURE.md` §10. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


For a model that fits on one GPU and four identical GPUs are available, compare at least these topologies.

### Topology A: one GPU, one replica

```text
benchmark client → mandatory load balancer → 1 replica; TP=1
4 GPUs available; 1 GPU used
```

Purpose: single-device baseline and scale-up denominator through the standard
instrumented request path.

### Topology B: four GPUs, four independent replicas

```text
4 replicas × 1 GPU each; TP=1 per replica
```

Place a load balancer in front of the replicas. Record routing policy:

- round robin;
- least outstanding requests;
- queue-aware;
- session/prefix affinity.

Measure aggregate and per-replica metrics. Ensure the benchmark’s concurrency is global, not multiplied accidentally per replica.

### Topology C: four GPUs, one distributed replica

```text
benchmark client → mandatory load balancer → 1 replica across 4 GPUs; typically TP=4
```

Record communication topology and TP/EP/DCP settings. This topology may improve single-request latency or make larger models possible, but communication overhead can reduce tokens/s per GPU.

### Topology D: two replicas across two GPUs each

```text
2 replicas × TP=2
```

This intermediate configuration often offers a latency/throughput compromise and should be included when supported.

### Fair comparison rules

For every topology:

- Route the benchmark client through the same mandatory load-balancer frontend,
  including one-backend topologies; never benchmark a backend directly.
- Use the same model revision and quantization.
- Use the same total number and type of GPUs.
- Use identical clocks and power limits.
- Use the same benchmark client and network path.
- Use the same request set or equivalent seeded random generation.
- Use the same input/output token distributions.
- Keep runtime settings equivalent unless topology requires a change; document every change.
- Warm each replica independently.
- Verify load is balanced across replicas.
- Measure aggregate throughput at the common front door.
- Also measure each replica separately to detect imbalance.

### Concurrency interpretation

Run global concurrency:

```text
1, 2, 4, 8, 16, 24, 32, 40, 48, 56, 64
```

For four replicas, also report average offered concurrency per replica:

```text
global concurrency / 4
```

Do not compare “concurrency 16 per replica” with “concurrency 16 total” without clearly labeling the difference.

### Metrics for topology comparison

For each topology and concurrency report:

- Aggregate generation TPS
- Aggregate prefill TPS
- TPS per GPU
- Requests/s
- TTFT p50/p95/p99
- ITL p50/p95/p99
- E2E p50/p95/p99
- Goodput under the chosen SLO
- Error rate
- Queue depth
- KV-cache peak and headroom
- GPU utilization balance
- GPU power and energy per million tokens
- Host CPU and RAM usage
- Inter-GPU bandwidth
- Passive PCIe RX/TX traffic, replay deltas, and link state
- NCCL collective latency, `algbw`, and `busbw` from campaign qualification
- Same-NUMA versus cross-NUMA fabric penalty
- Network bandwidth

Derived metrics:

```text
scale-out efficiency = throughput(4 × TP1 replicas) / (4 × throughput(1 × TP1))
scale-up efficiency  = throughput(1 × TP4 replica) / (4 × throughput(1 × TP1))
TPS per GPU           = aggregate TPS / GPU count
energy per 1M tokens  = average system watts × elapsed seconds / tokens × 1,000,000
```

### Expected questions the comparison should answer

- Does replication maximize aggregate throughput?
- Does TP reduce single-user latency enough to justify communication overhead?
- At what concurrency does each topology saturate?
- Which topology gives the best goodput under the latency SLO?
- Is traffic evenly distributed between replicas?
- Does each replica receive enough concurrency for efficient batching?
- Does TP increase available aggregate KV capacity, or only shard the same logical model/cache?
- Is PCIe/NVLink communication the distributed deployment’s bottleneck?
- Does host CPU, RAM bandwidth, or networking bottleneck four replicas?

---


## R-05-7 — Benchmark API Examples

> Formerly `PROCEDURE.md` §11. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


### Start a benchmark

```bash
curl -X POST "http://localhost:8437/api/inference-services/benchmark?name=<isvc-name>&namespace=inference" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "http://<isvc-name>-predictor.inference.svc.cluster.local:8080/v1",
    "concurrency": "1,2,4,8,16,24,32,40,48,56,64",
    "max_tokens": 500,
    "num_words": 50
  }'
```

### Check results

```bash
curl -s "http://localhost:8437/api/inference-services/benchmark?name=<isvc-name>&namespace=inference" | jq
```

### Delete a stuck job

```bash
curl -X DELETE "http://localhost:8437/api/inference-services/benchmark?name=<isvc-name>&namespace=inference"
```

### Inspect Kubernetes resources

```bash
kubectl logs -n inference job/benchmark-<isvc-name>
kubectl logs -n inference deployment/<isvc-name>-predictor --tail=200
kubectl top pod -n inference
kubectl describe pod -n inference <predictor-pod>
```

---


## R-05-8 — Manual TTFT Verification

> Formerly `PROCEDURE.md` §12. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


Use randomized text and streaming for independent TTFT validation:

```python
import secrets
import requests
import time

pod_ip = "<pod-ip>"
url = f"http://{pod_ip}:8080/v1/chat/completions"
random_text = secrets.token_hex(2000)

payload = {
    "model": "<model-name>",
    "messages": [{"role": "user", "content": f"Process: {random_text}"}],
    "max_tokens": 5,
    "stream": True,
}

start = time.perf_counter()
response = requests.post(url, json=payload, stream=True, timeout=300)
response.raise_for_status()

for line in response.iter_lines():
    if line:
        ttft = time.perf_counter() - start
        break

count_payload = dict(payload)
count_payload["stream"] = False
r = requests.post(url, json=count_payload, timeout=300)
r.raise_for_status()
prompt_tokens = r.json()["usage"]["prompt_tokens"]

print(f"TTFT: {ttft:.3f}s")
print(f"Prompt tokens / TTFT: {prompt_tokens / ttft:.0f} tok/s")
```

Note that the second non-streaming request may hit prefix caching. Use a distinct random prompt for token counting, use the local tokenizer, or disable prefix caching when validating uncached prefill.

---


## R-05-9 — Result Artifacts

> Formerly `PROCEDURE.md` §13. Moved mechanically on 2026-09-06: text
> preserved, rule ID assigned in move order. Inner `§x.y` citations inside this
> block resolve via `harness/MOVED.md`.


The normative external root and naming contract are defined in `harness/5-formal-campaign/RULES.md`. Benchmark data must not depend on the runner's current working directory. Set and record `LLM_BENCH_RESULTS_ROOT` explicitly before a campaign. If a
runner offers a default, it must be user-independent (for example
`$HOME/llm-benchmark-results`) and record the resolved absolute path.

The canonical campaign path is:

```text
<results-root>/<host>/<model-slug>/<revision>/<deployment-id>/<campaign-id>/
```

Store every measured run in its own immutable timestamped directory. A run means one profile, one concurrency level, and one repetition. Warm-up belongs inside that run directory.

Canonical run layout:

```text
<campaign>/runs/<profile>/c<zero-padded-global-concurrency>/run-r<repetition>-<timestamp>-<run-id>/
├── manifest.json
├── launch-command.txt
├── environment.txt
├── model-files.txt
├── server-startup.log
├── benchmark-request.json
├── benchmark-result.json
├── requests.jsonl
├── summary.csv
├── gpu.csv
├── cpu.csv
├── memory.csv
├── network.csv
├── disk.csv
├── server-metrics.json
└── NOTES.md
```

Each run-level `summary.csv` contains one summary row. Also append that row to a campaign-level CSV:

```text
<campaign>/summaries/runs.csv
```

The campaign CSV is the main tabular dataset used to compare profiles, concurrency levels, and repetitions. Include `campaign_id`, `run_id`, `repetition`, `start_time`, `end_time`, and the artifact-directory path in every row. Keep raw request data and telemetry alongside the run so every summary value can be audited.

Generate campaign charts in:

```text
<campaign>/charts/
```

Never overwrite a prior run. Use UUID/ULID run IDs, timestamps, and immutable finalized manifests. Write phase-boundary manifest updates atomically (temporary file plus rename). CSV is the standard summary format, while JSON/JSONL and telemetry exports retain the raw detail.

---



## R-05-10 — Artifact layout

> Formerly `harness/5-formal-campaign/RULES.md`, moved verbatim on 2026-09-06 so this chapter owns it.

#### Benchmark Artifact Layout

## Canonical external root

Benchmark results are not committed to this repository. Every runner must use:

```text
${LLM_BENCH_RESULTS_ROOT:-$HOME/llm-benchmark-results}
```

A runner must print and record the resolved absolute root before performing any
warm-up or measurement. It must not infer the root from its current working
directory.

## Canonical campaign path

```text
<results-root>/<host>/<model-slug>/<revision>/<deployment-id>/<campaign-id>/
```

Example:

Illustrative example:

```text
$HOME/llm-benchmark-results/
  gpu-host-01/
  example-model/
  0123456789ab/
  r2-tp4-pp1-dcp1-ep1-cfg-a4c92f10/
  20300102T030405Z-capacity-01EXAMPLE.../
```

### Components

- `host`: lowercase stable hostname, not an IP address.
- `model-slug`: lowercase repository/model name normalized to `[a-z0-9._-]`.
- `revision`: first 12 characters of the pinned immutable model commit. Never
  use `main` here.
- `deployment-id`: explicit stable slug identifying the frozen topology and
  capacity configuration. Do not derive it from a checksum.
- `campaign-id`: UTC basic timestamp, purpose (`qualification`, `capacity`,
  `long-context`, `fabric`, or another documented purpose), and ULID/UUID.

A capacity-affecting change creates a new `deployment-id`. Examples include
model revision, quantization, runtime image, replica count, TP/PP/DCP/EP,
GPU allocation, maximum model length, `max_num_seqs`, batched-token budget,
GPU-memory utilization, KV dtype/offload, speculative configuration, graph
settings, and CPU/NUMA placement.

## Campaign tree

```text
<campaign>/
├── campaign-manifest.json
├── deployment.json
├── deployment-capacity.json
├── environment.json
├── source-pointers.json
├── progress.log
├── preflight/
├── fabric/
├── idle/
│   ├── b0-unloaded/
│   ├── b1-pre-loaded/
│   └── b1-post-loaded/
├── runs/
│   ├── decode/
│   │   └── c0064/
│   │       └── run-r01-20260829T100000Z-<run-id>/
│   │           ├── manifest.json
│   │           ├── warmup/
│   │           ├── measured/
│   │           └── telemetry/
│   ├── prefill/
│   └── balanced/
├── summaries/
├── charts/
└── CAMPAIGN_COMPLETE
```

B0 and B1 are idle deployment-state baselines, not concurrency points. Never
store them under `runs/`, label them C0, or assign request throughput/latency
values to them. `b1-pre-loaded` is the workload-subtraction reference;
`b1-post-loaded` is the drift check.

Concurrency is zero-padded to four digits (`c0001`, `c0064`, `c0512`) so lexical
and numerical order agree. Repetitions are two digits (`r01`). Warm-up is part
of the same immutable run directory as its measurement; it is not a peer run.

`CAMPAIGN_COMPLETE` is written last and only after post-idle capture, telemetry
exports, manifest finalization, and integrity checks succeed.

## Immutability and resume rules

- Never overwrite a finalized run.
- A partially completed run may resume only if its manifest and phase markers
  match the exact deployment/configuration hashes.
- Otherwise create a new run ID.
- Write JSON atomically with temporary-file plus rename.
- Store absolute and root-relative artifact paths in manifests.
- Symlinks such as `latest` or `current` may exist for operator convenience but
  are never authoritative and must not appear as provenance.

## Legacy campaigns

Existing campaigns remain in their original locations and are referenced by a
legacy registry; do not move them while services or analysis jobs may hold open
paths. New campaigns must use the canonical root. A migration tool may later
copy legacy campaigns, verify hashes, and leave pointer files, but must never
silently rename them.

## Committed study records and campaign pointers

Repository placement is **derived from the pipeline**: a chapter's documents live in
`harness/<n>-*/`, everything else is a record under `results/`, and the retired layout
document lives in `results/xe7740-8x-rtx6000/journal/retired/`. Information
specific to a study, host, or campaign belongs under `results/<study-id>/`, not
in generic methodology. The repository may commit a small campaign pointer at:

```text
results/<study-id>/campaigns/<campaign-id>.yaml
```

It may contain:

- campaign and study IDs;
- host and model identity;
- external absolute path or object-store URI;
- schema version;
- completion-marker name;
- completion status.

Benchmark outputs and campaign pointers do not require checksums. Cryptographic
checksums are reserved for downloaded model data; see `harness/1-model-qualification/RULES.md`.

Study directories may also contain frozen configurations, host snapshots,
dated journal entries, and TODOs. They must not contain raw benchmark results.


## R-05-11 — Idle baseline capture (formerly `PROCEDURE.md` §7.1)

> Definitions live at `R-02-7` in chapter 2; what follows is the capture procedure only.
> Moved verbatim 2026-09-06.


Idle baselines are deployment states, not concurrency points. Do not label them
C0, include them on concurrency axes, or assign request latency/throughput values
to them. Request metrics for B0 and B1 are **not applicable**, not zero.

- **B0 — unloaded idle:** observability and the mandatory load balancer are
  running, no inference/model process has allocated GPU memory, no benchmark
  requests are sent, and the GPUs are otherwise idle. Confirm idleness from GPU
  power draw and allocated frame memory; utilization percentage can remain
  saturated while a server spins on CUDA graphs or asynchronous scheduling. A one-backend load
  balancer may report that backend unavailable until model startup.
- **B1-pre — loaded idle before measurement:** the exact frozen model/runtime is
  loaded and healthy behind the load balancer, CUDA-graph capture and startup
  work have completed, requests have drained, and no benchmark traffic is sent.
  Capture this before campaign warm-up.
- **B1-post — loaded idle after measurement:** the same model/runtime and load
  balancer remain running after all measured requests and telemetry exports have
  drained. This identifies thermal drift, leaks, or persistent state changes.

Record start/end timestamps, duration, deployment/container identities, model-
loaded assertion, no-request assertion, backend health, and telemetry
availability for every baseline. Collect the same host/GPU/network telemetry as
for measured runs, including GPU power/utilization/temperature/clocks/VRAM,
CPU/RAM, disk, PCIe endpoint rates and replay counters, HAProxy traffic,
container/interface traffic, and serving/KV state where applicable.

Use the baselines to report:

```text
model residency cost       = B1-pre − B0
incremental workload value = measured operating point − B1-pre
post-campaign drift         = B1-post − B1-pre
```

Compute differences only for metrics with compatible scope and units. For
counter-derived rates, compare rates over the baseline windows rather than raw
counter values. If B0 cannot be captured without disrupting an already active
campaign, do not stop the service mid-campaign: record B0 as unavailable and
capture it only after safe campaign closeout, explicitly labeling it
post-campaign and order-confounded.

Suggested request counts:

```text
warm-up requests  = min(max(4, 2 × concurrency), warm-up cap)
measured requests = max(32, 4 × concurrency)
```

For inference deployments with a known sequence-admission limit, set the
warm-up cap near `2 × max_num_seqs` (for example, 64 when
`max_num_seqs = 32`). This exercises multiple scheduling cycles without
creating an unnecessarily long warm-up queue. Record the cap in the immutable
campaign specification; do not introduce or change it after a campaign starts.
Omit the cap only when qualification demonstrates that a larger warm-up is
necessary.

Longer measured runs are preferable when tail latency and throttling matter.

---



## Remaining tasks in this chapter

- Collapse former §13 and `harness/5-formal-campaign/RULES.md` into one record contract; the loser becomes
  a reference.
- Reduce idle-baseline capture (former §7.1, still in `PROCEDURE.md`) to a reference to
  `R-02-7` plus capture steps only, then remove it from the legacy file.
- Make the chapter-mirrored campaign directory (`5-campaign/`) the single evidence root, so a
  missing gate becomes an empty directory instead of a prose absence.
- Split `R-05-8` (benchmark API examples) into tool documentation if it is how-to rather than
  normative; a `RULES.md` should not carry example code that nothing enforces.

## R-05-12 — Judge a candidate by artifacts found, not by a remembered layout or schema — 5

Two failures share one root: counting measurements under a hard-coded relative path, and parsing a
single assumed JSON shape. Both produce *silence*, which reads exactly like absence — a generation
containing fourteen complete results was nearly reported as a null result because the counter
looked in `points/cN/` while the harness wrote `decode-CN/repN/`, and a schema-1.4 export with a
flat `output_token_throughput.avg` parsed to nothing under a `results[0].metrics...` reader. A
candidate summary must discover measurement artifacts by filename anywhere beneath the candidate
directory, accept every export shape the installed tool version can emit, and treat "artifacts
present but zero values parsed" as a **validator defect**, never as a result.

## R-05-13 — Completed runs leave the host as they complete, not at the end

A campaign's evidence exists in exactly one place until it is copied: the machine doing the computing
is the only machine holding the result, and it is the machine most likely to be reclaimed, rebooted or
network-isolated during a multi-hour run. On 2026-09-07 the host lost its network path for roughly three
hours mid-campaign; 55 runs completed inside that blind window, the campaign finished, and **nothing in
the tooling detected the loss** - it was found by a human asking for status. The artifacts survived only
because the disk did.

Mirror each completed run, or at minimum each completed point, off the host as it finishes. Treat a
results root on the compute host as a single point of failure, not a default. _Source: formal campaign
`20260907-glm53-radixark-formal`, 2026-09-07._

## Sub-step budgets

One budget per sub-step: **wall-clock minutes**. B = blocking, charged in full;
O = off-path, must be scheduled inside a measurement window. Rules and breach protocol: `PIPELINE.md`.

| Sub-step | Owner | Path | Budget |
|---|---|---|---|
| freeze contract, spec validation | mech | B | 5m |
| full grid, 3 reps, front-end boundary | mech | B | planned, see formula |
| B1-post idle baseline | mech | B | 10m |
| mid-campaign tuning request | **forbidden** - escalate, do not act | B | 15m |

### R-05-14: Prefill measurements carry a measured cache verdict
* Every prefill run in a formal campaign is produced by `R-03-28` and must end with a gate
  verdict of `cold` recorded in the run's progress log.
* A run whose measured served-prompt fraction exceeds the limit, or whose counters are
  absent, is `INVALID` and the campaign halts rather than continuing to collect warm data.
* Cache-served prefill data is preserved and labelled, never edited into a cold result
  (R-PIPE-4). A campaign may report both series; they answer different questions.

### R-05-15: R-PIPE-8 case log -- mutations verified by re-reading

Recorded here because these are the failures the rule was abstracted from, and a rule without
its case history gets re-litigated:

* `git mv` followed by `git add` reported success while the file was deleted in the worktree
  and still staged.
* A path edit reported success while one literal remained unmatched in the same file.
* `rm -f ABORTED` succeeded while the marker's real name was `ABORTED.invalid-harness-defect`.
* `git rm` on a mismatched path (a file had been renamed to `test/TEST-KEEP-*.py` by a test)
  no-oped and still printed a commit message claiming it was archived.
* A campaign script written in place left two harness generations, two output trees and two
  completion markers, and a rerun silently appended to the interrupted tree.

Every one was caught by reading the effect (status, `find`, marker inventory) rather than the
exit code. The same discipline applied to measurement semantics produced `R-05-14`.

### R-05-16: Mirror whole run directories, then re-verify by digest after the run closes

A mirror taken while a run is still writing is a snapshot of a partial artifact, and it is
indistinguishable from a complete one until someone compares it to the source after completion.
The watcher's mid-run copies of two prefill runs had shorter logs than the node's finished
directories, and my own verification of that difference was defective twice over: `cmp -s` calls
directories "differing" while hiding its error text, and a whole-output string comparison
reported a mismatch that per-file SHA-256 showed did not exist.

* Copy whole run directories, not the handful of filenames the checker happens to read.
* Re-verify after completion with per-file digests against the source host, keeping the node as
  authority and recording which copy was installed where.
* Never claim a cleanup in a commit message that the command output does not show. R-PIPE-8
  applies to my own descriptions of my own commands, including after the fact.

### R-05-17: The benchmark instrument must collect the sampling contract, and missing data stays visible

The cold-input client measured throughput and validated cache state and nothing else, so the
report it produced had empty power, energy, VRAM, temperature, CPU and RAM panels. The proposed
fix -- omit panels whose metric was not sampled -- was rejected: hiding the error is not a
solution. The failure belongs to the instrument, which was contracted to collect hardware
telemetry per run and did not.

* An instrument is complete only when it collects everything the report renders: per-run GPU
  power/utilisation/VRAM, host RAM, and the campaign's fabric snapshot. Throughput-only tooling
  is not a benchmark runner wearing a different hat.
* A panel with no data stays present and visibly without data. The gap is the finding.
* Missing collection is repaired by measuring again, not by changing what is displayed.
  Fix the instrument, re-run the campaign, leave the earlier incomplete artifacts in place as
  the record of what happened.

