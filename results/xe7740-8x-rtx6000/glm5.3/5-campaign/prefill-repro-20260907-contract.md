---
kind: record
produced_by: 5
title: Prefill reproducibility rerun contract, C8/C32/C64, 2026-09-07
---

# Rerun contract — `prefill-repro-20260907`

Requested by the operator on 2026-09-07 ("lets rerun c8, c32, c64") immediately after the
prefill chart's non-monotonic shape was traced to the underlying repetitions. This is a
**new measurement contract**, not an amendment: `20260907-glm53-radixark-formal` finished,
was validated and published, and its evidence root is never written to. Artifacts for this
rerun go to `/home/demouser/glm53-raster/prefill-repro-20260907` on the node and mirror to
`results/xe7740-8x-rtx6000/_local-evidence/xe7740-04/glm5.3/5-campaign/prefill-repro-20260907/`.

## The question

The published prefill series puts C32 at 14,151.44 input tok/s and C64 at 12,810.34, so the
curve dips after C32 and climbs again. Visually that reads as a capacity inversion. Before
asking why, the ordering has to survive being measured.

## What the existing nine runs already say

Read from the mirrored raw exports (`runs/prefill/c0*/r*/profile_export_aiperf.json`) joined
to per-run `cache_read_pct` in the canonical tree's run manifests - not from a remembered
table:

| point | rep | input tok/s | prefix-cache served |
|-------|-----|-------------|---------------------|
| C8    | r1  | 2,961.01    | 0.00 %              |
| C8    | r2  | 3,234.60    | 15.72 %             |
| C8    | r3  | 3,102.66    | 16.39 %             |
| C32   | r1  | 9,725.44    | 62.87 %             |
| C32   | r2  | 15,485.12   | 88.93 %             |
| C32   | r3  | 14,151.44   | 88.23 %             |
| C64   | r1  | 12,810.34   | 72.17 %             |
| C64   | r2  | 13,456.57   | 72.88 %             |
| C64   | r3  | 11,825.90   | 69.92 %             |

Three things fall out of that table, and they are not the inversion:

1. **C32's repetition spread is 40.7 %** (9,725 to 15,485), against 12.7 % at C64 and 8.8 % at
   C8. This is the accepted-with-notes point whose spread exceeded the R-06-2 trigger; the
   note was right to refuse it a clean acceptance.
2. The distributions **overlap**: C32's weakest repetition is below C64's weakest, so a median
   comparison is not a capacity comparison here.
3. Regressing all nine runs on prefix-cache-served percentage alone gives
   `tok/s = 1552 + 149.4 × cache%` with **R² = 0.968**. Cache state by itself predicts a
   C32−C64 gap of **+2,400 tok/s** where only **+1,341** was observed - it over-explains. The
   residuals carry no per-point offset (C8 −52, C32 −387, C64 +439 tok/s mean), so nothing in
   this data requires a capacity difference between C32 and C64 to be accounted for.

So the working hypothesis is that the dip is cache-state ordering, not a property of the
server, and the rerun's job is to try to break that hypothesis rather than to confirm it.

## Design

Prefill shape only (isl 2048 / osl 8 as recorded in the formal spec), C8, C32, C64, **four
repetitions** each: 12 measured runs at the same 60 s declared window, plus warmups.

* Deployment inherited unchanged: image `local/radixark-glm53-r18-seq64-graph256:canary`,
  `MAX_NUM_SEQS=128`, `GRAPH=512`, `MTP=3`, `GPU_MEMORY_UTILIZATION=0.95`, 96 GiB container
  cap, one TP8 replica, no proxy. Verified line-for-line against the formal controller.
* Seed bases `808000 / 832000 / 864000` - aligned to satisfy the R-03-26 guard and disjoint
  from the formal campaign's `700000/800000/900000` families and from each other.
* Window-class controls are removed, not left in: 6 of 12 runs would otherwise have measured
  decode latency, which is not this question.
* The quality gate stays in front of measurement, and the B1-post idle baseline still runs,
  so ambient load is quantified the same way as in the formal campaign.
* Every run's prompt-cache read fraction is recorded beside its throughput, which is the
  quantity this rerun exists to correlate.

## Acceptance and stop rules

* **12 of 12** measured exports or the run is reported incomplete; fewer repetitions than the
  contract is a defect to report, not a result to publish (R-05-12).
* If C32 again exceeds C64 by more than the repetition spread at **matched** cache state
  (within ~5 points), the inversion is real and the published prefill series needs a
  correction note - added as a new record, never by editing the formal campaign.
* If the ordering disappears or the cache regression keeps R² > 0.9 with no per-point offset,
  the published wording stands: prefill is cache-served throughput, reported as a floor at
  C192, never as cold capacity.
* Either way the prefill **floor** claim does not move. It rests on C192 being the grid
  ceiling, which more repetitions at C8-C64 cannot touch.

## Unattended execution, disclosed

The node dropped off its overlay network at 10:00Z (reported offline, last seen 10:00:00Z) - the second
unannounced loss in three days - so the rerun is armed rather than run: `watch-and-run-prefill-repro.sh`
waits for reachability, then refuses to launch unless the container set is empty, all eight
GPUs report under 1 GiB used, host `MemAvailable` exceeds 700 GiB, the model directory and
telemetry sampler are present, and `/dev/shm` is clean. The uploaded controller is
SHA-256-compared against the tracked copy before it is allowed to start. Completed runs are
rsynced down while the campaign is still running, per R-05-13. `touch /tmp/prefill-repro.ABORT`
stops the watcher; it deletes nothing on the node.

Estimated wall clock: ~12 min model load, then ~2-3 min per run including warmup, so roughly
50-60 minutes for 12 runs.

## As-run observations, appended 2026-09-07 ~11:30Z

* **The rerun launched at 10:47:58Z and was never interrupted.** `uptime -s` reports
  2026-08-21 13:05:11, so there was no reboot; the container `radixark-glm53-repro` ran
  continuously and reached prefill C64 r2 at 11:22:17Z. The control plane said otherwise:
  the control plane reported `offline, last seen 29m ago` while the machine was measuring,
  and direct probes timed out four for four. Concluding from that signal that the run had
  "died with zero artifacts" was wrong, and it was the same inference error the pipeline
  already has a rule against - absence of evidence from a control plane is not evidence of
  absence. The node itself answered in one query the moment a path existed.
* **Artifacts live under `controls/prefill/`, not `runs/prefill/`.** `run_one` routes any run
  whose `seed_base` differs from the default into the `controls/` namespace, so a rerun that
  passes explicit disjoint seed bases - which R-03-26 asks for - is classified as a control
  by construction. The namespace is chosen by seed bookkeeping rather than by what the run is
  for. Left as-is mid-run rather than reorganised under a live campaign, and it is the reason
  the watcher's export count reported 0 while 10 exports were on disk; fixed to count
  recursively, with a regression case (dead start + `exports=10` must refuse to relaunch).
* **Deployment verified in force, not assumed:** `max_num_seqs 128`, `max_cudagraph_capture_size 512`,
  `num_speculative_tokens 3`, `gpu_memory_utilization 0.95`, `kv_cache_dtype fp8`, read back from
  the container's own startup log. Container peak RSS held at 63.27 GB (58.9 GiB) against the
  96 GiB cap across all ten completed runs, monotonically - no drift toward the limit.
* **The watcher adopted rather than relaunched.** At 11:23:40Z it found the in-flight run and
  logged `adopting the in-flight run (container=1 controller=5)`. Without that branch the
  relaunch switch then in place would have started a second container over ten completed
  measurements.
* Mirrored at time of writing: 10 of 12 exports, pulled during a reachable window at 11:24:44Z;
  the remaining two and `COMPLETE` are outstanding because the network path closed again at
  ~11:25Z. Nothing is inferred about them; the contract's 12-of-12 rule decides, and it will be
  read off the node.

## Result, provisional at 10 of 12 measurements (C64 r3/r4 outstanding), 2026-09-07 ~11:35Z

| point | rep | input tok/s | window s | prefix-cache served |
|-------|-----|-------------|----------|---------------------|
| C8    | r1  | 2,911.43    | 63.0     | 0.00 %              |
| C8    | r2  | 3,539.64    | 60.5     | 18.52 %             |
| C8    | r3  | 3,764.60    | 60.7     | 23.43 %             |
| C8    | r4  | 3,905.25    | 60.7     | 25.96 %             |
| C32   | r1  | 10,398.40   | 61.8     | 65.44 %             |
| C32   | r2  | 15,648.29   | 61.9     | 88.93 %             |
| C32   | r3  | 15,396.33   | 62.6     | 88.90 %             |
| C32   | r4  | 15,278.45   | 61.7     | 88.74 %             |
| C64   | r1  | 13,652.96   | 61.9     | 72.82 %             |
| C64   | r2  | 13,609.93   | 62.2     | 72.88 %             |

Unit asserted `tokens/sec` on every export. Point medians came back at +17.7% (C8), +8.4% (C32)
and +6.4% (C64) against the formal campaign, so the deployment is reproducible at the few-percent
level once cache state is comparable.

**The inversion is a cache artifact, and it reproduces.** Pooling all nineteen runs that carry
both a throughput and its cache state - nine formal, ten here, different launches, disjoint seed
families - the regression on prefix-cache-served fraction holds: `tok/s = 1235 + 156.3 × cache%`,
**R² = 0.965**. Cache state alone predicts a C32−C64 gap of **+2,488 tok/s**; the observed gap is
−1,822 (C64 below C32). Per-point residual means put C32 at **−280** and C64 at **+563**, so once
cache is accounted for, C64 is *faster* than C32 by roughly 840 tok/s, about 5.5%. The direction
of the apparent anomaly reverses; nothing about the server's behaviour at C64 is anomalous.

The mechanism is a first-repetition warm-up, and it reproduced at the same point with the same
magnitude on a fresh container and different seeds:

```
formal  C32 r1   9,725 tok/s at 62.87% cache      rerun  C32 r1  10,398 tok/s at 65.44% cache
formal  C32 r2+  14,151-15,485   at 88.2-88.9%    rerun  C32 r2+ 15,278-15,648   at 88.7-88.9%
```

The AIPerf shape draws `max(concurrency, 32)` prompts, so at C32 the first repetition is the one
that does not yet have that 32-prompt set resident, and every later repetition is served ~89% from
the prefix cache. C8 shows the same ramp without saturating (0 → 18.5 → 23.4 → 26.0% across four
repetitions, throughput rising 34%); C64 asks for 64 prompts, never fully warms, and is therefore
the *steadiest* point measured here - 0.3% spread across repetitions, against 34.2% at C32.

Consequences, in order of importance:

* The published prefill figure was never cold-prefill capacity and the published curve's shape is
  cache warm-up plus cache-state difference between points, not capacity turnover. The floor claim
  at C192 does not move: it rests on the grid ceiling, not on repetition or cache.
* Repetition spread is not noise here; it is the cache warming. Any prefill number quoted without
  its cache fraction is ambiguous by a factor of ~1.5 at these shapes, which is larger than most
  of the deltas this study has published.
* The prefill grid points are not comparable to each other as a capacity curve. C64 < C32 is a
  cache artifact; C32's own median is carried by warm repetitions.

Nothing on the site or in `publication.json` was edited as a result of this rerun. The correction
is a wording matter for the prefill series, and it will be raised rather than applied silently,
because three accepted publications cite that artifact as a comparator.
