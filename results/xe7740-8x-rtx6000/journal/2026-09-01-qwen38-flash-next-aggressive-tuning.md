# Qwen3.8-Flash-Next NVFP4 aggressive tuning journal

Date: 2026-09-01
Host: `xe7740-04`
Model: `RadixArk/Qwen3.8-Flash-Next-NVFP4`
Revision: `7b719225242aacd3dbd3f9407468c2ee9a9d2594`
Status: active qualification and tuning

## Objective

Find the highest stable whole-machine serving throughput for Qwen3.8-Flash-Next
on eight RTX PRO 6000 Blackwell 96 GB GPUs. The intended production topology is
four independent TP2 replicas behind HAProxy. Conservative settings are loader
and correctness gates only; they are not accepted as hardware-capacity results.

## Model and runtime provenance

Model acquisition and validation:

```text
remote files: 419
remote bytes: 135,253,622,894
indexed tensors: 296,475
safetensors shards: 206
upstream LFS SHA-256 values checked: 208
missing files: 0
size mismatches: 0
hash mismatches: 0
```

Required runtime identity supplied by the operator:

```text
lmsysorg/sglang:qwen38flashnext
OCI index digest: sha256:12d3392bdc8be8d35e9a95f191df6aef99c5114bdbefd41bfdc7e760e6d25ec1
SGLang base commit: d91c3682b0b429e4c70df63cd57f819588ce29b0
```

The day-0 image excludes exact SM120 from the working TRT-LLM QSA decode path.
The launch applies a fail-loud source edit that changes the guard from SM100
only to SM100 or SM120. The source import and guard must each match exactly once
before replacement.

PLE host offload is explicitly disabled:

```text
--no-ple-offload-embedding
```

The complete PLE table therefore remains GPU resident.

## Baseline and host-memory correction

Before Qwen launch, four root-owned stale files were found:

```text
/dev/shm/vllm_offload_*.mmap
4 × approximately 49 GiB
```

No process mapped them. They were preserved in a removal receipt and deleted
through a root container sharing the host IPC namespace. Host used RAM dropped
from approximately 312 GiB to approximately 59–60 GiB; `/dev/shm` dropped from
approximately 196 GiB to approximately 30 MiB. This confirmed that the previous
high host-RAM reading was stale-runtime contamination, not current model
residency.

Mandatory Qwen B0 unloaded idle completed for 300 seconds with HAProxy running
and no model backend. B1-pre loaded idle later completed after four TP2 replicas
were loaded.

## HAProxy and backend validation

Request path:

```text
AIPerf → HAProxy leastconn :8000 → TP2 backends :8101–:8104
```

Each backend passed a direct OpenAI-compatible generation check. A 16-request
HAProxy burst changed directional byte counters on all four backends:

| Backend | Bytes in delta | Bytes out delta |
|---|---:|---:|
| qwen_a | 1,098 | 2,741 |
| qwen_b | 1,098 | 2,772 |
| qwen_c | 1,097 | 2,778 |
| qwen_d | 1,098 | 2,770 |

The exporter response-total series selected for the first check did not change;
directional backend byte counters proved distribution and are authoritative for
that gate.

Important operational finding: `GET /health` in this SGLang build performs a
64-token generation. It is not a passive health probe. HAProxy was changed to
TCP backend checks; readiness uses TCP plus a single `/v1/models` request.

## Failed and rejected candidates

### 1. Day-0 runtime with FP8 KV

Result: failed during QSA warm-up/CUDA graph capture; no OOM.

```text
AssertionError: q.dtype torch.bfloat16 != k.dtype torch.float8_e4m3fn
```

Cause: the pinned day-0 image lacks the later QSA FP8-KV dequantization fix.
FP8 KV remains a deferred runtime-upgrade candidate, not a valid setting for the
current pinned image.

### 2. Day-0 runtime with BF16 KV but without SM120 guard edit

Result: failed during FA4/CuTe compilation; no OOM.

```text
MLIRError: expects coord and shape of view are weakly congruent
```

Cause: exact SM120 was excluded from the working TRT-LLM QSA path and fell into
the broken generic FA4/CuTe fallback.

### 3. Incorrect alternative image selection

An unrelated alternative image pull was started, then cancelled before use when
the operator supplied the exact required runtime and launch recipe. It is
recorded as rejected and was never used for measurements.

### 4. B/C/D Docker GPU visibility mistake

Docker `--gpus device=<host pair>` remapped each selected pair to container-local
CUDA devices 0 and 1. Setting `CUDA_VISIBLE_DEVICES` to the host indices inside
those containers hid every accelerator. B/C/D failed before model load with:

```text
RuntimeError: No accelerator ... is available
```

The correction removed `CUDA_VISIBLE_DEVICES` from B/C/D.

### 5. Redundant patch assertion in cloned launch scripts

The committed local image already contained the SM120 source edit, but B/C/D
clone scripts accidentally retained the fail-loud source assertion. An earlier
`sed` removed `set -e` instead of the assertion, allowing startup after the
assertion traceback. These launch receipts were classified invalid and B/C were
relaunched with clean scripts.

### 6. Broad graph-batch-1 qualification

The initial known-working deployment used:

```text
4 × TP2
NEXTN 3/1/4
max-running-requests requested: 96/replica
decode graph max batch: 1
max Mamba cache size: 16
```

The broad qualification was intentionally superseded after 15/24 real runs.
There were no OOMs or request errors, but Decode plateaued near 240 output tok/s
and queue latency became extreme. Representative results:

```text
Decode C1:  156.81 output tok/s
Decode C32: 232.20 output tok/s, TTFT p95 65.8 s
Decode C64: 239.91 output tok/s, TTFT p95 157.4 s
```

This was not a hardware limit.

## Critical hidden-cap finding

SGLang uses five Mamba state slots per active request for this target plus
NEXTN configuration. With:

```text
--max-mamba-cache-size 16
```

the runtime silently capped each TP2 replica to:

```text
floor(16 / 5) = 3 active requests
```

The runtime explicitly logged:

```text
max_running_requests is capped to 3 by the mamba state cache
```

This cap, combined with decode graph batch 1, explains the disastrous initial
throughput plateau. Requested `max-running-requests=96` was not the actual
admission ceiling.

## First genuinely wide TP2 candidate

Configuration A:

```text
one TP2 replica on GPUs 0–1
NEXTN 3/1/4
max Mamba cache size: 160
actual max running requests: 32
decode target-verify graph batches through 32
mem-fraction-static: 0.95
context: 262,144
PLE GPU-resident
BF16 KV
```

Confirmed runtime state:

```text
Mamba cap: 32 active requests
captured target-verify graph batches:
1,2,3,4,5,6,7,8,10,12,14,16,18,20,22,24,26,28,30,32
KV capacity: 1,206,144 tokens
```

Short direct single-TP2 Decode results:

| Concurrency | Output tok/s | Per-user tok/s | TTFT p95 | Average ITL | Errors |
|---:|---:|---:|---:|---:|---:|
| C8 | 586.96 | 96.93 | 1.467 s | 10.46 ms | 0 |
| C16 | 928.08 | 71.25 | 1.711 s | 14.33 ms | 0 |
| C24 | 1,160.90 | 60.36 | 0.847 s | 17.05 ms | 0 |
| C32 | 1,274.77 | 51.51 | 0.483 s | 20.16 ms | 0 |

This transformed performance and proved the earlier approximately 240 tok/s
plateau was configuration-bound.

## Parallel aggressive candidate matrix

The operator approved testing four disjoint TP2 candidates concurrently to
measure realistic whole-machine contention and accelerate selection.

| Candidate | GPUs | Speculation | Requested/actual active requests | Graph max | Mamba cache | KV tokens |
|---|---|---|---:|---:|---:|---:|
| A | 0–1 | NEXTN 3/1/4 | 32 / 32 | 32 | 160 | 1,206,144 |
| B | 2–3 | NEXTN 3/1/4 | 48 / 48 | 48 | 240 | 906,624 |
| C | 4–5 | NEXTN 3/1/4 | 64 / 64 | 64 | 320 | 607,104 |
| D | 6–7 | disabled | 64 requested / 19 actual | 64 requested | 96 | 1,758,144 |

Confirmed graph capture:

- A target-verify graph batches through 32.
- B target-verify graph batches through 48.
- C target-verify graph batches through 64.
- D was capped to 19 active requests by Mamba cache; it is not a valid 64-wide
  no-spec candidate in its current form.

All four candidates loaded without OOM. At the time of this journal creation,
a concurrent C32 Decode test was running against ports 8101–8104. Its results
must be appended from:

```text
/home/demouser/llm-benchmark-results/xe7740-04/qwen3.8-flash-next-nvfp4/7b719225242a/qualification-4xtp2/20260831-qwen38-flash-next-qualification/tuning/parallel-aggressive/parallel-c32-summary.json
```

## Evidence paths

Primary qualification root:

```text
/home/demouser/llm-benchmark-results/xe7740-04/qwen3.8-flash-next-nvfp4/7b719225242a/qualification-4xtp2/20260831-qwen38-flash-next-qualification
```

Superseded broad qualification:

```text
/home/demouser/llm-benchmark-results/xe7740-04/qwen3.8-flash-next-nvfp4/7b719225242a/r4-tp2-nextn3-seq96-graph1-b32768-sglang-sm120/20260901-qwen38-flash-next-4xtp2-qualification
```

Key subdirectories:

```text
canary/
tuning/graph32-mamba160/
tuning/parallel-aggressive/
preflight/backend-validation/
idle/b0-unloaded/
idle/b1-pre-loaded/
```

## Parallel C32 whole-machine result

All four TP2 candidates were benchmarked concurrently at C32 each, for global
offered concurrency C128. All AIPerf processes completed with exit code 0, zero
request errors, and no container OOM.

| Candidate | Configuration | KV-cache capacity | Output tok/s | Per-user tok/s | TTFT p95 | Average ITL | Errors |
|---|---|---:|---:|---:|---:|---:|---:|
| A | NEXTN, graph32, Mamba160, actual seq32 | 1,206,144 tokens | 1,324.87 | 50.31 | 0.458 s | 20.66 ms | 0 |
| B | NEXTN, graph48, Mamba240, actual seq48 | 906,624 tokens | 1,240.08 | 50.17 | 1.810 s | 20.63 ms | 0 |
| C | NEXTN, graph64, Mamba320, actual seq64 | 607,104 tokens | 1,247.06 | 49.41 | 1.979 s | 20.79 ms | 0 |
| D | no speculation, Mamba96, actual seq19 | 1,758,144 tokens | 985.30 | 61.87 | 10.887 s | 16.18 ms | 0 |

Aggregate whole-machine output throughput:

```text
4,797.31 output tokens/s at global offered C128
```

Candidate A was the strongest at this operating point despite narrower admission
and graph coverage. B and C provided more configured headroom but lower C32
throughput under simultaneous host contention. D was not a valid graph64/seq64
comparison because Mamba cache silently capped it to 19 active requests.

The benchmark orchestration wrapper remained alive after all AIPerf jobs exited
because a bare shell `wait` also included its `tee` process substitution. The
wrapper was terminated only after verifying four exit-code-zero receipts and all
four result JSON files; measurements were complete and unaffected.

## Final short comparison and promotion

A final contention-aware comparison tested candidate widths and a fair matched
no-speculation configuration:

| Candidate | Test | Result | Interpretation |
|---|---|---:|---|
| A | NEXTN, seq32/graph32 at C32 | 1,334.11 output tok/s | Stable |
| B | NEXTN, seq48/graph48 at C48 | **1,605.02 output tok/s** | Highest stable absolute throughput; promoted |
| C | NEXTN, seq64/graph64 at C64 | Failed; HTTP 500/timeouts and SIGQUIT, no OOM | Disqualified as unstable |
| D | No speculation, seq32/graph32 at C32 | 1,466.41 output tok/s | 9.9% faster than matched NEXTN A at C32 |

Candidate B was promoted because it delivered the highest stable absolute
throughput. The no-speculation result establishes that NEXTN is not universally
beneficial at matched C32 width, but no-speculation was not yet tested at a
stable width above 32. C demonstrated that graph/admission width 64 exceeded a
stable runtime boundary for this configuration despite fitting in memory.

The ideal homogeneous four-replica scaling hypothesis for B is:

```text
4 × 1,605.02 = 6,420.08 output tok/s
```

This is a hypothesis, not a result. A previous heterogeneous simultaneous C32
run measured 4,797.31 output tok/s. The promoted homogeneous deployment must be
measured globally to quantify shared-host scaling efficiency.

Promoted deployment under test:

```text
4 × TP2
NEXTN 3/1/4
48 active requests per replica
Mamba cache 240 per replica
decode graph batches through 48
KV capacity 906,624 tokens per replica
global active-sequence ceiling 192
```

The global promotion test uses C64, C96, C128, and C160. These are below the
C192 aggregate ceiling and locate the throughput knee without immediately
repeating the unstable per-replica C64 condition.

## Current interpretation

1. Four TP2 replicas fit with the complete PLE table on GPU.
2. The primary decode limiter was not model size, PCIe, or GPU count; it was an
   unnoticed Mamba-state admission cap plus insufficient graph width.
3. Candidate A already exceeds 1,270 output tok/s on one TP2 pair at C32.
4. Wider B/C candidates trade KV capacity for admission and graph width. Their
   value must be judged under concurrent whole-machine load.
5. Requested configuration values are not authoritative. Every candidate must
   preserve runtime logs proving actual Mamba admission and captured graph
   batches.
6. No formal campaign should begin until the winning graph/Mamba/NEXTN setting
   is selected and cloned consistently across all four TP2 replicas.
