# RadixArk GLM-5.3 seq64 / graph256 qualification finding

Date: 2026-08-31
Host: `xe7740-04`
Status: qualification evidence; one repetition per point

## Finding

Raising the active-sequence ceiling from 32 to 64, while increasing the MTP3
CUDA-graph capture ceiling from 128 to 256, materially increased decode
throughput above C32. This confirms that the prior `max_num_seqs=32` deployment
was a scheduler/deployment capacity limit rather than the server's final decode
throughput frontier for this request shape.

## Frozen candidate deployment

```text
Model: RadixArk/GLM-5.3-NVFP4
Revision: 363e8f086905afd83db356a620f9aa401c23800a
Runtime: Infernal Invocation r18
Topology: one TP8 replica
MTP: 3 speculative tokens
max_num_seqs: 64
max_cudagraph_capture_size: 256
max_num_batched_tokens: 8192
max_model_len: 262144
KV cache: FP8
GPU memory utilization: 0.95
```

For MTP3, the widest verification batch at 64 active sequences requires graph
width `64 × (1 + 3) = 256`.

## Qualification results

| Concurrency | seq32 / graph128 formal median | seq64 / graph256 qualification | Change |
|---:|---:|---:|---:|
| C32 | 639.34 output tok/s | 695.69 output tok/s | +8.8% |
| C48 | 578.56 output tok/s | 924.77 output tok/s | +59.8% |
| C64 | 588.97 output tok/s | 804.63 output tok/s | +36.6% |

Seq64 / graph256 latency results:

| Concurrency | TTFT p95 | Average ITL |
|---:|---:|---:|
| C32 | 2.37 s | 37.89 ms |
| C48 | 3.23 s | 47.13 ms |
| C64 | 3.88 s | 61.96 ms |

Operational result:

- 3/3 runs complete;
- zero failed attempts;
- zero request errors;
- no OOM;
- server remained healthy;
- peak qualification throughput occurred at C48: 924.77 output tok/s.

## KV-cache tradeoff

```text
seq32 / graph128: 568,576 tokens
seq64 / graph256: 545,216 tokens
change:             -23,360 tokens (-4.1%)
```

The graph-memory increase reduced KV capacity modestly, but the tested short
Decode workload used far less than total KV capacity. KV capacity did not
explain the previous plateau.

## Interpretation

The large C48 improvement demonstrates that requests above C32 were previously
queued behind the configured 32-active-sequence ceiling. Raising the ceiling
allowed a wider effective execution batch and moved the throughput frontier.
The decline from C48 to C64, together with higher ITL, suggests an execution-
efficiency optimum near C48 for this request shape, but one qualification run
per point is insufficient to establish a stable production result.

The C32 increase may reflect graph/deployment differences or normal single-run
variation and must be checked with repeated measurements.

## Evidence

```text
/home/demouser/llm-benchmark-results/xe7740-04/glm-5.3-nvfp4/363e8f086905/r1-tp8-dcp1-mtp3-seq64-b8192-graph256-r18/20260830-full-glm53-radixark-seq64-graph256-canary
```

Markers and state at inspection:

```text
campaign status: runs_complete
RUNS_COMPLETE: present
complete operating points: 3/3
failed attempts: 0
container OOMKilled: false
health endpoint: HTTP 200
```

## Limitation and required confirmation

This qualification campaign began before the mandatory load-balancer rule and
targeted the model backend directly. It therefore has no HAProxy application-
traffic telemetry and is incomplete under the updated full protocol.

Promotion requires a new campaign through:

```text
AIPerf → HAProxy → one TP8 backend
```

with three repetitions at C32, C48, and C64, exact-window HAProxy directional
traffic telemetry, and comparison against both this qualification and the
seq32 / graph128 formal campaign.
