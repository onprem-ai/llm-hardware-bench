#!/usr/bin/env bash
set -euo pipefail
OUT=${1:?usage: run-p2p-matrix.sh OUTPUT_DIR}
IMAGE=${FABRIC_RUNTIME_IMAGE:?set FABRIC_RUNTIME_IMAGE to immutable digest}
BINARY=${P2P_BINARY:-/opt/llm-bench-tools/bin/p2pBandwidthLatencyTest}
mkdir -p "$OUT"
printf 'started_at=%s\nimage=%s\nbinary=%s\n' \
  "$(date -u --iso-8601=ns)" "$IMAGE" "$BINARY" > "$OUT/manifest.txt"
docker run --rm --gpus all --ipc=host -v "$(dirname "$BINARY"):$(dirname "$BINARY"):ro" --entrypoint "$BINARY" "$IMAGE" > "$OUT/p2pBandwidthLatencyTest.log" 2>&1
printf 'ended_at=%s\nreturn_code=0\n' "$(date -u --iso-8601=ns)" >> "$OUT/manifest.txt"
