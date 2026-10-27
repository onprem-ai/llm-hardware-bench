# Campaign runner

`run_campaign.py` executes a campaign specification conforming to
`harness/5-formal-campaign/schemas/campaign-spec.schema.json`. Validate edited records before use:

```bash
python3 harness/5-formal-campaign/code/validate_spec.py <campaign.yaml> \
  --schema harness/5-formal-campaign/schemas/campaign-spec.schema.json
```

## Safety and lifecycle

- Commands are argument arrays and never interpreted by a shell.
- `--dry-run` materializes the complete randomized run plan without contacting
  an endpoint or executing benchmark/collector commands.
- An existing campaign requires `--resume`.
- Resume is rejected if the specification hash changed.
- Runs already in a terminal state are not overwritten.
- Every run receives an immutable UUID-bearing directory and atomic manifest.
- Collector processes are terminated after the measured command, including on
  interruption or failure.
- `RUNS_COMPLETE` is written when every planned run completed.
- `finalize_campaign.py` writes `CAMPAIGN_COMPLETE` only after aggregation,
  post-idle evidence, and run-manifest checks succeed.
- Benchmark outputs are not checksummed. Cryptographic checksums are reserved
  for downloaded model data; see `harness/1-model-qualification/RULES.md`.
- A failed run is preserved and stops execution; resume creates a new run for
  that operating point rather than overwriting evidence.

## Use

Validate the example without GPUs:

```bash
python3 harness/5-formal-campaign/code/run_campaign.py harness/5-formal-campaign/code/examples/campaign.yaml \
  --results-root /tmp/llm-bench-plan --dry-run
```

Run the bundled mock integration campaign:

```bash
python3 harness/5-formal-campaign/code/run_campaign.py harness/5-formal-campaign/code/examples/mock-campaign.json \
  --results-root /tmp/llm-bench-test
CAMPAIGN=/tmp/llm-bench-test/$(hostname | tr A-Z a-z)/mock/0123456789ab/mock-r1-tp1/mock-capacity
python3 harness/6-accept-and-publish/code/aggregate_campaign.py "$CAMPAIGN"
# For this mock only; real campaigns require a post-idle capture:
python3 harness/5-formal-campaign/code/finalize_campaign.py "$CAMPAIGN" --allow-missing-post-idle
```

For a real campaign, copy the example into the relevant study's `configs/`
and pin all model/deployment/runtime values. Verify the generated command plan,
server health, telemetry targets, idle baselines, and deployment-capacity record
before removing `--dry-run`.

The example targets AIPerf 0.12.0 semantics. Run `aiperf profile --help` on the
pinned environment and review every option before execution; external CLI
interfaces can change.

## Warm-up request cap

Profiles may set `warmup_requests_cap`. The runner computes:

```text
min(max(4, warmup_requests_multiplier × concurrency), warmup_requests_cap)
```

For deployments with a known sequence limit, a recommended starting cap is
`2 × max_num_seqs`. The cap must be frozen before launch. Never edit an active
campaign's specification: resume protection intentionally rejects a changed
specification hash.

## Current scope

The runner handles the profile × concurrency × repetition execution core,
local collectors, exact run timestamps, delayed VictoriaMetrics export, atomic
manifests, and resume protection. Deployment launch/teardown and loaded-idle
baselines remain explicit campaign-stage operations because they are highly
runtime- and model-specific. They must be referenced by the campaign's study
records and preserved as artifacts.
