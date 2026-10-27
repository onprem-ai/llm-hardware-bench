#!/usr/bin/env bash
# In-container server command for the decode-optimized profile.
#
# Recovered verbatim from the campaign's generated scripts at
#   .../formal-completion-v2/deployments/decode/{a,b,c,d}/launch.sh
# All four replicas were byte-identical apart from --port, so the port is the
# only value parameterised here.
#
# Runs inside local/qwen38-flash-next-sm120:operator-patched; see
# ../deployment.yaml for the container identity and its required SM120 patch.
set -euo pipefail
PORT="${PORT:?set PORT to the replica port, 8101 to 8104}"

exec python3 -m sglang.launch_server \
 --model-path /model --served-model-name qwen38-flash-next-nvfp4 \
 --host 127.0.0.1 --port "$PORT" --tp 2 --trust-remote-code \
 --mem-fraction-static 0.95 --context-length 262144 \
 --max-running-requests 48 --max-prefill-tokens 32768 \
 --quantization modelopt_fp4 --fp4-gemm-backend flashinfer_cutlass \
 --page-size 64 --chunked-prefill-size 4096 \
 --no-ple-offload-embedding \
 --linear-attn-prefill-backend triton --linear-attn-decode-backend flashinfer \
 --mamba-ssm-dtype bfloat16 --mamba-radix-cache-strategy extra_buffer \
 --mamba-track-interval 64 --max-mamba-cache-size 240 \
 --cuda-graph-max-bs-decode 48 \
 --speculative-algorithm NEXTN --speculative-num-steps 3 \
 --speculative-eagle-topk 1 --speculative-num-draft-tokens 4 \
 --reasoning-parser auto --tool-call-parser auto --enable-metrics
