#!/usr/bin/env bash
# In-container server command for the prefill-optimized-uncached profile.
#
# Recovered verbatim from the campaign's generated scripts at
#   .../formal-completion-v2/deployments/prefill/{a,b,c,d}/launch.sh
# All four replicas were byte-identical apart from --port.
#
# Differs from the decode profile in six flags: narrower admission and decode
# graph, larger prefill and chunk sizes, half the Mamba cache, no speculative
# decoding, and radix cache disabled so prefill is measured uncached.
set -euo pipefail
PORT="${PORT:?set PORT to the replica port, 8101 to 8104}"

exec python3 -m sglang.launch_server \
 --model-path /model --served-model-name qwen38-flash-next-nvfp4 \
 --host 127.0.0.1 --port "$PORT" --tp 2 --trust-remote-code \
 --mem-fraction-static 0.95 --context-length 262144 \
 --max-running-requests 24 --max-prefill-tokens 65536 \
 --quantization modelopt_fp4 --fp4-gemm-backend flashinfer_cutlass \
 --page-size 64 --chunked-prefill-size 16384 \
 --no-ple-offload-embedding \
 --linear-attn-prefill-backend triton --linear-attn-decode-backend flashinfer \
 --mamba-ssm-dtype bfloat16 --mamba-radix-cache-strategy extra_buffer \
 --mamba-track-interval 64 --max-mamba-cache-size 120 \
 --cuda-graph-max-bs-decode 24 \
 --disable-radix-cache \
 --reasoning-parser auto --tool-call-parser auto --enable-metrics
