---
kind: record
produced_by: 1
title: s2 host qualification and deployment inventory
date: 2026-09-21
scope: qualification evidence, not a measurement campaign
---

# s2-2x-rtx-6000: host qualification and deployment inventory

Recorded 2026-09-21, before any measurement on this host. Everything below was
read from the host itself; nothing is inferred.

## Host

- serving node `ain-9g6ros`, single-node cluster, Ubuntu 24.04, kernel 6.17
- 24 CPU cores, MemTotal 63,400,524 KiB (preflight constant for the normalizer)
- 2x NVIDIA RTX PRO 6000 Blackwell Server Edition, 97,887 MiB each, driver 595.71.05
- scratch/results volume: 768 GiB at `/persistent`, 139 GiB free; benchmark
  artifacts go under `/persistent/tmp` (the node's designated scratch area),
  never the root filesystem
- the node also runs the management platform that fronts the model (API gateway,
  model registry, observability, auth) — its pods are long-lived and restart on
  their own schedule; a B0 ambient baseline is mandatory before any campaign
  (the eight-GPU host hit exactly this class of problem, see
  `results/xe7740-8x-rtx6000/todos/hold-observability-background-load-constant.md`)

## Model: revision already resolved, matches the eight-GPU study's pin

- `RadixArk/Qwen3.8-Flash-Next-NVFP4` at revision
  `7b719225242aacd3dbd3f9407468c2ee9a9d2594` — read from the checkpoint's own
  download-cache tree on the node. This is **the same revision** pinned by the
  published `results/xe7740-8x-rtx6000/qwen3.8-flash-next/publication.json`, so
  cross-host comparability holds and the chapter-1 provenance transfers.
- checkpoint audit on the node: `audit_unchanged_report.json` = 1562 files,
  118,408,052,728 bytes compared, verdict `pass` (mtp tables included)
- config: `Qwen4ExpForConditionalGeneration`, NVFP4 W4A4 group-16, routed experts
  scoped; PLE embedding tables and MTP head unquantized

## Deployment as found (not yet a benchmark profile)

- KServe InferenceService `rtx6k--qwen38-flash-next-nvfp4` (namespace
  `inference`), predictor pod 1/1, engine port 8080
- engine image `lmsysorg/sglang:qwen38flashnext` @
  `sha256:12d3392bdc8be8d35e9a95f191df6aef99c5114bdbefd41bfdc7e760e6d25ec1`
  (node-local registry mirror); the pod entrypoint patches the SGLang QSA
  attention backend at launch so SM120 is included in the working decode path
  (guard `is_sm100_supported` -> `is_sm100_supported or is_sm120_supported`),
  then launches the server; the patch is asserted, not blind
- launch contract (verbatim parameters): `--tp 2`, `--mem-fraction-static 0.95`,
  `--context-length 262144`, `--max-total-tokens 262144`,
  `--max-running-requests 1`, `--quantization modelopt_fp4`,
  `--fp4-gemm-backend flashinfer_cutlass`, `--page-size 64`,
  `--chunked-prefill-size 4096`, `--no-ple-offload-embedding`,
  `--linear-attn-prefill-backend triton`,
  `--linear-attn-decode-backend flashinfer`,
  `--mamba-ssm-dtype bfloat16`, `--mamba-radix-cache-strategy extra_buffer`,
  `--mamba-track-interval 64`, `--max-mamba-cache-size 16`,
  `--cuda-graph-max-bs-decode 1`, `--speculative-algorithm NEXTN`,
  `--speculative-num-steps 3`, `--speculative-eagle-topk 1`,
  `--speculative-num-draft-tokens 4`, reasoning/tool-call parsers `auto`
- container resources: requests 2 CPU / 8 GiB, limits 8 CPU / 16 GiB
- GPU residency as found: 72,814 MiB per GPU (two scheduler processes, TP rank
  per GPU)

**The found profile is a single-stream interactive profile, not a capacity
profile.** `--max-running-requests 1`, `--cuda-graph-max-bs-decode 1` and
`--max-mamba-cache-size 16` cap concurrency at one running request: measuring
it as-is would characterize queueing behind an admission ceiling of 1, which is
not serving capacity. A capacity raster needs profile candidates that raise the
admission and cache ceilings; that is chapter-3 work and a deployment change,
recorded as such.

## Smoke check (by effect, not by configuration)

A single-turn chat request to the deployment's public endpoint completed in
~1.05 s round trip with well-formed usage counters. This says the stack is
live; it is not a measurement and is not comparable to any campaign number.

## What this host is not

This is not the eight-GPU host and not the parked comino box; it is a new node,
new study directory, no comparators registered for it yet. Cross-host deltas
against `results/xe7740-8x-rtx6000/` comparators are legitimate only after this
host's own campaign completes chapter 6.
