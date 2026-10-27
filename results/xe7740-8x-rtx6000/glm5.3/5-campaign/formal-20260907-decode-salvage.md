---
status: superseded-by-mirrored-artifacts
kind: record
produced_by: 5
title: Formal campaign decode results, transcribed before node outage
---

# Formal campaign `20260907-glm53-radixark-formal` - decode half

**Provenance, stated precisely.** These values were parsed from the node's AIPerf exports at
2026-09-07 05:03 UTC and transcribed here while the node was still reachable. This file is a
*salvage copy of a summary*, not the measurement record. Publishable numbers require the raw
`profile_export_aiperf.json` files under
`XE7740-04:/home/demouser/glm53-raster/formal-20260907/runs/decode/`, which as of this writing are
unreachable. Nothing here may be published until those artifacts are pulled, structurally
validated, and run through the claims validator.

## Environment

Per `formal-20260907-freeze-contract.md`: one TP8 replica, no HAProxy, `MAX_NUM_SEQS=128`,
`GRAPH=512`, `MTP=3`, `GPU_MEMORY_UTILIZATION=0.95`, 96 GiB host cap, image
`local/radixark-glm53-r18-seq64-graph256:canary`, decode profile isl=8 / osl=768 / stddev 0,
60 s windows, `--use-server-token-count` asserted in every export (`use_server_token_count: True`,
28/28), units asserted `tokens/sec` (28/28).

Preflight passed 13/13 before launch. B0 idle baseline: 12 samples, GPU 29.5 W, 0% util,
host `MemAvailable` 2,967 GiB.

## Decode grid, median across repetitions

| C | median tok/s | reps | min..max | TTFT (median) |
|---:|---:|---:|---|---:|
| 1 | 78.73 | 3 | 77.63 .. 79.19 | 624.4 ms |
| 8 | 353.03 | 3 | 345.68 .. 356.43 | 543.0 ms |
| 32 | 718.06 | 3 | 712.82 .. 727.48 | 1194.7 ms |
| 64 | 987.48 | 3 | 972.80 .. 992.51 | 1860.9 ms |
| 96 | 1158.91 | 5 | 1137.34 .. 1167.02 | 2753.1 ms |
| 128 | **1230.02** | 5 | 1223.72 .. 1234.53 | 4251.2 ms |
| 160 | 1148.32 | 3 | 1139.55 .. 1150.40 | 16804.6 ms |
| 192 | 1096.57 | 3 | 1094.64 .. 1116.97 | 27525.2 ms |

28 runs, 0 run failures, 0 unreadable exports.

## What this establishes

- **Interior peak at C128 = 1230.02 output tok/s.** Peak-candidate points carry 5 repetitions;
  within-point spread is 0.9% at C128, so the point is not noise.
- **Turnover is real, on both sides of the peak, inside one launch.** C160 is -6.6% and C192 is
  -10.9% below the peak, each roughly 10x the within-point spread, and TTFT rises
  4.25 s -> 16.80 s -> 27.53 s independently of throughput. Two independent signals indicating
  saturation rather than drift or order effects. Rasters gen14/gen16 could not make this claim
  because measurement order was not controlled; a single ascending pass to C192 does control it,
  and the decline is measured after the peak rather than before it.
- **Comparability caveat, mandatory in any report.** Against the recorded comparator
  `927.373479422657` @ C48 this is +32.6%, but that comparator was produced by deployment
  `r1-tp8-dcp1-mtp3-seq32-b8192-r18` (seq32, not seq128) on a grid that did not reach C96. The
  statement is therefore a *cross-deployment* comparison, not the same system getting faster.
  Both old and new use 8-token synthetic prompts with prefix caching enabled, so both share the
  short-prompt inflation; that limits absolute decode rates, not the delta's direction.
- **Host RAM**: peak charged inside the container during decode was 58.80 GiB under a 96 GiB cap,
  `oom_kill 0`, 37 GiB headroom. Aggregate PSS 60.98 GiB across 11 processes
  (anon 55.91 + shmem 2.52 GiB). See the journal for the 50.33 GiB measurement on the
  `seq64/graph256` deployment: the floor moves with serving parameters, not with the model.

## Not established by this file

Prefill and balanced profiles (never started), the 60 s vs 90 s window-class control (lost twice:
once to the harness defect, once to the outage), the B1-post idle baseline, and any
`claims.yaml`-validated statement. `CAMPAIGN_COMPLETE` does not exist.
