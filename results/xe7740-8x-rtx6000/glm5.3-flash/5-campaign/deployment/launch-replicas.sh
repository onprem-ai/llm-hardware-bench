#!/usr/bin/env bash
set -euo pipefail
MODEL_DIR="$HOME/models/LibertAIDAI--GLM-5.3-Flash-NVFP4--model"
ROOT="$HOME/benchmarks/glm53/two-replica"
IMAGE="local/vllm-glm53-flash:sm120-v8"
mkdir -p "$ROOT/logs"

COMMON=(
  --model /model
  --served-model-name glm-5.3-flash-nvfp4
  --tensor-parallel-size 4
  --trust-remote-code
  --max-model-len 1048576
  --max-num-seqs 94
  --max-num-batched-tokens 8192
  --block-size 2304
  --gpu-memory-utilization 0.95
  --kv-cache-dtype fp8_e4m3
  --moe-backend marlin
  --speculative-config '{"method":"mtp","num_speculative_tokens":4}'
  --tool-call-parser glm47
  --enable-auto-tool-choice
  --reasoning-parser glm45
)
ENV_ARGS=(
  -e VLLM_ENGINE_READY_TIMEOUT_S=3600
  -e HF_HUB_OFFLINE=1
  -e TRANSFORMERS_OFFLINE=1
  -e FLASHINFER_DISABLE_VERSION_CHECK=1
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
)

# Preserve unrelated observability containers; replace only model services/LB.
docker rm -f glm53-a glm53-b glm53-lb glm53-vllm >/dev/null 2>&1 || true
docker stop glm52-vllm >/dev/null 2>&1 || true


docker run -d --name glm53-a --restart unless-stopped \
  --gpus all --network host --ipc=host --shm-size=32g \
  -e CUDA_VISIBLE_DEVICES=0,1,2,3 "${ENV_ARGS[@]}" \
  -v "$MODEL_DIR:/model:ro" \
  "$IMAGE" "${COMMON[@]}" --host 127.0.0.1 --port 8080 \
  > "$ROOT/logs/replica-a-container-id.txt"

docker run -d --name glm53-b --restart unless-stopped \
  --gpus all --network host --ipc=host --shm-size=32g \
  -e CUDA_VISIBLE_DEVICES=4,5,6,7 "${ENV_ARGS[@]}" \
  -v "$MODEL_DIR:/model:ro" \
  "$IMAGE" "${COMMON[@]}" --host 127.0.0.1 --port 8081 \
  > "$ROOT/logs/replica-b-container-id.txt"

echo "Replicas launched. Wait for both /health endpoints before starting HAProxy."
