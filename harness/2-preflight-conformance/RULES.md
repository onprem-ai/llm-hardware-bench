---
kind: rule
step: 2
title: Preflight and conformance rules
absorbs:
  - PROCEDURE.md §1 Goals, §2 Terminology and Metric Definitions
  - PROCEDURE.md §4 Preflight Checks, §4.1 Background-load qualification
  - harness/2-preflight-conformance/RULES.md (availability tiers, collection rules, scope semantics)
  - harness/2-preflight-conformance/RULES.md (grid selection rule; the frozen grids are per-host
    instance data at `results/<host>/concurrency-grids.yaml`, and the instrument ships only a
    clearly-toy example at `harness/2-preflight-conformance/code/examples/concurrency-grids.toy.yaml`)
---

# Chapter 2 — Preflight and workload conformance

Pipeline order, budgets and gates: `PIPELINE.md`. This chapter fixes **what will be
measured, in what units, against which toolchain and workload**, and proves the machine is
fit to measure it. Everything downstream ranks or reports against definitions frozen here.

Ownership split that matters in practice: **this chapter owns the definition of a baseline;
chapter 5 owns capturing it.** A definition restated in chapter 5 is a bug (`R-PIPE-1`).

## What this chapter produces

`preflight.json` in the campaign root:

```json
{"verdict": "PASS | PASS_WITH_EXCEPTION | FAIL",
 "workload":    {"workload_id": "...", "corpus_sha256": "...", "cache_policy": "disabled|measured"},
 "toolchain":   {"image_ref": "...", "image_digest": "sha256:...", "model_revision": "..."},
 "ambient":     {"cores_busy": 0.0, "bounded": ["obs-cadvisor=4"], "documented": []},
 "comparators": [{"id": "...", "resolved_value": 0.0, "artifact": "..."}],
 "exceptions":  ["..."]}
```

A `FAIL` stops the campaign. `PASS_WITH_EXCEPTION` requires every exception written down
with the number it affects — an undocumented exception is how a defect becomes a result.

## Objectives

### R-02-1 What every deployment measurement must answer

Single-request generation speed; aggregate generation throughput as concurrency rises;
isolated prefill throughput as concurrency rises; TTFT, ITL and end-to-end latency; the
concurrency maximising useful throughput without unacceptable queuing; KV-cache capacity
available and consumed; which resource limits performance (KV capacity, compute, memory
bandwidth, communication, CPU, RAM, network, scheduler); the effect of topology (one
replica per GPU, many one-GPU replicas, one replica across GPUs, distributed replicas where
hardware permits); performance per GPU, per watt, per dollar where power and cost exist;
application network traffic across the mandatory load-balancer boundary as directional
throughput and bytes per successful request.

## Metric definitions — the frozen contract

### R-02-2 Definitions

- **Generation/decode throughput** — output tokens per wall-clock second. Report aggregate
  generation TPS (output tokens of completed requests ÷ measured interval) *and* per-request
  generation rate from a benchmark-provided ITL-based metric. Do not divide aggregate TPS by
  configured concurrency when requests are not continuously active.
- **Prefill throughput** — input tokens ingested per second. For isolated prefill use large
  randomised prompts and very short outputs. From TTFT, either subtract a measured fixed
  overhead or label the value `prompt tokens / TTFT`; never call it "pure prefill TPS".
  AIPerf end-to-end `input_tok_s` on a balanced workload is arrival/completion throughput
  for input tokens, affected by decode and scheduling.
- **Total token throughput** — `(input + output) / measured interval`, always reported
  alongside input and output TPS separately.
- **TTFT** — dispatch to first token, including network, queueing, prefill, scheduler delay
  and the first decode step.
- **ITL / TPOT** — streamed inter-token latency; time per output token after the first.
  Report average and p50/p95/p99 where available.
- **Request throughput** — completed requests/s; comparable only at constant input and
  output lengths.

### R-02-3 Measurement scopes are not interchangeable

The standard path is `AIPerf → HAProxy → model server(s)`. AIPerf measures client-observed
throughput, TTFT, ITL, end-to-end latency and errors. HAProxy is the mandatory common
request boundary and measures proxied traffic, sessions, queues, retries and backend
distribution. Host/NIC collectors measure named loopback, bridge or physical interfaces.
DCGM measures GPU PCIe endpoint traffic. Complement, never substitute.

### R-02-4 Goodput

Throughput satisfying explicit SLOs (e.g. TTFT p95 ≤ 5 s, ITL p95 ≤ 100 ms, error rate ≤
0.1%). The highest raw TPS is not automatically the best production operating point, and a
peak bought with latency must be reported as a set of operating points, not one headline.

### R-02-5 Availability tiers

- **Required** — campaign invalid without: request timings/counts, actual token counts,
  errors, GPU memory/utilisation/power, host CPU/RAM, deployment identity, KV capacity and
  state, raw timestamps, load-balancer frontend/backend byte and request counters.
- **Required when supported** — PCIe RX/TX, replay counters, SM/tensor/DRAM profiling,
  energy counters, runtime scheduler/speculative metrics. Missing support must be recorded
  with probe evidence.
- **Qualification-only** — NCCL/P2P microbenchmarks, NUMA/UPI bandwidth, pinned vs
  unpinned comparisons.
- **Diagnostic** — Nsight, CUPTI, PMU, eBPF, kernel and allocator traces.

### R-02-6 Collection rules

Record metric name, source, unit, type, labels and scrape interval; preserve raw series with
exact measured-window timestamps; use rates/increases for cumulative counters with reset
detection, but never `rate()` on interval-average gauges such as DCGM PCIe throughput; never
convert absent, unsupported, permission-denied or conflicting metrics to zero; validate each
custom counter under controlled load before campaign start; do not combine differently scoped
values until labels and aggregation semantics are explicit; separate client-observed,
server-reported and derived metrics; profiling runs with material overhead are separate
experiments; every measured request traverses the load-balancer frontend even with one
backend — direct-backend campaigns do not satisfy this contract.

### R-02-7 Idle baseline definitions (capture is chapter 5)

- **B0 unloaded idle** — no model/inference process holds GPU allocations.
- **B1-pre loaded idle** — frozen model/runtime ready, startup complete, no requests; the
  active-workload subtraction reference.
- **B1-post loaded idle** — same deployment after measured requests drain; the drift check.

These are state baselines, not C0 workload points; request throughput and latency do not
apply. B1-pre − B0 is model-residency cost; operating point − B1-pre is incremental workload
cost; B1-post − B1-pre is drift.

### R-02-8 Metric-scope semantics that get confused

HAProxy frontend/backend, cAdvisor container, host-interface and physical-NIC RX/TX are
different scopes; derive directional MiB/s and bytes per successful request from exact
window counter deltas; never sum ingress and egress into one bandwidth number, and never
read same-host proxy/bridge/loopback traffic as physical-NIC usage. Despite its `*_BYTES`
name, `DCGM_FI_PROF_PCIE_RX/TX_BYTES` is an interval-average byte *rate* — export as a gauge
and integrate samples, do not `rate()` it. `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` is an
error/retry indicator, not bandwidth. NCCL `algbw`/`busbw` are collective metrics, not
directional PCIe payload rates. Metric availability is a state, not a numeric sample.

## Grid and workload

### R-02-9 The concurrency grid is frozen before any measurement

Formal global grid: `1, 8, 32, 64, 96, 128, 192, 256`
(`results/<host>/concurrency-grids.yaml`, frozen beside the study it planned). Exploratory rasters may use finer,
deployment-specific concurrency, but a formal campaign may not change its grid after
preflight, because a grid chosen after seeing results selects on noise.

### R-02-10 A workload must be identifiable, not just described

The campaign spec records `workload_id`, `corpus_sha256` and `cache_policy`. Prefix caching
is either disabled or deliberately tested and labelled; measured on 2026-09-06, a
synthetic short-prompt corpus with prefix caching enabled inflates input-token throughput
without bound, which is why two prefill "improvements" had to be withdrawn. Any comparison
across different `workload_id` or `cache_policy` values is invalid regardless of deployment
similarity.

## Environment gate

### R-02-11 Preflight checks (all 13, recorded, not remembered)

1. Benchmark clock synchronised; 2. no stale inference replicas on benchmark ports;
3. system and software inventory recorded; 4. adequate disk for model and logs;
5. expected model revision and downloaded-data checksum (`R-01-11`); 6. endpoint exposes
the intended model; 7. telemetry endpoint reachable; 8. load balancer healthy with every
backend in the expected state, including a one-backend deployment; 9. a controlled request
through the load-balancer endpoint demonstrably moves its frontend/backend byte and request
counters — **a direct-backend URL is a preflight failure**; 10. time synchronisation on
client and server; 11. dynamic power-management changes disabled or documented; 12. prefix
caching disabled or deliberately tested; 13. ambient background load quantified, then every
non-benchmark consumer bounded or documented (`R-02-12`).

Save command output under the campaign directory; terminal history is not evidence.

### R-02-12 Ambient background load is an experimental variable

Always-on telemetry agents, log shippers, indexers, backup daemons, scheduled jobs and other
tenants contribute CPU, memory-bandwidth, page-cache and interrupt activity to every
measured number. Before the first measured run: sample ≥ 10 s and record aggregate busy CPU
in cores, load average, top non-benchmark consumers, and per-container CPU with its cgroup
quota (`harness/2-preflight-conformance/code/check-host.sh`); require every non-benchmark consumer to be cgroup-bounded
or explicitly documented as intentional — an unbounded sustained multi-core consumer is a
preflight failure; evaluate the gate in an unmeasured state (preflight, B0 or B1), never
under generated traffic; exempt colocated serving and load-generation processes **by
explicit name**. Re-record ambient load in B0, B1-pre, B1-post and each run, and hold the
background environment constant across every member of a comparison set.

Two traps, both measured on this host on 2026-09-06:

- **Low queueing is not proof of no interference.** On a high-core host a background
  consumer can leave serving threads with no measurable runqueue wait while still
  pre-empting dispatch threads and inflating tail TTFT/ITL.
- **Attribution is not optional, and the obvious suspect may be wrong.** Ambient load was
  measured at 41.43 busy cores, 40.1 of them a single monitoring container — which turned
  out to be a *docker* container, not a systemd unit (`MainPID=0`), so a unit-based cap
  would have silently done nothing. Capping it to 4 CPUs moved ambient load to 4.79 cores and
  bought **+1.1% to +2.7%** throughput, not the 16% a remembered comparator had implied.
  The hypothesis "ambient load explains the gap" was tested and rejected; the gap itself
  turned out to be fabricated (see `R-PIPE-2`).

### R-02-13 Toolchain identity is pinned by digest, not tag

Record image reference *and* `@sha256:` digest, model revision (`R-01-1`), and the
launcher/tool hashes. A mutable tag is not an identifier: `:canary` on 2026-09-06 pointed at
whatever was built last, so two campaigns sharing a tag could share nothing.

### R-02-14 Comparators are resolved at preflight, not at reporting time

Any comparator a campaign intends to quote must be registered in `results/<host>/comparators.json` and
resolved during preflight, with the resolved value recorded in `preflight.json`. Resolving
late is how a remembered number survives into a published delta (`R-PIPE-2`).

## Client-side traps that produced wrong numbers

### R-02-15 Count tokens at the server

AIPerf against these runtimes requires `--use-server-token-count`; client-side tokenisation
of chat templates does not match the served tokenizer and silently changes input length.

### R-02-16 Assert units; never assume them

Exported JSON timing fields are in **milliseconds**. Assert the `"unit"` field rather than
inferring scale; a silently mis-scaled latency is invisible in a throughput headline.

### R-02-17 Timestamps must be locale-independent

`date --iso-8601=ns` emits a locale-dependent decimal separator; under some locales it
produces a comma inside a CSV field and corrupts the column. Use UTC with an explicit
format string.

### R-02-18 Measured-window class is part of every comparison

Results from different window regimes (e.g. 60 s × 2 vs 90 s × 3) are not comparable:
measured on 2026-09-06 at **+0.8%** on one configuration and **+3.1%** on another, which is
larger than most parameter effects in a decode raster. Record window and repetition count
alongside every value (`R-RASTER-15`).

## Exit gate — entering chapter 3

- [ ] `preflight.json` written with verdict, workload, toolchain, ambient, comparators
- [ ] metric definitions frozen and the decision metric named explicitly
- [ ] concurrency grid recorded and will not change
- [ ] all 13 preflight checks recorded; direct-backend path excluded by counter evidence
- [ ] every ambient consumer bounded or documented; ambient figure recorded
- [ ] workload identity (`corpus_sha256`, `cache_policy`) recorded
- [ ] intended comparators registered and resolved to values
- [ ] host-RAM allocation qualified (`R-02-18` companion evidence from chapter 1 runs)

## Sources

Rule IDs assigned 2026-09-06. `R-02-2`..`R-02-8` moved from `PROCEDURE.md` §2 and
`harness/2-preflight-conformance/RULES.md`; `R-02-11`/`R-02-12` from `PROCEDURE.md` §4/§4.1. `R-02-10`, `R-02-13`,
`R-02-14`, `R-02-15`..`R-02-18` are new, and each traces to a specific measured failure on
this host during the 2026-09-06 GLM-5.3 raster: two withdrawn prefill claims, a `:canary`
tag shared by unrelated campaigns, a fabricated comparator, an unscaled latency field, a
locale-corrupted CSV column, and a cross-window comparison that was 3.1% wide.

## R-02-19 — Environment prerequisites

> Formerly `harness/2-preflight-conformance/RULES.md`, moved verbatim on 2026-09-06 so this chapter owns it.

#### Clean-Machine Prerequisites

This document defines the host contract required before a benchmark campaign is
allowed to start. Installation and benchmarking are separate phases. Never
install packages, restart Docker, reload systemd, change clocks, or restart a
telemetry exporter while a measured campaign is running.

## 1. Supported host baseline

Required:

- Linux with a supported NVIDIA datacenter/workstation driver;
- x86-64 or another architecture explicitly supported by every selected image;
- NVIDIA GPUs visible to NVML and CUDA;
- local storage large enough for model, image layers, temporary files, and
  results with at least 15% free-space safety margin;
- stable hostname and synchronized UTC clock;
- root or controlled `sudo` access for one-time host setup and hardware
  inventory;
- an unprivileged benchmark operator with Docker access and write access to the
  external results root.

A study-specific host snapshot belongs in
`results/<study-id>/hosts/<host>.yaml`. Pin the actual versions in every
campaign manifest. Do not silently upgrade a qualified host between
repetitions.

## 2. Required host software

### Core operation

- `bash`, GNU coreutils, `findutils`, `util-linux`;
- `git`, `curl`, `jq`, `tmux`;
- Python 3.11+ and `venv`;
- Docker Engine with Compose plugin;
- NVIDIA driver, NVML tools (`nvidia-smi`), and NVIDIA Container Toolkit;
- `pciutils` (`lspci`), `numactl`, `hwloc`/`lstopo`;
- `sysstat` (`mpstat`, `pidstat`), `procps` (`vmstat`), `iproute2`, `ethtool`;
- `lsof`, `rsync`, and `zstd`.

### Benchmark and telemetry

- NVIDIA AIPerf in an isolated, pinned virtual environment;
- DCGM Exporter with a version-matched embedded DCGM library;
- VictoriaMetrics or a compatible Prometheus query-range store;
- node-exporter and cAdvisor;
- HAProxy when multiple replicas are load-balanced;
- a custom DCGM collector enabling supported PCIe/profiling fields;
- an external results directory as defined in `ARTIFACT_LAYOUT.md`.

### Fabric qualification

- CUDA toolkit matching the build requirements of the selected `nccl-tests`;
- NCCL library matching, or intentionally comparable to, the serving runtime;
- `nccl-tests` pinned to an immutable commit;
- CUDA Samples `p2pBandwidthLatencyTest` or an equivalent directional P2P tool;
- OpenMPI only when multi-process/multi-node `nccl-tests` require it.

### Optional deep diagnostics

- Intel PCM or architecture-equivalent memory/UPI tools;
- Linux `perf` with permission to access required PMUs;
- Nsight Systems and Nsight Compute;
- eBPF/BCC or bpftrace for scheduler, I/O, and networking investigations;
- `turbostat`/`cpupower` where supported.

Optional tools must never be represented as available merely because their
package is installed. Run a capability probe and record permission or PMU
limitations.

## 3. Version and image policy

`harness/2-preflight-conformance/code/configs/toolchain-policy.yaml` defines the generic identity requirements.
Observed versions belong in `results/<study-id>/hosts/<host>.yaml`; they are
historical evidence, not permission to use mutable tags.

For every campaign record:

- OS release and kernel;
- NVIDIA driver and firmware-visible GPU identity;
- Docker and NVIDIA Container Toolkit versions;
- inference image repository, immutable digest, image ID, and internal vLLM,
  PyTorch, CUDA, FlashInfer, NCCL, ModelOpt, and tokenizer versions;
- AIPerf version and Python lock hash;
- telemetry image digests;
- `nccl-tests` commit and compile command.

Never identify a runtime only by `latest` or a mutable tag.

## 4. NVIDIA container validation

Before installing benchmark services, prove GPU container access:

```bash
nvidia-smi
nvidia-ctk --version
docker info
docker run --rm --gpus all <PINNED-CUDA-IMAGE-DIGEST> nvidia-smi
```

Validate that all intended GPUs appear, their UUID/index mapping is stable, and
containers retain access after reboot. Be aware that daemon reloads can disrupt
GPU access on some systemd/cgroup configurations; do not reload system services
during a campaign.

## 5. Telemetry deployment

Deploy and pin:

- node-exporter;
- cAdvisor;
- DCGM Exporter with `CAP_SYS_ADMIN`, all GPUs, and the custom collector;
- VictoriaMetrics with persistent storage;
- HAProxy as a mandatory request-path boundary for every measured deployment,
  including one-backend deployments, with its Prometheus metrics endpoint
  scraped as a separate job.

The DCGM exporter image must pair a compatible exporter and DCGM version. A
custom collector file selects fields but does not guarantee hardware support.
Before a campaign:

1. list available fields/profiling groups using `dcgmi` inside the exporter or a
   matching DCGM utility container;
2. request the custom metrics;
3. verify that every required series is actually emitted;
4. run a short controlled GPU/PCIe load and verify that counters change;
5. record unsupported or conflicting metric groups;
6. ensure VictoriaMetrics retains samples long enough for delayed export.

Do not restart the exporter to add metrics after measured runs have begun.

## 6. Python benchmark environment

Create an isolated virtual environment and install from a lock file. At minimum
pin AIPerf and all direct/transitive dependencies that affect request generation,
tokenization, timing, and export.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install --require-hashes -r requirements.lock
.venv/bin/aiperf --version
```

The lock file, Python version, and hash must be preserved in the campaign.
Synthetic prompt generation must use an explicit seed.

## 7. Clock, power, and environmental stability

Required preflight:

- NTP/chrony synchronized; record offset, stratum, and source;
- GPU persistence mode and compute/MIG mode recorded;
- power limits and application clocks recorded;
- CPU governor, turbo state, and frequency policy recorded;
- no unexpected thermal, power, or reliability throttle state;
- ambient/inlet temperature recorded when available.

Do not change power limits, clocks, CPU governor, BIOS settings, or cooling policy
between repetitions unless the change defines a new deployment/configuration ID.

## 8. Privilege model

Document which steps require:

- Docker group access;
- passwordless or interactive `sudo`;
- `CAP_SYS_ADMIN` for DCGM profiling;
- access to `/dev/nvidia*`, PCI sysfs, PMUs, and tracefs;
- `perf_event_paranoid`/`kptr_restrict` changes;
- MSR access for PCM.

A bootstrap script may print required commands but must not perform privileged
mutations by default. Provide an explicit `--apply` mode for reviewed changes.

## 9. Network and storage

- Verify model download source, authentication, and pinned revision.
- Hash all model shards before qualification.
- Measure local filesystem capacity and mount options.
- Keep result writes off a congested or remote filesystem where possible.
- Verify benchmark client to load-balancer latency and available bandwidth.
- Configure one load-balancer backend even when only one model server exists;
  the benchmark client must never target that backend directly.
- Verify a controlled proxied request changes frontend/backend byte and request
  counters before measurement begins.
- Preserve separate scopes for HAProxy application traffic, container/bridge or
  loopback traffic, and physical-NIC traffic.
- Ensure firewall rules expose only required local/management ports.

## 10. Clean-machine workflow

1. Provision OS, firmware, driver, Docker, and NVIDIA Container Toolkit.
2. Reboot and verify all GPUs and topology.
3. Install non-GPU host tools.
4. Clone this repository at a pinned commit.
5. Run `harness/2-preflight-conformance/code/check-host.sh`; retain its JSON/text output.
6. Install/start observability using pinned images and custom metrics.
7. Verify metric availability and counter movement.
8. Build or install pinned `nccl-tests` and P2P tools.
9. Run idle and fabric qualification with no inference service active.
10. Create the pinned AIPerf environment.
11. Acquire and verify the model.
12. Qualify the serving topology and freeze its deployment ID.
13. Start the measured campaign.

A failure at any mandatory gate blocks campaign start. Optional unavailable
metrics are permitted only when explicitly recorded with a reason.

## R-02-20 — Concurrency grid design

> Formerly `harness/2-preflight-conformance/RULES.md`, moved verbatim on 2026-09-06 so this chapter owns it.

#### Designing an Eight-Point Concurrency Grid

## Purpose

Every primary capacity profile uses exactly eight **global offered client
concurrency** points. The grid must reveal:

1. single-user latency;
2. early batching gains;
3. the throughput knee;
4. the useful production region;
5. saturation;
6. queueing collapse or overload behavior.

The grid is global across the complete load-balanced deployment. It is not a
per-replica value and is not the same as `max_num_seqs`.

## Inputs

Record these inputs before freezing a grid:

- `G`: total GPUs;
- `T`: tensor-parallel GPUs per replica;
- `R = G / T`: independent replicas;
- `A`: active parameters per token; for a dense model, total parameters;
- weight precision and bytes resident per replica;
- speculative method and draft cost/acceptance;
- profile shape: input/output token distribution;
- `M`: qualified `max_num_seqs` per replica;
- `B`: maximum batched-token budget per replica;
- `K_profile`: KV/state-cache concurrency limit for the profile;
- `S_profile`: measured per-replica saturation concurrency;
- latency/error SLOs and load-balancer behavior.

Active parameter count is a useful prior for compute per token, but it is not a
complete cost model. Dense versus MoE execution, attention type, context,
quantization, kernel efficiency, TP communication, MTP acceptance, and memory
bandwidth can reverse a simple parameter-based prediction.

## Topology semantics

For `G` GPUs and `T` tensor-parallel ranks per replica, the nominal independent
replica count is `R = G / T` when `G` is divisible by `T`. Candidate layouts
range from one `TP=G` replica to `G` independent `TP=1` replicas, subject to
model fit, KV capacity, scheduler behavior, and topology.

Prefer replica GPU groups that stay within a PCIe/NUMA locality domain. A
cross-NUMA TP group must be explicitly qualified rather than assumed equivalent.
Record the actual GPU groups in the study configuration; do not assume a
particular GPU count or socket layout in the generic method.

## Qualification sweep

Do not derive the final grid from active parameters alone. First complete the
mandatory evolutionary deployment raster in `PROCEDURE.md`. The topology and
runtime settings entering grid design must be the strongest stable promoted
candidate, not merely the first loader configuration. Preserve requested versus
actual admission, graph, KV/state, and offload settings for every candidate.

Then run a short qualification sweep with the intended workload profiles and
promoted topology.

Recommended exploratory global points:

```text
1, R, 2R, 4R, 8R, 16R, 32R, 64R, ...
```

Continue until at least one of these is observed:

- aggregate throughput improves by less than 5% across two successive steps;
- p95 TTFT or ITL crosses the SLO;
- queue depth grows throughout the measured interval;
- active sequences approach `R * M`;
- KV/state-cache utilization approaches the approved safety limit;
- preemption, rejection, timeout, OOM, or instability occurs;
- the business-approved hard maximum is reached.

Measure saturation independently for decode, prefill, and balanced profiles.
The final common grid must cover the important knees of all three.

## Capacity anchors

Define:

```text
A_slots   = R * M
A_kv[p]   = qualified global KV/state-cache concurrency for profile p
S[p]      = measured global saturation knee for profile p
H         = approved hard offered-concurrency maximum
```

`H` may exceed `A_slots`. This is intentional when the study needs to expose
queueing and overload behavior. Queued client requests are not simultaneously
active model sequences.

Choose eight ordered points with these semantic roles:

1. **C1 — latency anchor:** always `1`.
2. **C2 — replica/batching anchor:** exercises multiple replicas or an early
   efficient batch; commonly `max(R, 4)` or `8`.
3. **C3 — low-load scaling:** below the earliest measured knee.
4. **C4 — first knee:** near the earliest profile saturation knee.
5. **C5 — production shoulder:** useful throughput before severe tails.
6. **C6 — near saturation:** near the strongest throughput region.
7. **C7 — overload shoulder:** queueing/tail-latency evidence.
8. **C8 — hard maximum:** `H`, including above-slot overload when approved.

Round to operationally legible values—usually powers of two or multiples of
`R`—without moving a point so far that it misses a measured knee. Never insert
points only to make a visually regular logarithmic series.

## Active-parameter prior

Before qualification, use active parameters only to select a broad search
range:

| Active parameters/token | Initial expectation on 8x high-end GPUs |
|---:|---|
| `<= 15B` | high concurrency; test through 512 or beyond if scheduler/KV permit |
| `15B–30B` | medium-high concurrency; test through 256–512 |
| `30B–50B` | medium concurrency; test through 128–256 |
| `> 50B` | begin conservatively but continue until measured saturation |

These are search priors, not reportable capacity claims. A dense 27B model and
an MoE with 27B active parameters do not necessarily behave alike. Likewise, a
small active MoE can still have expensive routing, communication, or attention.

## Topology adjustment

For otherwise similar per-replica behavior, the global saturation region tends
to scale with replica count:

```text
S_global approximately R * S_per_replica
```

Do not assume perfect scaling. Validate load-balancer distribution, CPU/network
capacity, PCIe/NCCL overhead, and per-replica batch formation. Increasing TP
may improve single-request latency while reducing aggregate replica count;
increasing replicas usually improves aggregate capacity but duplicates weights
and caches.

## Eight-point construction algorithm

1. Qualify the chosen topology and freeze all capacity-affecting settings.
2. Measure exploratory powers-of-two/multiples-of-`R` points for all profiles.
3. Estimate each profile's throughput knee and SLO boundary.
4. Set `H` at or above the highest business-relevant saturation/overload point,
   subject to safety gates.
5. Select eight points covering the semantic roles above.
6. Require C1 and H.
7. Require at least two points below the earliest knee, two around useful
   saturation, and two in the queueing/overload region.
8. Verify each point is global, unique, increasing, and compatible with all
   profiles.
9. Record the evidence and rationale in the campaign manifest.
10. Do not alter the grid after measured repetitions begin; a changed grid is a
    new campaign version.

## Study-specific grids

Store frozen grids and their rationale under
`results/<study-id>/configs/`. That record may include model names, parameter
counts, selected topology, qualification observations, and hard maxima. The
generic method intentionally contains no current-study grid.

## Manifest requirements

Every campaign manifest must record:

```yaml
concurrency:
  semantics: global_offered_client_concurrency
  grid: [1, 8, 32, 64, 128, 256, 384, 512]
  hard_max: 512
  topology:
    replicas: 2
    tensor_parallel_per_replica: 4
  active_parameters: 27000000000
  max_num_seqs_per_replica: 256
  aggregate_active_sequence_slots: 512
  qualification_evidence: qualification/summary.json
  rationale: "..."
```

Also preserve per-profile exploratory measurements used to identify the knees.
The grid is a documented experimental design choice, not an unexplained list.

### R-02-21 — What a study is for — 2

Determine how much prefill, generation, mixed, concurrency, context and energy-efficient capacity
the machine can serve; name the limiting component at each operating point; identify materially
underused or oversized components; turn that into sizing and topology recommendations. Per model
family, qualify plausible checkpoints, quantizations, KV formats, speculation settings and replica
layouts, select the best stable production-credible candidate, record the choice and rationale, and
run the repeated suite on that candidate. Preserve rejected candidates for audit, but do not present
implementation variants (FP8 versus NVFP4) as separate models unless the variant comparison *is* the
stated experiment. Separate model-dependent software or kernel limits from demonstrated hardware
limits.

A report answers: how much this hardware serves at defined latency and error SLOs; where saturation
begins; whether the limit is GPU compute, memory bandwidth, VRAM/KV, inter-GPU communication,
CPU/NUMA, RAM, network or load balancing, storage, power and thermals, or serving software; what
headroom remains elsewhere; and which topology and runtime settings suit latency-, throughput- and
long-context deployments.

## Sub-step budgets

One budget per sub-step: **wall-clock minutes**. B = blocking, charged in full;
O = off-path, must be scheduled inside a measurement window. Rules and breach protocol: `PIPELINE.md`.

| Sub-step | Owner | Path | Budget |
|---|---|---|---|
| B0 idle baseline | mech | B | 10m |
| ambient load sample and bound | mech | O | 10m |
| residue, ports, cgroup, host-RAM floor vs recorded | mech | O | 5m |
| workload conformance assertions (cache policy, token source, units) | mech | B | 5m |
| toolchain identity capture | mech | O | 5m |
| disqualify / document / accept decision | **agent** | B | 15m |
