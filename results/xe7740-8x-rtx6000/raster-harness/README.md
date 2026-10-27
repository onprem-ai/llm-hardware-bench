---
kind: record
produced_by: 3
title: Deployment raster harness as actually run on XE7740-04
---

# The raster harness, versioned

This is the code that produced every session-peak number in the GLM-5.3 raster journal. Until
2026-09-07 it existed **only** at `XE7740-04:/home/demouser/glm53-raster/`, which is not a backup:
one generation directory (`gen13-session-peak-extension/`) has already disappeared from that node
during a window when two controllers ran concurrently, and the node copy of `bench/` is empty
after having held the earlier bench helper. A method that exists on one disk is not a method.

| File | Role |
|---|---|
| `run-gen16.sh` | current candidate harness: order-controlled turnover run, boot-scaled readiness deadline |
| `run-gen15.sh` | expert-execution-width run behind the quality gate; source that gen16 was derived from |
| `free-8080.sh` | stops whatever holds :8080; prints `free8080_ok stopped=[...]` / `free8080_failed listeners_remain` and **stops but never removes** |
| `telemetry.sh` | per-candidate GPU/host sampling into `telemetry.csv` |
| `correctness.py` | the 7-check quality gate run before any timing measurement (see R-03-18 for why it was rewritten) |
| `metrics-delta.py` | /metrics before-after delta for acceptance-length attribution |
| `queue-14-then-15.sh` | pidfile-based serialisation; the empty-pid bug this replaced caused a two-controller collision |

Deploy by copying into a fresh directory on the node and editing `STATE`; **never** reconstruct a
launcher from memory (R-03-20). The node's own directory remains the running instance; this is the
source of record, and every generation's `run.sh` should be copied back here when a generation ends.

Conventions the scripts depend on, because they are invisible in a process listing: the image
entrypoint is `/usr/local/bin/serve-infernal-invocation.sh` with an empty CMD, so **never pass the
model as a positional argument**; `docker run -e` takes the **last** occurrence, so a switch is
cleared with a trailing `-e NAME=`; graph coverage must satisfy `max_num_seqs x (1 + MTP depth)`.
