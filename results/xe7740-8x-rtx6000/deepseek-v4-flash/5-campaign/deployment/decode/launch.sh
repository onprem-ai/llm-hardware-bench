#!/usr/bin/env bash
# In-container command for the selected Decode profile.
#
# Reconstructed from the 2026-09-02 qualification artifacts. The image
# entrypoint translates these explicit environment values into vLLM arguments.
set -euo pipefail

export MODEL_PATH="${MODEL_PATH:?set MODEL_PATH to the mounted model directory}"
export SERVED_MODEL_NAME="${SERVED_MODEL_NAME:?set SERVED_MODEL_NAME}"
export PORT="${PORT:?set PORT to the replica port, 8080 to 8083}"
export HOST="${HOST:-127.0.0.1}"
export MODE=dspark
export DSPARK_TOKENS=5
export DSPARK_DEPTH_MODE=fixed
export BACKEND=b12x-a8
export ALLREDUCE_MODE=b12x
export TP_SIZE=2
export DCP_SIZE=1
export MAX_NUM_SEQS=32
export MAX_NUM_BATCHED_TOKENS=8192
export MAX_MODEL_LEN=32768
export MAX_CUDAGRAPH_CAPTURE_SIZE=192
export GPU_MEMORY_UTILIZATION=0.975
export KV_CACHE_DTYPE=fp8
export KV_OFFLOADING_SIZE=48.5
export BLOCK_SIZE=256
export PREFIX_CACHE=0
export LOAD_FORMAT=instanttensor
export INSTANTTENSOR_BACKEND=BUFFERED
export NCCL_IB_DISABLE=1
export NCCL_P2P_LEVEL=SYS
export NCCL_PROTO=LL,LL128,Simple
export VLLM_DISABLED_KERNELS=MarlinFP8ScaledMMLinearKernel

exec /usr/local/bin/serve-ds4-flash.sh
