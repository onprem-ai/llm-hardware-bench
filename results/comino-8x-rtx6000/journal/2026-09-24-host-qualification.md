---
kind: record
status: current
date: 2026-09-24
device: comino-8xrtx6000
purpose: Host qualification and acquisition start
---

# Comino 8x RTX PRO 6000 - host qualification

## Device, measured

Comino workstation, bare metal (no container runtime found at qualification; Docker
29.8.1 + nvidia-container-toolkit 1.20.1 installed from upstream repos, nvidia runtime
configured). 8x RTX PRO 6000 Blackwell Server Edition, 97,887 MiB each, driver 595.91.07,
all eight idle at qualification (0 MiB, 0%), persistence mode Disabled (recorded as-is).
128 CPUs, MemTotal 791,713,492 KiB, Ubuntu 24.04.5, kernel 6.8.0-139-generic, /dev/shm
378 GiB. OS logical volume extended 100 GiB -> 914 GiB from the volume group's free space.
Full egress to PyPI, Hugging Face, and the Docker registry. No preexisting Docker.
Access configuration is deliberately not recorded; journals cover the LLM and the
benchmark only.

## Position in the cross-host set

Same GPU model as xe7740-8x-rtx6000 and s2-2x-rtx-6000; same per-replica shape is
therefore viable (TP2 over 2x97 GiB). No TP8-forced deviations and no MoE padding patch
are needed: the xe7740-qualified decode profile transfers verbatim
(max-running 48 / mamba 240 / graph 48 / prefill 32768 / chunked 4096, NEXTN 3/1/4, mem
0.95), with the SM120 QSA entrypoint patch carried verbatim from the found deployments.
The qualified load-generator client is pinned and locked from the s2 study's acquisition.

## Model acquisition (chapter 1)

Pinned revision resolved before payload transfer (R-01-1): repository
RadixArk/Qwen3.8-Flash-Next-NVFP4 @ 7b719225242aacd3dbd3f9407468c2ee9a9d2594, same pin
as the xe7740 and s2 studies; remote inventory written to the downloader state dir
(419 files, 135.3 GB expected, resolved sha equals requested). Destination
$HOME/bench/models/RadixArk--Qwen3.8-Flash-Next-NVFP4--model/ per R-01-2, downloader
state in a sibling directory. Transfer in progress at qualification time; structural
validation and the atomic receipt follow on completion (R-01-6, R-01-7).

Engine image: lmsysorg/sglang:qwen38flashnext@sha256:12d3392bdc8be8d35e9a95f191df6aef99c5114bdbefd41bfdc7e760e6d25ec1
- the same digest as the xe7740 and s2 deployments (R-01-13 external identifier).

## Next

Chapter 2 preflight on one TP2 replica through a one-backend load balancer, B0 idle
baseline, then the capacity seed raster (gen1) with the qualified decode profile, ahead
of a 4x TP2 campaign proposal.
