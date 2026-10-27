# DeepSeek-V4-Flash evolutionary tuning

Date: 2026-09-02
Host: `xe7740-04`
Status: qualification and formal 72-run campaign complete

## Objective

Find separate maximum-throughput configurations for Decode and Prefill before
freezing the formal repeated campaign. Speculative decoding is mandatory. The
formal campaign will use global concurrency `1, 8, 32, 64, 96, 128, 192, 256`.

## Provenance limitation

The local checkpoint is `deepseek-ai/DeepSeek-V4-Flash-0731`, but its immutable
upstream revision and download receipt are unavailable. The campaign is stored
under `local-unverified`; no commit SHA is inferred. Local identity evidence:

```text
config.json SHA-256: 6c8f3d2d3b48707541b88f32f22ef3f0f8a6b57d8523281e2b8d3cdb0ae9a023
model.safetensors.index.json SHA-256: 98efab455cf08dfbbbaaba6f570e1bf10bf927d2b4c3c453a59c2f6f0e3be92b
48 referenced Safetensors shards; zero missing shards
```

## Baseline

The proven four-TP2 deployment used DSpark-5, B12X A8, B12X all-reduce,
`max_num_seqs=16`, batch 4096, graph 96, FP8 KV, 48.5 GiB host KV offload per
replica, and a 524,288-token context limit. At global C256:

```text
Decode: 2,536.97 output tokens/s, p95 TTFT 61.59 s, zero errors
Prefill: 36,950.52 input tokens/s, p95 TTFT 16.75 s, zero errors
```

The latency and queueing show that C256 overloaded the baseline's combined
64-active-request ceiling.

## Failed broad raster

Launching four graph-heavy candidates concurrently caused startup contention
and invalidated that attempt. Sequential launches were used afterward. Large
speculative graph allocations also reduced available KV memory enough to reject
several candidates even after context reduction. All failed logs are retained.

## Focused speculative decode raster

| Candidate | Output tok/s | p95 TTFT | Average ITL | Outcome |
|---|---:|---:|---:|---|
| DSpark-5, seq16, graph96, batch4096 | 696.18 | 2.001 s | 18.98 ms | Stable baseline |
| DSpark-5, seq24, graph144, batch8192 | 928.32 | 1.782 s | 22.46 ms | Stable |
| DSpark-5, seq32, graph192, batch8192 | 1,099.67 | 1.879 s | 25.26 ms | Selected |
| DSpark-7, seq24, graph192, batch8192 | 904.80 | 1.404 s | 22.95 ms | Slower |
| DSpark-5, seq24, NCCL | 920.27 | 2.280 s | 22.46 ms | Slower than B12X |
| DSpark-5, seq24, B12X A16 | unavailable | unavailable | unavailable | Startup failed |
| DSpark-5, seq24, dynamic depth | unavailable | unavailable | unavailable | Startup failed |

## Decode promotion

| Global concurrency | Output tok/s | p95 TTFT | Average ITL | Errors |
|---:|---:|---:|---:|---:|
| 128 | 3,983.50 | 2.652 s | 26.51 ms | 0 |
| 192 | 3,941.30 | 21.571 s | 28.13 ms | 0 |
| 256 | 3,743.70 | 31.037 s | 29.46 ms | 0 |
| 384 | 3,693.90 | 59.016 s | 31.14 ms | 0 |
| 512 | 3,691.07 | 86.215 s | 31.57 ms | 0 |

Peak measured throughput occurred at C128. C192 and C256 retain overload
coverage. C384 and C512 added no throughput and sharply worsened TTFT, so they
were removed from the formal grid. C96 was added to resolve the knee.

## Frozen decode candidate

```text
Topology: 4 independent TP2 replicas behind HAProxy leastconn
DSpark speculative tokens: 5
DSpark depth: fixed
Backend: b12x-a8
All-reduce: b12x
max_num_seqs: 32 per replica
max_num_batched_tokens: 8192 per replica
max_cudagraph_capture_size: 192 physical verifier rows
max_model_len: 32768 during decode qualification
KV cache dtype: fp8
KV offload: 48.5 GiB per replica
Prefix caching: disabled
```

## Rejected settings and operational lessons

- DSpark requires at least five draft tokens; depth three is invalid.
- DSpark-7 was slower than DSpark-5 at the matched active width.
- B12X A16 and dynamic-depth DSpark failed startup.
- NCCL was slightly slower and had worse p95 TTFT than B12X all-reduce.
- Seq64 and very large graph candidates failed startup; fitting model weights in
  VRAM does not imply enough memory remains for graphs and required KV capacity.
- A no-speculation seq64 candidate was cancelled before measurement when the
  operator made speculative decoding mandatory. It is ineligible for selection.
- Start graph-heavy TP2 candidates sequentially. Concurrent compilation caused
  initialization stalls and contaminated qualification.
- Preserve runtime-reported effective limits; requested values alone are not
  evidence that the scheduler admitted the intended width.
- Prefix caching remains disabled for uncached comparisons.

## Evidence

```text
/home/demouser/llm-benchmark-results/xe7740-04/deepseek-v4-flash-0731/local-unverified/r4-tp2-qualification/20260902-deepseek-v4-flash-evolutionary
```

Relevant subpaths are `qualification/baseline`, `raster`, and
`promotion/decode-ds5-s32-4xtp2`.

## Prefill raster and final selection

The first Prefill raster retained the 32K Decode winner as a control and tried
larger scheduler token budgets. The control produced 15,731.44 input tokens/s
with p95 TTFT 4.851 seconds and zero errors. Every 32K-context candidate at
batch 16K or above failed startup because graph/compile workspace left too
little KV memory to guarantee one 32K request. At batch 16K the runtime
estimated a maximum context around 14.3K; at batch 32K it estimated about 4.5K.

A targeted 8K-context raster then tested the larger budgets:

| Candidate | Input tok/s | p95 TTFT | Errors |
|---|---:|---:|---:|
| seq8, batch16384, graph48 | 9,519.40 | 1.780 s | 0 |
| seq16, batch12288, graph96 | 10,094.27 | 3.013 s | 0 |
| seq16, batch16384, graph96 | 12,727.76 | 2.178 s | 0 |
| seq32, batch12288, graph192 | 13,527.86 | 6.023 s | 0 |
| seq32, batch16384, graph192 | 15,833.22 | 4.725 s | 0 |
| seq64, batch16384, graph192 | 14,044.66 | 13.797 s | 0 |

The 8K seq32/batch16K result was only 0.65% above the 32K control in a single
qualification run. The formal campaign therefore retained the shared 32K,
seq32, batch8192, graph192 deployment instead of reducing context capability by
75% for a difference within likely run-to-run variance.

The catalog entry at
`$HOME/repos_e2/p009_ai_node/app/backend/catalog/rtx6k/deepseek-v4-flash-dspark-0731`
also confirmed DSpark-5/probabilistic as the validated choice, documented
DSpark-7/greedy startup problems, and showed the six physical verifier rows per
logical sequence relationship. Its upstream revision was not assigned to this
checkpoint because local snapshot identity was not proven.

## Formal campaign

The canonical campaign ran Decode, Prefill, and Balanced at global concurrency
`1, 8, 32, 64, 96, 128, 192, 256`, three repetitions each: 72/72 operating
points completed with zero failed runs. The formal specification is
`results/xe7740-8x-rtx6000/deepseek-v4-flash/0-spec/deepseek-v4-flash-formal-20260902.yaml`.

Headline medians:

```text
Decode:  3,535.32 output tokens/s at C128
Prefill: 76,092.69 input tokens/s at C256
```

The raw canonical campaign is:

```text
/home/demouser/llm-benchmark-results/xe7740-04/deepseek-v4-flash-0731/local-unveri/r4-tp2-dspark5-seq32-b8192-graph192-ctx32768/20260902-full-deepseek-v4-flash-formal
```

`local-unveri` is the runner's twelve-character truncation of the explicit
`local-unverified` revision label. It is not an upstream revision.

## Closeout state

`RUNS_COMPLETE` exists and all 72 manifests are complete. Normalized report
data, per-run CSV, aggregate CSV, publication JSON, and Astro rendering are in
the repository. A post-campaign loaded-idle capture and `CAMPAIGN_COMPLETE`
receipt were not present when this record was updated; this limitation does not
change the completed inference-run count.
