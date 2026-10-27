---
kind: record
produced_by: 5
title: Formal campaign harness defects and the node outage that followed
---

# `20260907` formal campaign: four harness defects, then the host disappeared

Kept because each defect was invisible in the exit status of the thing that ran it, which is the
class of failure R-PIPE-8 exists to catch.

## 1. Fatal arithmetic on a repetition label

`run_one` computed `seed=$(( 700000 + c*100 + rep ))`. Fine while `rep` was numeric. The 90 s
window-class control passed the label `w90-1`, so bash parsed `w90-1` arithmetically, `set -u`
rejected `w90`, and the controller exited:

```
run.sh: line 149: w90: unbound variable
2026-09-07T03:08:03Z controller_exit=1
```

Decode had finished (28 runs); prefill and the control never started. **The server kept serving,
idle, for 2 hours** because nothing treated a dead controller as an event. `progress.log` gained
one line; the GPU cost was silent. Labels are now forbidden in numeric slots, and a repetition
label is validated as `^[0-9]+$`.

## 2. Control runs would have replayed grid seeds

With `rep` numeric, the C128 control seeds were `700000 + 128*100 + 1..3` - identical to the C128
grid repetitions. The window-class control would have been the same request stream as the run it
was meant to calibrate against, so a measured "60 s vs 90 s offset" would have contained no new
measurement. Defect 1 masked this one. Control bases are now disjoint: grid 700000, control60
800000, control90 900000, verified at C128 r1 as 712801 / 812801 / 912801.

**Known weakness, not fixed:** the added guard tests `seed_base % 1000 == 0`, i.e. *alignment*,
not *uniqueness*. A control given the grid's base is still accepted, as a re-test confirmed. Real
uniqueness comes from explicit bases plus a separate `controls/` artifact namespace. A proper check
belongs in collection, comparing each run's manifest `seed` against every other run at the same
concurrency.

## 3. My fix was worse than the bug

The first control block called `run_one decode "$r" 60 800000`, but the signature is
`(profile concurrency repetition window_seconds seed_base)`. That is concurrency 1-3, repetition
60, and `--benchmark-duration 800000`: a 9.3-day benchmark. Caught by reading the assembled file,
not by running it. `run_one` now rejects a window outside 10-300 s, non-numeric concurrency,
non-numeric repetition labels, and misaligned seed bases - each historical bug fed back through the
guards, all rejected, valid runs accepted.

## 4. Window-class control confounded by the restart

Resuming re-ran `launch formal`, which stopped the 4-hour-warm container and started a cold one.
The campaign therefore has **two launches instead of the one the freeze contract describes**: the
decode grid belongs to launch A, prefill/balanced to launch B, and the in-loop decode control would
also have belonged to launch B - putting the restart offset inside the window-class offset. Added a
same-launch control block (C128 at 60 s and 90 s back to back) so that offset stays interpretable.
The launch-count deviation stands and must be disclosed with any number from this campaign.

## 5. Node outage, cause unknown

`05:08:36Z` relaunch, last confirmed reachable ~05:11. The host's overlay-network presence reports
`offline, last seen 3h ago` as of 09:38 UTC, so the host went down roughly 06:30-06:40, about 90
minutes into the resumed run and during cold start of the 433 GiB checkpoint.

- Direct and overlay-network reachability probes time out; the node reports offline. This is
  the machine or its network, not a hung command.
- No secondary address, no bastion, no out-of-band path is recorded anywhere in this repo, and the
  observability stack (`obs-grafana`, `obs-victoriametrics`, `obs-dcgm-exporter`, `obs-cadvisor`,
  `obs-node-exporter`) ran *on that host*, so there is no external view of the outage either.
- Nothing in the harness can plausibly take a 3 TiB host down: the container was capped at 96 GiB
  with `oom_kill 0`, host `MemAvailable` was 2,923 GiB, `/dev/shm` was empty, and no code path here
  touches reboot, power, or the network stack. A provider-side reclaim, host crash, or
  administrator action remain indistinguishable candidates from this distance.
- **The outage was not detected by anything I built.** I found it while answering a status question.
  A background watcher now polls SSH every 60 s and captures campaign state the moment it returns.

## Resolution, 2026-09-07 09:44 UTC: network-only loss, and the campaign completed

The watcher reached the host at 09:44:15Z. `uptime -s` reports **2026-08-21 13:05:11**, so the
machine never rebooted: the network link dropped and everything else kept running. Telemetry holds
658 samples across 06:00-07:00 with GPU utilization non-zero throughout, so the harness, the
container and the measurements were alive for the entire blackout. The provider-reclaim and
host-crash candidates above are withdrawn; what broke the SSH path is still undetermined, but it
was neither the campaign nor the compute.

Final state, read from artifacts rather than from a log line:

- `COMPLETE` present, no `INVALID` marker, `formal_complete runs=84 parseable=84`.
- 96 exports: 84 grid runs (3 profiles x 8 points x 3 reps, plus 2 extra reps at C96 and C128) and
  12 controls. 0 run failures, 0 guard trips, 0 unreadable exports, units `tokens/sec` on all 96,
  `use_server_token_count: true` on all 96.
- Container high-water 59.03 GiB of the 96 GiB cap (61%), `oom_kill 0`; host `MemAvailable` never
  fell below 2,901 GiB. B0 idle 29.4 W vs B1-post idle 29.8 W median GPU power: ambient background
  load was unchanged across a 9 h campaign, so no ambient-drift confound.
- Payload mirrored to `results/xe7740-8x-rtx6000/_local-evidence/xe7740-04/glm5.3/5-campaign/formal-20260907/`
  (1,847 files, 331,892,604 bytes) and declared in `results/xe7740-8x-rtx6000/EVIDENCE.md`. The mirror carries
  `run.sh` - the exact driver that produced the numbers - plus `preflight.json`, telemetry, and both
  idle baselines.

## Consequence worth keeping as a rule

28 formal decode runs existed on exactly one disk, in one directory, and had never been mirrored to
the evidence cache. The salvage copy in `formal-20260907-decode-salvage.md` is a transcription of a
parse, not the raw exports; it stood up the numbers in transit but is superseded by the mirrored
raw artifacts, which are what the claims validator must read. Long-running campaigns must push
completed artifacts off the host as they finish, not at the end: artifacts that only exist where
the compute happens are artifacts that only exist until the compute stops. This campaign got lucky,
and a rule that depends on luck is not a rule.
