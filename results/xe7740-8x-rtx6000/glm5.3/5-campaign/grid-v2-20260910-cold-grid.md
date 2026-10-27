# Cold prefill grid v2 - 2026-09-10 (mechanical harness, full 8-point campaign)

kind: record

First campaign produced entirely by `benchmark-step.py`: preflight, sampler, disjoint per-run
prompt pools, per-run measurement, and the collection contract, in one process, with no manual
step in between. 24 runs measured, 24 cold.

## What ran

```
container            
concurrency points   [1, 8, 16, 32, 64, 96, 128, 160]
repetitions          3
window               60 s per run
pool source          pool-source-20260911.txt  sha256 e24e38bc1082a437b8a5b39de666cf865a3cd9246fbeb7ec0904c26f04142118
                     587,222,566 bytes; 1,678 Gutenberg works, zero ebook-ID overlap with the
                     v1 corpus, so no prompt in this grid was ever served from the engine's
                     prefix cache during the nine v1 runs measured earlier that day
telemetry samples    1504
                     50 fields/row; the three engine-RAM fields are NOT in these rows - the
                     sampler that ran was the pre-RAM version still resident in memory
```

## Result (input tokens/s, per repetition)

```
point  n  served%          tok/s per rep            spread   median
C1    3  [0.0, 0.0, 0.0] [2658, 2570, 2816]         8.7%   2657.6
C8    3  [0.0, 0.0, 0.0] [4121, 3930, 4105]         4.6%   4104.6
C16   3  [0.0, 0.0, 0.0] [5738, 5754, 6338]         9.5%   5754.3
C32   3  [0.0, 0.0, 0.0] [5769, 5771, 5738]         0.6%   5768.5
C64   3  [0.0, 0.0, 0.0] [5710, 6302, 6332]         9.8%   6301.6
C96   3  [0.0, 0.0, 0.0] [5755, 6310, 6257]         8.8%   6257.3
C128  3  [0.0, 0.0, 0.0] [5749, 5729, 6297]         9.0%   5749.0
C160  3  [0.0, 0.0, 0.0] [6363, 6355, 5772]         9.3%   6354.8
```

Every point reports `served_prompt_pct 0.0` from the engine's own prefix-cache counters over the
measured window, and `cache_verdict: cold` on all 24 runs. This is the first prefill series here
whose numbers are not cache throughput.

## Unresolved: the results are bimodal, not merely noisy

Repetitions land near ~5,750 or ~6,300 tok/s, a ~9% alternation appearing in six of the eight
points. It is not monotone drift and it is not one bad point. Before a single number per point is
published, the cause must be identified - candidate causes are GPU clock/power state, NUMA
placement, or the 2.3 TiB anonymous-memory holder in `obs-cadvisor` on this host. Per-run
telemetry is sufficient to test the clock and co-tenant hypotheses.

## Environmental condition, recorded

The host had a process holding 2,389 GiB of anonymous memory (obs-cadvisor, up 13 days, no
cgroup limit) with 504 GiB of the 3,023 GiB machine available. No swap activity and no memory
pressure appeared in the sampler's CPU fields. Throughput results are not obviously affected;
any statement about host RAM headroom derived from this campaign is not.

The network path to this host dropped for ~70 minutes during and after the campaign. The node did
not reboot (uptime 20 days on return). The campaign completed regardless: 24/24 with
STEP_COMPLETE written by the harness.

## Where the evidence is

```
node      /home/demouser/glm53-raster/grid-v2-20260910T140248Z/   (authoritative, never deleted)
mirror    results/xe7740-8x-rtx6000/_local-evidence/xe7740-04/glm5.3/5-campaign/grid-v2-20260910T140248Z/
          296 files, 692,656,381 bytes, untracked by policy
manifest  MANIFEST.sha256 (per-file SHA-256, one line per file)
          sha256 of that manifest: 3f0328e2fa4780749bdbe2d715f66c134d9e300ff562d64823dcf0ea0af1745e
```

The mirrored tree carries a per-file SHA-256 manifest.

**Verified 2026-09-10 23:35 CEST:** 295 files common between node and mirror, **0 differing
hashes**. The only path present on one side is `IDLE-NOT-CAPTURED.reason`, written locally after
the mirror was taken, so its absence on the node is expected rather than a defect.

An automated check run earlier reported "MIRROR MISMATCH: 49 differing lines". That report was
wrong and is withdrawn: it diffed two `sort -k2` listings produced under different locale settings,
so identically-hashed paths landed on different lines. Comparing by path rather than by line order
gives the result above. A verification that fails because of `LC_COLLATE` is not a verification;
the comparison is by path.

## Status

Collection: satisfied (harness reported STEP_COMPLETE, 0 contract defects).
Idle references: B0 and B1-post were NOT captured by the harness that ran this campaign. See
`IDLE-NOT-CAPTURED.reason` beside the evidence, which quotes the inter-run power gaps without
calling them idle. benchmark-step.py captures both from this commit onward.
Acceptance: NOT run. Publication: NOT permitted. Nothing from this campaign is on the site.
Acceptance is the next gate and it decides, not this record.

