#!/usr/bin/env bash
# Start the GLM-5.3 NVFP4 TP8 server for one profile.
#
# Reconstructed from the campaign's launch-and-run.sh on xe7740-04. Unlike the
# other models in this study, the configuration is not passed as flags: the
# image entrypoint expands baked-in environment variables into the vLLM
# invocation, so a profile IS an image. See deployment.yaml.
#
# The campaign produced the wide image by committing the narrow one with two
# changed variables:
#
#   docker commit --pause \
#     --change 'ENV MAX_NUM_SEQS=64' --change 'ENV GRAPH=256' \
#     radixark-glm53-graph128 local/radixark-glm53-r18-seq64-graph256:canary
#
set -euo pipefail

PROFILE="${1:?usage: launch.sh <seq32-graph128|seq64-graph256>}"
MODEL="${MODEL:-/home/demouser/models/RadixArk--GLM-5.3-NVFP4--model}"
CACHE_VOLUME="${CACHE_VOLUME:-radixark-glm53-canary-cache}"
PORT="${PORT:-8080}"

case "$PROFILE" in
  seq32-graph128)
    IMAGE=local/radixark-glm53-r18-graph128:canary
    EXPECT_SEQS=32; EXPECT_GRAPH=128 ;;
  seq64-graph256)
    IMAGE=local/radixark-glm53-r18-seq64-graph256:canary
    EXPECT_SEQS=64; EXPECT_GRAPH=256 ;;
  *) echo "unknown profile: $PROFILE" >&2; exit 2 ;;
esac

NAME="radixark-glm53-$PROFILE"
[[ -d $MODEL ]] || { echo "model path not found: $MODEL" >&2; exit 1; }
docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" --restart no \
  --gpus all --ipc host --security-opt label=disable \
  -p "$PORT:8080" \
  -v "$MODEL:/model:ro" \
  -v "$CACHE_VOLUME:/cache" \
  "$IMAGE"

deadline=$((SECONDS + 1800))
until curl -fsS --max-time 5 "http://127.0.0.1:$PORT/health" >/dev/null; do
  state=$(docker inspect "$NAME" --format '{{.State.Status}} {{.State.OOMKilled}} {{.State.ExitCode}}')
  [[ $state == 'running false 0' ]] || { echo "server_failed $state" >&2; docker logs --tail 200 "$NAME" >&2; exit 1; }
  ((SECONDS < deadline)) || { echo readiness_timeout >&2; docker logs --tail 200 "$NAME" >&2; exit 1; }
  sleep 5
done

# What the engine actually configured, not what the image requested.
evidence=$(docker logs "$NAME" 2>&1 | grep -E 'non-default args:|Initializing a V1 LLM engine|GPU KV cache size' | tail -10)
printf '%s\n' "$evidence"
grep -q "max_num_seqs.: $EXPECT_SEQS" <<<"$evidence" || { echo "VERIFY max_num_seqs != $EXPECT_SEQS" >&2; exit 1; }
grep -q "max_cudagraph_capture_size.: $EXPECT_GRAPH" <<<"$evidence" || { echo "VERIFY graph != $EXPECT_GRAPH" >&2; exit 1; }
grep -q "num_spec_tokens=3" <<<"$evidence" || { echo "VERIFY num_spec_tokens != 3" >&2; exit 1; }

echo "profile_ready=$PROFILE endpoint=http://127.0.0.1:$PORT time=$(date -u --iso-8601=seconds)"
