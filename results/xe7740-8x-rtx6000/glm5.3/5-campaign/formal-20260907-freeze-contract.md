---
kind: record
produced_by: 5
title: Approved formal freeze contract for GLM-5.3, 2026-09-07
---

# Freeze contract — `20260907-glm53-radixark-formal`

Approved explicitly by the operator on 2026-09-07 ("yes to all") after this contract was presented.
It fails closed: no formal run exists until this file, `preflight.json`, and the B0 idle baseline
exist. Never mutate this file after the first formal measurement; a capacity-affecting change is a
new contract.

## Deployment

Single replica, TP8, **no HAProxy** (`concurrency-grids.yaml` records `replicas: 1`).

| Setting | Value |
|---|---|
| Artifact | `RadixArk/GLM-5.3-NVFP4` at `/home/demouser/models/RadixArk--GLM-5.3-NVFP4--model` |
| Image | `local/radixark-glm53-r18-seq64-graph256:canary` |
| `MAX_NUM_SEQS` | 128 |
| `GRAPH` | 512 (= 128 × (1 + MTP 3), graph coverage satisfied) |
| `MTP` | 3 |
| `GPU_MEMORY_UTILIZATION` | 0.95 |
| Host RAM cap | `--memory 96g --memory-swap 96g`, **measured** via cgroup `memory.peak` |
| Expert execution | default (no `B12X_MOE_*` override; gen15 measured A16/A8/native within 0.3%) |

## Profiles and exact token shapes

Identical to `radixark-glm53-formal.yaml` (2026-08-30) so published deltas stay admissible.

| Profile | `input_tokens_mean` | `output_tokens_mean` | stddev | window |
|---|---:|---:|---:|---:|
| decode | 8 | 768 | 0 | 60 s |
| prefill | 2048 | 8 | 0 | 60 s |
| balanced | per prior spec | per prior spec | 0 | 60 s |

## One shared global concurrency grid, every primary profile

`1, 8, 32, 64, 96, 128, 160, 192` — **8 points**, `hard_max: 192`.

This deliberately supersedes the recorded `glm-5.3` grid (`hard_max: 64`, whose rationale excluded
C128 "without the long C128 drain"). Reason: every 2026-09-06 raster measurement places the decode
peak between C88 and C128, so a grid capped at 64 cannot contain the operating point being
reported. Approved in words by the operator, not inferred.

## Repetitions and totals

3 per point; 5 at each peak-candidate point (C96 and C128, because the peak's position is not yet
order-controlled); plus a 3-repetition 90 s control at C128 to re-measure the window-class offset
once measured at 3.1%.

```
grid points x profiles x base reps = 8 x 3 x 3  = 72
peak-candidate extras: 2 points x 3 profiles x 2 extra reps = 12
90 s control at C128: 1 point x 3 profiles x 3 reps          =  9
                                                             ---
total measured runs                                            93
```

**Arithmetic correction, recorded before launch:** the contract as presented said 63 runs and
~5 h 30 m. That count used 7 grid points, not the 8 approved, and omitted the 12 peak extras.
Corrected estimate: 93 runs x ~4 min (60 s window + warm-up at 2x concurrency + settle/drain)
= ~6 h 12 m, plus 1 startup (~15 min), B0 and B1-post idle baselines (~20 min), telemetry tail
(~20 min) = **~6 h 50 m wall clock**, budget stop at +25% (~8 h 25 m). The correction is stated
before the first run, not after; if the operator rejects the larger total this contract is
re-frozen rather than silently trimmed.

## Comparability disclosure, mandatory in the report

The formal decode comparator `927.373479422657` @ C48 was measured on deployment
`r1-tp8-dcp1-mtp3-seq32-b8192-r18` — **seq32, not seq128** — and its grid did not include C96 or
above. Any improvement statement is therefore a *deployment* comparison, not the same system
getting faster, and must be worded that way. The prefill comparator `11086.79` @ C48 carries the
same caveat.

## Not part of this contract

- gen16's order-controlled turnover result. If it shows turnover below C160, the grid's upper
  points become overload coverage rather than peak search; that is a *reported consequence*, not a
  licence to edit this file.
- Expert-width or MTP-depth claims: gen15 (width) and gen10 (MTP4/MTP5 at −20%) settle those.
- Anything from the 8-token synthetic raster windows, which is qualification evidence only.
