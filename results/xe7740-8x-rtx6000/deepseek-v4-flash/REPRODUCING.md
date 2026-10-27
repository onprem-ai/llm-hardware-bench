# Reproducing the DeepSeek V4 Flash benchmark

The formal benchmark used one capability-preserving deployment for Decode,
Prefill, and Balanced. Run from the repository root on `xe7740-04`.

## Start and verify the deployment

```bash
export MODEL=/home/demouser/models/deepseek-ai--DeepSeek-V4-Flash-0731--model
export IMAGE='voipmonitor/vllm@sha256:48518e91cf87dd0c0483c76ff86e81dfc0f46de7e364b46f7a82c481ce08188f'
export STATE=/home/demouser/deepseek-formal-deployment-receipts

results/xe7740-8x-rtx6000/deepseek-v4-flash/deployment/launch-replicas.sh formal
```

The script starts four TP2 replicas sequentially, verifies the runtime-reported
sequence, graph, and DSpark settings, starts HAProxy `leastconn`, and preserves
startup logs and `docker inspect` output in `$STATE`.

## Validate and run the campaign

```bash
python3 harness/5-formal-campaign/code/validate_spec.py \
  results/xe7740-8x-rtx6000/deepseek-v4-flash/0-spec/deepseek-v4-flash-formal-20260902.yaml \
  --schema harness/5-formal-campaign/schemas/campaign-spec.schema.json

python3 harness/5-formal-campaign/code/run_campaign.py \
  results/xe7740-8x-rtx6000/deepseek-v4-flash/0-spec/deepseek-v4-flash-formal-20260902.yaml \
  --results-root /home/demouser/llm-benchmark-results
```

The specification contains all AIPerf arguments, workload shapes, randomization,
warm-up limits, telemetry collectors, three repetitions, and concurrency grid.
Use `--resume` only with the byte-identical campaign specification.

## Provenance limitation

The local checkpoint has stable local hashes recorded in `deployment.yaml`, but
no verified upstream download receipt. Do not replace `local-unverified` with an
upstream commit unless snapshot identity is independently established.
