---
kind: record
produced_by: 2
title: Local evidence cache manifest
---


# Local evidence cache - 6.7 GiB, 15,661 files, untracked by design

Raw per-run evidence is too large and too noisy for git, so it lives in an ignored directory
next to the studies it supports. The tree **mirrors the record layout** - `<host>/<model>/<n-step>/` -
so a number in `results/xe7740-8x-rtx6000/<model>/<n-step>/` has a same-named cache directory beside it.

Location: `results/xe7740-8x-rtx6000/_local-evidence/`, ignored by the root `.gitignore`. Enforced by
`harness/check_repo.py`: an undeclared cache or a subtree missing from this manifest is a
violation, as is any tracked file over 5 MiB, a cache directory reusing a repository name at host
or model level, and a step level that is not `N-step`. Each moved directory carries
`PROVENANCE.txt`.

**This table is generated from the filesystem** by
`harness/2-preflight-conformance/code/generate_evidence_manifest.py`. A row that does not exist on
disk is a checker violation, so this file cannot outlive what it describes.

## Top level

| Directory | Meaning |
|---|---|
| `xe7740-04` | host directory; mirrors the node's filesystem layout |

## Contents, by host path (generated)

| Path under cache root | Files | Size | Oldest | Newest | What it is |
|---|---:|---|---|---|---|
| `xe7740-04/_unsorted-campaign-evidence/xe7740-04-hardware-capacity` | 11,100 | 4.2 GiB | 2026-08-28 | 2026-08-28 | pulled before the cache had a shape; not mapped to a step |
| `xe7740-04/glm5.3/5-campaign` | 4,255 | 2.5 GiB | 2026-08-27 | 2026-09-10 | step evidence, mirrors the record layout |
| `xe7740-04/_unsorted-aiperf/results` | 202 | 34.0 MiB | 2026-08-24 | 2026-08-24 | pulled before the cache had a shape; not mapped to a step |
| `xe7740-04/glm5.3/3-deployment-raster` | 29 | 7.6 MiB | 2026-08-27 | 2026-09-06 | step evidence, mirrors the record layout |
| `xe7740-04/glm5.3/1-model` | 33 | 3.9 MiB | 2026-08-27 | 2026-09-06 | step evidence, mirrors the record layout |
| `xe7740-04/_unsorted-website-orphan-reports` | 4 | 470.1 KiB | 2026-08-31 | 2026-09-06 | pulled before the cache had a shape; not mapped to a step |
| `xe7740-04/glm5.3-flash/1-model` | 33 | 154.8 KiB | 2026-08-27 | 2026-09-06 | step evidence, mirrors the record layout |
| `xe7740-04` | 2 | 75.1 KiB | 2026-08-28 | 2026-09-06 | host-level loose files (no model or step directory) |
| `xe7740-04/glm5.3/2-preflight-conformance` | 2 | 5.7 KiB | 2026-08-27 | 2026-09-06 | step evidence, mirrors the record layout |
| `xe7740-04/qwen3.8-flash-next/0-ram-20260910T212724Z` | 1 | 71.0 B | 2026-09-15 | 2026-09-15 | step evidence, mirrors the record layout |

## Hand-written notes

## `_unsorted-*`: admitted, not hidden

Two pulls predate the cache having any shape and are not mapped to steps: `_unsorted-aiperf`
(AIPerf result trees, 2026-08-28 formal stage) and `_unsorted-campaign-evidence` (per-run evidence
in the older host-first layout, including `hardware/idle-baselines` and
`models/deepseek-v4-flash/campaign-4xtp2-fp8-dspark5/`). Exempt from step naming **by prefix**,
listed above, and every file under them is counted. Mapping them is open work; guessing a step for
`combined/` would be worse than admitting the pile.

## Named by step, not by accident

`glm53/` was one pile of launch scripts, container dumps, image-build logs and result trees, and
held a directory called `studies` that held none. It is split: bring-up and image-build attempts
under `1-model/`, the VictoriaMetrics exporter under `2-preflight-conformance/`, launch scripts and
replica topology under `3-deployment-raster/`, measured runs under `5-campaign/`.

One artifact boundary is enforced by placement: `GLM-5.3-Flash-NVFP4-262K-2x-DGX-Spark/` is
**`LibertAIDAI/GLM-5.3-Flash-NVFP4`**, not `RadixArk/GLM-5.3-NVFP4`, so its bring-up bundle lives
under `glm5.3-flash/`, never `glm5.3/`.

## Authoritative copies, and what is not reproducible

- `XE7740-04:/home/demouser/glm53-raster/` - 16 raster generations, ~302 MB; authoritative for the
  2026-09-06 GLM-5.3 raster.
- `XE7740-04:/home/demouser/benchmarks/aiperf/` ~1.1 GB, and `/home/demouser/benchmarks/glm53/`.
- `XE7740-04:/home/demouser/bench/` is **empty** (directory mtime 2026-09-06 21:36), having held
  `run_aiperf_endpoint.sh` and earlier campaign logs. Raster generations 1, 7, 9 and 12 invoked it
  and are not directly re-runnable. Cause not established; do not assume the node is complete for
  pre-2026-09-06 campaigns.
- `gen13-session-peak-extension/` disappeared from the node between 21:36 and 23:15 on 2026-09-06,
  in the window when two raster controllers ran concurrently. Nothing published depends on it.

## Removals, with the authority that permitted them

`glm52/` (`CHANGELOG.md`, `start-server.sh`, `extract_result.py`, `run-stage1.sh`) and
`glm53/glm52-vllm-before-stop.inspect.json` were removed on 2026-09-07 **after** each was found on
the node and SHA-256-compared byte for byte (`/home/demouser/benchmarks/glm52/`,
`/home/demouser/benchmarks/glm53/`). They were never tracked, so this cache held no independent copy.

## Rules

- Never `git add -f` anything here; the 5 MiB ceiling exists to catch that.
- Never delete while the node copy is unverified; archive per `R-PIPE-4` and record the authority.
- New evidence goes under `<host>/<model>/<n-step>/` matching the step directory it supports.
- A cache directory may not reuse a repository top-level name at host or model level.

