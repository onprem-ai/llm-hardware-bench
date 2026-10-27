---
kind: rule
step: 3
title: Deployment raster rules
---

# Chapter 3 - Deployment raster

Substance of the raster. Order, budgets and gates live in `PIPELINE.md`; the naming
contract and pipeline-level rules (R-PIPE-1..7) also live there. Rule IDs below map
1:1 to the former `PROCEDURE.md` numbered list and to rules 13-19 added on 2026-09-06.

# Mandatory evolutionary deployment raster

Rule IDs `R-03-1..R-03-20`; the older `R-RASTER-n` citation form is an alias for
`R-03-n` (see `harness/MOVED.md`). IDs assigned 2026-09-06.

Before freezing a formal campaign for any model, run an explicit evolutionary
parameter search. A conservative loader canary is only generation zero; it must
not be presented as hardware capacity unless the raster demonstrates that no
more aggressive stable candidate improves the decision metric.

### R-03-1 — Define the search genome

> Formerly raster rule 1 (also cited as `R-RASTER-1`).

Include every capacity-affecting parameter that
plausibly changes the frontier: replica/TP/EP/DCP topology, active-sequence or
running-request ceiling, CUDA-graph coverage, Mamba/state-cache allocation,
KV dtype and capacity, context limit, batch/prefill token budget, speculative
method/depth, PLE or other offload placement, communication backend, and
CPU/NUMA placement.
### R-03-2 — Start from a known-correct seed

> Formerly raster rule 2 (also cited as `R-RASTER-2`).

Require successful load, non-corrupt
generation, post-request health, and exact runtime identity. Preserve loader
and correctness failures.
### R-03-3 — Verify phenotype, not requested genotype

> Formerly raster rule 3 (also cited as `R-RASTER-3`).

Parse runtime logs and metrics
for the actual admitted sequence count, graph batches captured, KV/state
capacity, backend selection, offload state, and disabled/fallback features.
Requested flags are not evidence that the runtime honored them.
### R-03-4 — Rasterize broadly

> Formerly raster rule 4 (also cited as `R-RASTER-4`).

Test materially different candidates rather than tiny
serial changes. Use coarse-to-fine values around memory and scheduling
boundaries, including at least one deliberately aggressive candidate.
### R-03-5 — Use disjoint hardware in parallel when available

> Formerly raster rule 5 (also cited as `R-RASTER-5`).

Independent candidates
may load and benchmark simultaneously on non-overlapping GPU groups when the
study goal is whole-machine throughput. Label this as a contention-aware
comparison. Use sequential A/B runs when isolated per-candidate attribution
is required.
### R-03-6 — Use short decisive workloads

> Formerly raster rule 6 (also cited as `R-RASTER-6`).

During evolution, benchmark only the
concurrency points needed to expose low-load speed, the expected knee,
candidate admission ceiling, and one overload point. Do not launch the full
repeated profile grid for every candidate.
### R-03-7 — Select and mutate winners

> Formerly raster rule 7 (also cited as `R-RASTER-7`).

Rank candidates by stable aggregate useful
throughput subject to errors, OOMs, output correctness, latency/goodput,
memory headroom, and production credibility. Create the next generation by
mutating around the best candidates, including a fair speculation-on/off
comparison with matched admission and graph width.
### R-03-8 — Disqualify unstable candidates

> Formerly raster rule 8 (also cited as `R-RASTER-8`).

A higher nominal peak does not win if it
restarts, emits malformed output, returns request errors, silently falls back
outside the intended graph/kernel path, or fails a repeat confirmation.
### R-03-9 — Promote homogeneously and retest globally

> Formerly raster rule 9 (also cited as `R-RASTER-9`).

Clone the winning settings to
the complete intended deployment and measure global concurrency through and
beyond its aggregate active-sequence ceiling. Do not extrapolate
`replicas × single-replica TPS` as the final result.
### R-03-10 — Optimize profiles independently

> Formerly raster rule 10 (also cited as `R-RASTER-10`).

Run separate evolutionary rasters for
Decode, Prefill, and Balanced workloads. Their winners may use different
graph modes, sequence ceilings, cache allocations, speculation, chunk sizes,
token budgets, or topology. Do not force one compromise deployment to
define every peak-capacity metric.
### R-03-11 — Promote profile-specific winners

> Formerly raster rule 11 (also cited as `R-RASTER-11`).

The final study may report a
Decode-optimized deployment, a Prefill-optimized deployment, and a Balanced
production deployment. Give each a distinct deployment ID and complete
provenance. Never attach telemetry or latency from one deployment to the
throughput of another.
### R-03-12 — Stop criterion

> Formerly raster rule 12 (also cited as `R-RASTER-12`).

Freeze each profile's formal campaign only after
neighboring mutations fail to improve stable useful throughput materially,
or trade unacceptable latency, capacity, quality, or reliability for the
gain.

### R-03-13 — Treat winner-mutation as one-factor-at-a-time and test the interactions it cannot see

> Formerly raster rule 13 (also cited as `R-RASTER-13`).

Mutating around a current winner is OFAT: it finds single-factor
improvements and is structurally blind to interactions. After the first factor is
settled, run at least one **factorial probe** over the two factors that moved the
decision metric most. Actively look for a **sign change** - a candidate that wins
at one setting of a second factor and loses at another - because that is proof the
factors interact and OFAT results are not composable. Worked example: a shallower
speculation depth beat the deployed depth by 9.3% at exactly the concurrency where
the deployed depth saturated admission, while losing by 6-12% everywhere below it.
Neither raster was designed to test the other, and each alone would have produced a
wrong conclusion.
### R-03-14 — Establish turnover before calling anything a peak

> Formerly raster rule 14 (also cited as `R-RASTER-14`).

The highest measured point
is not a peak; it is the top of an unfinished sweep. A peak is established only
when a measured point beyond it is lower, with the same protocol. Where throughput
is still rising at the last planned point, extend the sweep to the configuration's
own admission ceiling instead of reporting it.
### R-03-15 — Never compare measurements across measured-window classes

> Formerly raster rule 15 (also cited as `R-RASTER-15`).

Short exploratory
windows read systematically lower than protocol-length windows on the same
configuration and server. Measure the offset on one configuration, record the
correction (3.1% measured for 60 s x 2 versus 90 s x 3 on a TP8 decode profile),
and label every reported figure with its window length and repetition count. A
candidate "tie" between two different window classes is not a tie.
### R-03-16 — Re-baseline across any environment change

> Formerly raster rule 16 (also cited as `R-RASTER-16`).

When a precondition changes -
background load capped or removed, clocks, driver, kernel, thermal state, node
restart - stop at a candidate boundary rather than mid-candidate, record the change
and the before/after environmental measurement, and make the **first measurement of
the next generation a re-measurement of the control**. Comparisons that straddle an
undocumented change are not comparisons. Never reconfigure a background telemetry
agent mid-candidate (see 4.1).
### R-03-17 — Judge a run by evidence on disk, never by its completion markers

> Formerly raster rule 17 (also cited as `R-RASTER-17`).

A completion
marker with zero exported result artifacts is a null result, and a complete run
with a lost marker is real data. Require the count of exported result files to
match the planned point count before accepting any generation. Record terminal
state explicitly (`COMPLETE`, `ABORTED`, `INVALID`, `DEFERRED`); a marker added
after the fact must say so in the file. Archive defective runs; never delete them,
and never publish a measurement from one.
### R-03-18 — Record a falsified hypothesis as a finding

> Formerly raster rule 18 (also cited as `R-RASTER-18`).

State what was refuted, by what
margin, under which conditions, and which prediction it disconfirmed. Equally,
state which levers remain **untested** and are not "tested and rejected" - an
experiment that produced no measurements because of harness failure has an unknown
outcome, and must be relabelled rather than left as an implicit negative.

### R-03-19 — A guard verifies state, not a remembered log line

Any preflight or inter-candidate guard must (a) assert the interface it actually calls, read
from that interface's source, and (b) verify the **state it cares about** independently of that
interface's output text.

This produced a third class of null result on 2026-09-06. A generated raster controller
required the string `ok free 8080` from `free-8080.sh`; the script has always emitted
`free8080_ok stopped=[...]`. Two generations aborted within one second of each other, before
any container launch, yielding zero measurement files. The failure was invisible in the exit
path because the script returned 0 — the guard's invented contract, not the environment, was
wrong.

The repaired guard checks the real string **and** the state: no `ss` listener on 8080, and no
HTTP answer from `/health`. Three properties it must keep:

- it passes when the port is genuinely free (`free8080_verified free8080_ok stopped=[]`);
- it stops a live container and then verifies, rather than rejecting outright — freeing the
  port is the guard's job, not an error;
- it fails if a listener survives, which is the only outcome that should stop a campaign.

Corollary, learned the hard way three times today: **verify a guard by executing it, including
one hostile case.** Parsing, dry-runs and `bash -n` all passed on two scripts that could not
run, and a regex-based patch reported "replaced 1 lines" while silently not matching, which is
what made the first relaunch fail identically. A guard that has never been observed rejecting
something is decoration.

### R-03-20 — A queue handoff waits on a recorded pid, and the single-controller invariant is asserted

Two failure modes cost ~11 minutes of eight-GPU startup on 2026-09-06 and produced a fourth
and fifth null result in one day. Both came from chaining generations by inference instead of
by record.

1. **A follower must wait on a pid that was written down, and fail closed if it is absent.**
   A follower waiter was handed an empty pid (the predecessor was matched by searching the
   process table for its directory path, but it had been started as `bash run.sh`, so the path
   was never in argv). `kill -0 ""` fails instantly, the wait loop ended at once, and the
   follower started immediately — the failure looked like success because nothing raised.
2. **Where generations share a resource name, single-controller is an invariant, not a
   courtesy.** Both generations used the container name `radixark-glm53-raster`, so each
   `launch` stopped the other's server. Neither candidate reached readiness; four launches
   interleaved and all produced zero measurements. The harness's own `name_still_taken`
   assertion caught one collision, which is the only reason this was not a longer silent stall.

Required of a controller: write `controller.pid` at start; on chain, read the predecessor's
pidfile and refuse to proceed if it is empty, if any other `run.sh` is alive, or if the port is
still bound. Hand off on **artifact state** (`COMPLETE`/`ABORTED` present) or a recorded pid —
never on a process-table string match, because argv is not identity.

Corollary on reuse: when generating a new controller, copy the harness from a generation that
reached `ready` and change only the candidate list. A regenerated launcher silently dropped
`--memory 96g` and passed the model as a positional argument that the image entrypoint rejects;
the second fault is loud, the first is not — it would have measured the session's headline
extension **outside the qualified host-RAM allocation**, invalidating it against the very
qualification the earlier work established. Copying tested code is not laziness: that is where
the memory bound, the mount layout, the corpus (`isl=8 osl=768`) and the smoke test live.

### R-03-21 — Control the order in which points are measured, and record it — 3

Throughput depends on position within a launch session: cache warming, tenant decay and thermal
drift all act in the same direction. When points are measured in a fixed order, that effect is
indistinguishable from the parameter under test, and a sweep can look monotonic in the wrong
variable. Within a candidate, points must be visited in randomized or counterbalanced order, and
each measurement must record its position in the sequence. If order is not controlled, the
candidate may report per-point values but must not report a peak, an optimum, or a turnover.

### R-03-22 — A readiness deadline must be justified by a measured boot time, not a constant — 3

Graph capture time grows with the graph set size, so a fixed deadline fails exactly the largest
candidates — the ones worth testing — and the failure looks like a capacity limit rather than a
timeout. Record time-to-ready for every candidate; set the deadline from measured boots with
margin, scaled by the parameter driving capture cost; and distinguish `startup_timeout` from
`startup_failed` in the record, because they carry opposite implications about hardware capacity.

### R-03-20a — Write and read a control marker through one shared constant — 3

The abort marker's filename existed as two string literals, one in the writer and one in the
reader; the reader tested a name the writer never emits, and a cleanup command deleted a file that
had never existed while the real marker stayed in place. Any marker, lock or sentinel used by more
than one process must be produced by a single constant or helper, and the pair must be exercised
by a test that writes it in one process and observes it in the other.

### R-03-23 — Qualification is decisive, not ceremonially cautious — 3

Run independent candidates concurrently on disjoint GPU groups when safe. Use one short repetition
and only knee-finding concurrency points while candidates are still being evolved; reserve three
repetitions and full grids for winners. Test coarse jumps first, then refine around a winner - one
tiny increment at a time across a wide range is a search that cannot terminate. Combine orthogonal
questions in one generation where interpretation stays clear, such as admission and graph
candidates alongside a matched speculation-off control. Start from production-credible aggressive
values and let explicit OOM, correctness, latency or instability gates reject them; conservative
defaults are loader seeds, not recommendations.

Stop a broad sweep as soon as a configuration defect makes the remaining points non-decision-
useful: preserve completed evidence, record the reason, fix the deployment, continue with focused
canaries. Chain approved stages - readiness, correctness, baseline, short raster, promotion test -
without avoidable waits. A timeout is a qualification failure receipt, not a reason to wait.

A generation should take tens of minutes. If qualification costs more than the expected formal set,
the search is too serial, too dense, or measuring points that cannot affect promotion.

### R-03-24 — Read the runtime's actual behaviour, not the requested settings — 3

Parse the log immediately after startup and abort or reclassify a candidate when the runtime
silently caps sequences, narrows graph coverage, changes kernels, disables a feature, or moves cache
placement. The requested configuration is a hypothesis; the runtime's own report is the measurement.

### R-03-25 — One raster row per candidate, and one journal for the study — 3

Preserve a compact row per candidate: identity, GPU allocation, topology, requested settings, actual
runtime settings, KV/state capacity, graph coverage, workload and concurrency, throughput, latency,
errors, OOM/restart state, output-validity result, promotion decision, reason. Maintain a
chronological study journal of every mutation, failure, correction and promotion decision.
Qualification output stays exploratory and is never relabelled as formal repetitions.

Parallel-contended tests answer whole-machine capacity questions; sequential tests answer isolated
candidate-efficiency questions. Use the one that matches the decision and label which it was.

### R-03-26 Guard harness parameters, and record the realized window rather than the requested one

Three defects on 2026-09-07 were invisible in the exit status of the command that caused them: a
repetition label reaching an arithmetic seed expression (`set -u` killed the controller mid-campaign and
left the server serving nothing for 2 hours); control repetitions that would have reused the grid's
seeds, making a control a replay; and a transposed argument list that set `--benchmark-duration` to
800000 seconds - a 9.3-day measurement. `run_one` now rejects non-numeric concurrency or repetition
labels, windows outside 10-300 s, and misaligned seed bases; each historical bug was fed back through the
guards. Note what the seed guard does **not** do: it checks alignment, not uniqueness, so distinctness
still depends on explicit per-class bases.

`--benchmark-duration` is a request, not a measurement: with `--benchmark-grace-period inf` a declared
60 s window realized 87.8 s at C128 and 141.7 s at C192 for a 768-token profile, so the comparable
window is the one read back from `benchmark_duration`. Sampler CSVs must be rectangular - the campaign
sampler declared 7 header fields while emitting 21, which consumers then parsed by position or mis-read.
_Source: formal campaign `20260907-glm53-radixark-formal`, 2026-09-07._

## Sub-step budgets

One budget per sub-step: **wall-clock minutes**. B = blocking, charged in full;
O = off-path, must be scheduled inside a measurement window. Rules and breach protocol: `PIPELINE.md`.

| Sub-step | Owner | Path | Budget |
|---|---|---|---|
| candidate design: hypothesis + what would refute it | **agent** | O | 20m, max 5 candidates |
| script validation, no GPU | mech | B | 2m |
| startup + phenotype verification | mech | B | 15m |
| curve measure, <=6 points, exploratory window | mech | B | 30m |
| collect, audit, spec/latency deltas | mech | O | 5m |
| interpretation, next-candidate decision | **agent** | B | 15m |
| extension to turnover for a prospective winner | mech | B | 25m |

### R-03-28: Cold-input measurement runner is parameterised, probed, and fails closed
`cold-prefill-bench.sh` (preserved as as-run campaign code beside the study that used it,
`results/<host>/raster-harness/`) runs a cache-free sweep. It takes the evidence directory,
container name, grid, prompt-pool size, corpus file and gate path as parameters, so the
measurement definition is one reviewed tool rather than a script rewritten per campaign.

* Before any measurement, probe the installed binary with the exact input argument set. If
  it is rejected, write `INVALID.probe` and exit 2. A silently ignored option reverts to
  the default 100-prompt pool, which is the defect this runner exists to prevent.
* Input is either `--dataset-type synthetic --num-dataset-entries N` with `N` above the
  largest window's request count, or `--dataset-type custom --input-file <corpus>`, where
  `code/make_book_corpus.py` builds one non-overlapping passage per prompt from real book
  text and records source SHA-256, offsets and the disjoint warm-up/measured ranges.
* After every run, `code/cold_gate.py` reads that run's own prefix-cache counters. Above
  the limit, or with counters absent, write `INVALID.cold-cache` and halt the campaign.
  Unknown is never treated as cold (R-PIPE-8).

R-03-28 addendum, from the first execution of the cold client against a real benchmark binary:

* Flag vocabulary is versioned. A 0.13.0 build exposes `--isl/--osl/--custom-dataset-type/
  --server-metrics` and has no `--dataset-type` or `--synthetic-input-tokens-mean`; the build on
  the benchmark host is the other one. Never hard-code one vocabulary: detect, and refuse when
  neither matches, because an option this build does not know is silently dropped.
* Artifact names are versioned too. 0.13.0 writes `profile_export.jsonl` and no
  `profile_export_aiperf.json`. A reader bound to one filename reports throughput as absent --
  the same failure as calling a measurement unsampled because the expected filename was wrong
  (R-06-10). Locate exports by role.
* `--num-dataset-entries` prints `[default: 100]` in the tool's own help. The defect that
  inflated 84 prefill runs was documented in the binary that exhibited it, in the flag I never
  passed, in the line nobody read.

