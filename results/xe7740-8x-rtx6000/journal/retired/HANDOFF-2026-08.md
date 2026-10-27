<!--
  RETIRED 2026-09-06. A handoff document duplicates *state*, and state already
  has an owner: the campaign directory (chapter-mirrored evidence) and the
  journal. This file was referenced by nothing and is stale by construction.
  Kept as evidence per R-PIPE-4; not procedure. Read /PIPELINE.md instead.
-->

# Clean-Machine Handoff

This is the shortest path from a fresh supported Ubuntu host to a reproducible
campaign. It does not hide privileged changes or model/runtime licensing.

## 1. Review and provision

1. Read `harness/2-preflight-conformance/RULES.md` and `harness/2-preflight-conformance/code/configs/toolchain-policy.yaml`.
2. Review `harness/2-preflight-conformance/code/bootstrap/ubuntu-24.04-packages.txt`; install applicable packages
   through the site's approved package-management process.
3. Install a supported NVIDIA driver, Docker Engine/Compose, and NVIDIA
   Container Toolkit using vendor instructions.
4. Reboot if required, then verify `nvidia-smi` on the host and in a pinned CUDA
   container.
5. Clone this repository and create an isolated Python environment:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r harness/2-preflight-conformance/code/bootstrap/requirements.in
.venv/bin/pip freeze --all > bootstrap/requirements.lock
```

The generated lock is an installation receipt. For exact redistribution,
review it and produce a hash-locked requirements file or wheelhouse appropriate
to the target Python/platform; do not claim cross-platform bitwise package
reproduction from an unhashed input file.

## 2. Create a study record

Follow `INDEX.md` and create:

```text
results/<study-id>/
  README.md
  study.yaml
  configs/
  hosts/
  campaigns/
  journal/
  todos/
```

Record the host and all selected immutable versions. Raw results remain outside
Git.

## 3. Establish the results root and preflight

```bash
export LLM_BENCH_RESULTS_ROOT="$HOME/llm-benchmark-results"
harness/2-preflight-conformance/code/check-host.sh "$LLM_BENCH_RESULTS_ROOT/preflight-$(date -u +%Y%m%dT%H%M%SZ)"
```

Resolve every failure and review every warning. Optional counters remain
explicitly unavailable if the hardware or permissions do not expose them.

## 4. Deploy observability

Copy the generic observability example into the study, pin every OCI image by
digest, set a persistent VictoriaMetrics data directory, and review networking:

```bash
cp harness/2-preflight-conformance/code/deployments/observability/stack.compose.yaml results/<study-id>/configs/
cp harness/2-preflight-conformance/code/deployments/observability/scrape.example.yaml results/<study-id>/configs/
```

Do not blindly deploy the examples. Adjust host reachability, ports, retention,
container-runtime mounts, and security policy. Validate `/metrics`, scrape
targets, timestamps, and retention under a controlled load before benchmarking.

## 5. Acquire and verify the model

Record:

- repository and immutable revision;
- license/authentication path without storing secrets;
- complete file inventory and SHA-256 manifest;
- structural validation;
- tokenizer/chat-template revision;
- local absolute path and filesystem capacity.

If cryptographic upstream identity cannot be verified, state that explicitly.
Structural completeness is not cryptographic provenance.

## 6. Qualify and freeze deployment

Copy `harness/2-preflight-conformance/code/deployments/examples/openai-compatible.compose.yaml` or create a
runtime-specific equivalent in the study. Pin the image digest and all
capacity-affecting settings. Verify readiness with `/health`, not merely a model
listing endpoint. Record failed candidate configurations as qualification
evidence.

Capture environment, topology, link state, and the mandatory **B0 unloaded-idle
baseline before starting the model**. After the exact frozen model and load
balancer are healthy and startup work has completed, capture the mandatory
**B1-pre loaded-idle baseline** and static KV capacity:

```bash
harness/2-preflight-conformance/code/host/capture-environment.sh "$CAMPAIGN/preflight/environment"
harness/2-preflight-conformance/code/pcie/capture-topology.sh "$CAMPAIGN/preflight/topology"
harness/2-preflight-conformance/code/pcie/capture-link-state.sh "$CAMPAIGN/preflight/link-start.json"
harness/2-preflight-conformance/code/capture_idle.sh "$CAMPAIGN/idle/b0-unloaded" 300 unloaded
# Start and qualify model plus load balancer here.
harness/2-preflight-conformance/code/capture_idle.sh "$CAMPAIGN/idle/b1-pre-loaded" 300 loaded
```

Use 300-second windows when practical and never less than 60 seconds. Review
and set each idle manifest's `operator_assertions`; the tool cannot prove model
state or absence of requests by itself. Idle states are not C0 operating points,
and request throughput/latency are not applicable.

## 7. Define and validate the campaign

Copy `harness/5-formal-campaign/code/examples/campaign.yaml` into the study, replace every example
value, and freeze the model, revision, deployment ID, commands, profiles,
concurrency, seeds, repetitions, and telemetry endpoints.

Validate the schema and always inspect a dry run first:

```bash
python3 harness/5-formal-campaign/code/validate_spec.py results/<study-id>/configs/<campaign>.yaml \
  --schema harness/5-formal-campaign/schemas/campaign-spec.schema.json
python3 harness/5-formal-campaign/code/run_campaign.py results/<study-id>/configs/<campaign>.yaml \
  --results-root "$LLM_BENCH_RESULTS_ROOT" --dry-run
```

Delete that dry-run output or select a distinct campaign ID before real
execution. Verify the generated argv arrays and paths.

## 8. Execute and resume

After B1-pre loaded-idle, load-balancer, and service-health gates pass:

```bash
python3 harness/5-formal-campaign/code/run_campaign.py results/<study-id>/configs/<campaign>.yaml \
  --results-root "$LLM_BENCH_RESULTS_ROOT"
```

Use `--resume` only with the exact unchanged spec. Failed attempts are retained;
they are not overwritten. The runner writes `RUNS_COMPLETE` when every planned
operating point succeeds; this is not final campaign completion.

## 9. Aggregate and close

```bash
python3 harness/6-accept-and-publish/code/aggregate_campaign.py "$CAMPAIGN"
harness/2-preflight-conformance/code/pcie/capture-link-state.sh "$CAMPAIGN/postflight/link-end.json"
```

After all requests drain, capture the mandatory B1-post loaded-idle baseline,
then aggregate and finalize:

```bash
harness/2-preflight-conformance/code/capture_idle.sh "$CAMPAIGN/idle/b1-post-loaded" 300 loaded
python3 harness/6-accept-and-publish/code/aggregate_campaign.py "$CAMPAIGN"
python3 harness/5-formal-campaign/code/finalize_campaign.py "$CAMPAIGN"
```

Keep the model and load-balancer configuration unchanged between B1-pre,
measurement, and B1-post. B0 establishes empty-GPU host idle; B1-pre minus B0
estimates model-residency cost; active measurements minus B1-pre estimate
incremental workload cost; B1-post minus B1-pre exposes drift.

Review and set the idle operator assertions before finalization. The finalizer
validates required closeout files, writes hashes, and creates
`CAMPAIGN_COMPLETE` last. Then record exclusions and add or update the small
pointer under `results/<study-id>/campaigns/`. Never commit raw campaign data.

## Reproducibility boundary

This repository can reproduce the procedure and execution lifecycle. Numerical
performance is reproducible only within expected experimental variance on
sufficiently equivalent hardware, firmware, topology, software, model data, and
operating conditions. Secrets and licensed model payloads are deliberately not
bundled.
