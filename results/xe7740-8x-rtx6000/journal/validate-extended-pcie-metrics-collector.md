# Validate the Extended PCIe Metrics Collector

```yaml
status: complete
trigger: satisfied
owner: unassigned
completed_at: 2026-08-29T16:02:44Z
completion_record: ../journal/2026-08-29-fabric-closeout.md
result_pointer: ../campaigns/fabric-qualification-20260829.yaml
```

## Purpose and status

Validate and qualify the PCIe/DCGM collector on `xe7740-04`, including P2P,
NCCL, NUMA, and uncore evidence. The work completed after the Qwen3.8 campaign
finished. The historical checklist below is retained as an audit record; the
result pointer and completion journal above are authoritative.

At the time this checklist was created (`2026-08-29T12:32:51Z`), the campaign
was still active: the `qwen38-auto-study` tmux session existed, no
`CAMPAIGN_COMPLETE` marker existed, and benchmark processes were running.

Active campaign:

```text
/home/demouser/benchmarks/results/xe7740-8x-rtx6000/qwen38-flash/campaign-2xtp4-optimized-20260829
```

The reusable procedure and tooling are documented at:

- `harness/2-preflight-conformance/code/deployments/observability/README.md`
- `PROCEDURE.md`, Section 8.7
- `collectors/dcgm/`, `collectors/pcie/`, and `collectors/victoriametrics/`

The server working copy was `/home/demouser/llm-inference-hardware-bench` when
this TODO was recorded.

**Do not execute active fabric tests or alter observability while that campaign
is running or being finalized.**

## Entry gates

All boxes must be satisfied before changing services or generating fabric load:

- [ ] The campaign controller has exited normally.
- [ ] All expected 72 base runs have been accounted for.
- [ ] Run manifests, raw AIPerf output, HTTP traces, and local telemetry exist.
- [ ] Delayed VictoriaMetrics exports cover the exact measured intervals.
- [ ] Post-campaign loaded-idle baseline has completed.
- [ ] Campaign manifests and hashes have been finalized.
- [ ] `CAMPAIGN_COMPLETE` exists, or an explicit interruption record explains
      why the campaign is closed without it.
- [ ] Any required adaptive extra repetitions have either completed or been
      explicitly deferred.
- [ ] Qwen inference and benchmark-client processes have been intentionally
      stopped and verified absent.
- [ ] An idle maintenance window has been approved.

A missing tmux session or absent AIPerf process alone does not prove campaign
completion.

## Phase 1 — preserve the current state

Before stopping or replacing any observability component:

- [ ] Record UTC time and operator.
- [ ] Capture `docker ps`, `docker inspect obs-dcgm-exporter`, and exporter logs.
- [ ] Record the exact exporter image digest and reported exporter/DCGM version.
- [ ] Preserve the current collector configuration and VictoriaMetrics scrape
      configuration.
- [ ] Save the current `http://127.0.0.1:9400/metrics` response.
- [ ] Record all VictoriaMetrics target health states.
- [ ] Record rollback commands before making a change.

Expected observed reference, to be verified rather than assumed:

```text
container: obs-dcgm-exporter
image: nvcr.io/nvidia/k8s/dcgm-exporter:4.8.3
observed digest: sha256:613ab03c11d442fd960ff515f547e9921537454a712d08160bc8f677f89f1c35
reported version: 4.6.0-4.8.3
```

## Phase 2 — static topology baseline

Create a new canonical external campaign with purpose `fabric`; do not store raw
results in Git. Resolve its path under:

```text
${LLM_BENCH_RESULTS_ROOT:-/home/demouser/llm-benchmark-results}
```

Then capture static topology before active testing:

```bash
cd /home/demouser/llm-inference-hardware-bench
harness/2-preflight-conformance/code/pcie/capture-topology.sh "$FABRIC_CAMPAIGN/topology/pre"
harness/2-preflight-conformance/code/pcie/capture-link-state.sh "$FABRIC_CAMPAIGN/topology/link-pre.json"
```

Review GPU BDFs, switch/bridge ancestry, root complexes, NUMA nodes, IOMMU/ACS
state, negotiated link generation/width, BAR1, P2P capability, and NVLink state.
Do not infer link properties from GPU specifications.

## Phase 3 — DCGM field discovery

- [ ] Obtain a version-matched DCGM utility package/container containing
      `dcgmi`; the exporter image currently may not contain it.
- [ ] Record its image digest/package version.
- [ ] Run discovery for every GPU:

```bash
DCGM_CONTAINER=<reviewed-matching-utility-container> \
  harness/2-preflight-conformance/code/dcgm/discover-fields.sh "$FABRIC_CAMPAIGN/dcgm/discovery"
```

- [ ] Preserve `dcgmi dmon --list` and every per-GPU
      `dcgmi profile --list --entity-id gpu:N` result.
- [ ] Record heterogeneous support, permission failures, and profiling-group
      restrictions explicitly.

Discovery only reports potential support. Runtime `/metrics` emission and
controlled-load behavior must still be validated.

## Phase 4 — qualification exporter

Do not casually run two embedded DCGM host engines. During the idle window:

1. Stop the original exporter after its state has been preserved.
2. Render and review the qualification Compose file.
3. Start the qualification exporter on loopback port `19400`.
4. Preserve startup logs and verify `/metrics`.

```bash
export DCGM_EXPORTER_IMAGE='nvcr.io/nvidia/k8s/dcgm-exporter@sha256:613ab03c11d442fd960ff515f547e9921537454a712d08160bc8f677f89f1c35'
docker compose -f harness/2-preflight-conformance/code/deployments/observability/dcgm-exporter.compose.yaml config
docker compose -f harness/2-preflight-conformance/code/deployments/observability/dcgm-exporter.compose.yaml up -d
curl -f http://127.0.0.1:19400/metrics
```

These commands are examples, not authorization to execute them before the entry
gates pass.

## Phase 5 — idle and controlled-load validation

First capture an idle comparison without claiming a load occurred:

```bash
harness/2-preflight-conformance/code/dcgm/validate-fields.sh \
  --endpoint http://127.0.0.1:19400/metrics \
  --output "$FABRIC_CAMPAIGN/dcgm/idle-validation"
```

Then run an independently recorded controlled PCIe workload spanning the sample
interval and validate with `--load-executed`:

```bash
harness/2-preflight-conformance/code/dcgm/validate-fields.sh \
  --load-executed --wait 30 \
  --endpoint http://127.0.0.1:19400/metrics \
  --output "$FABRIC_CAMPAIGN/dcgm/controlled-load-validation"
```

For each field classify separately:

- emitted and changed under load;
- emitted but static under load;
- emitted but not tested under load;
- intermittent;
- not emitted;
- permission denied;
- unsupported;
- profiling conflict.

Never translate any unavailable state to numeric zero. Remember that
`DCGM_FI_PROF_PCIE_RX_BYTES` and `TX_BYTES` are interval-average byte-rate
gauges, while `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` is cumulative.

## Phase 6 — active P2P, NCCL, and NUMA qualification

Pin and hash the CUDA P2P binary and `nccl-tests` commit/build before testing.
Capture raw output and errors for every test.

Required matrix:

- [ ] CUDA P2P bandwidth and latency across all GPU pairs and both directions.
- [ ] Same-NUMA representative pairs.
- [ ] Cross-NUMA representative pairs.
- [ ] Production TP group GPUs 0–3.
- [ ] Production TP group GPUs 4–7.
- [ ] Deliberately cross-NUMA four-GPU group of equal size.
- [ ] All eight GPUs.
- [ ] `all_reduce_perf` over latency- and bandwidth-sensitive sizes.
- [ ] `all_gather_perf` over the same size range.
- [ ] `reduce_scatter_perf` over the same size range.
- [ ] Pinned versus unpinned CPU/NUMA placement where safe and supported.
- [ ] Identical rank counts, sizes, iterations, and warmups for topology
      comparisons.

Record CUDA, driver, NCCL, binary hash, build flags, GPU ordering,
`CUDA_VISIBLE_DEVICES`, NCCL environment, CPU affinity, memory policy, message
sizes, iterations, warmups, correctness failures, `algbw`, and `busbw`.

Active fabric tests must not overlap inference measurements.

## Phase 7 — interpretation and passive-collector decision

- [ ] Compare same-NUMA and cross-NUMA results.
- [ ] Identify asymmetry and weak links in the directional P2P matrix.
- [ ] Compare negotiated links with measured endpoint traffic and NCCL results.
- [ ] Check replay/error deltas and link downshifts.
- [ ] Determine which DCGM fields are reliable enough for future per-run passive
      collection.
- [ ] Document unsupported fields rather than deleting them from history.
- [ ] Do not call endpoint RX/TX a direct PCIe-switch internal counter.
- [ ] Do not equate NCCL `busbw`, `algbw`, endpoint payload rate, or PCIe line
      rate.

A throughput plateau alone is not proof of a PCIe bottleneck.

## Acceptance criteria

The TODO is complete only when:

- every requested metric has an evidence-backed availability state;
- PCIe RX/TX behavior is validated under a recorded load or marked unavailable;
- P2P and required NCCL topology cases have raw receipts;
- the original exporter is restored and its scrape target is healthy;
- a fabric campaign pointer and completion journal entry exist;
- unsupported/conflicting fields and all test limitations are documented.

## Phase 8 — rollback and closeout

- [ ] Capture post-test topology and link state.
- [ ] Stop and remove only the qualification exporter.
- [ ] Restore the original exporter exactly.
- [ ] Verify port `9400`, target health, expected metrics, and VictoriaMetrics
      ingestion.
- [ ] Preserve qualification and restored-exporter logs.
- [ ] Finalize the fabric manifest using
      `harness/2-preflight-conformance/schemas/fabric-qualification.schema.json`.
- [ ] Hash all qualification artifacts.
- [ ] Write the fabric campaign completion marker last.
- [ ] Record which host configuration changes would invalidate this baseline.

Repeat host-level qualification after material changes to GPU placement, PCIe
hardware/firmware, BIOS, kernel/IOMMU configuration, NVIDIA driver, DCGM, CUDA,
NCCL, or NUMA policy. Future model campaigns should still collect passive PCIe
telemetry for every measured run.
