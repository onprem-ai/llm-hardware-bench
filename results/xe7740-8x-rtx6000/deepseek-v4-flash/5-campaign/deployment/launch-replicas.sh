#!/usr/bin/env bash
# Start the shared DeepSeek-V4-Flash formal deployment.
# The same capability-preserving profile served Decode, Prefill, and Balanced.
set -euo pipefail

PROFILE="${1:?usage: launch-replicas.sh <formal|decode>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${MODEL:?set MODEL to the absolute host model directory}"
IMAGE="${IMAGE:?set IMAGE to the digest-pinned DeepSeek runtime image}"
STATE="${STATE:?set STATE to an empty receipt directory}"

case "${PROFILE}" in
  formal|decode) EXPECTED_MAX_SEQS=32; EXPECTED_GRAPH=192; LAUNCH_PROFILE=decode ;;
  *) echo "profile is not qualified: ${PROFILE}" >&2; exit 2 ;;
esac

[[ -d "${MODEL}" ]] || { echo "model path not found: ${MODEL}" >&2; exit 1; }
mkdir -p "${STATE}"

for suffix in a b c d; do
  docker rm -f "ds4-${suffix}" >/dev/null 2>&1 || true
done
docker rm -f ds4-lb >/dev/null 2>&1 || true

index=0
for suffix in a b c d; do
  first_gpu=$((index * 2))
  second_gpu=$((first_gpu + 1))
  port=$((8080 + index))
  docker run -d --name "ds4-${suffix}" --restart no \
    --gpus all --network host --ipc host --shm-size 32g \
    --entrypoint /bin/bash \
    -v /home/demouser/models:/home/demouser/models:ro \
    -v /home/demouser/.cache/huggingface:/root/.cache/huggingface \
    -v ds4-shared-jit:/cache \
    -v "${HERE}/${LAUNCH_PROFILE}/launch.sh:/launch.sh:ro" \
    -e "CUDA_VISIBLE_DEVICES=${first_gpu},${second_gpu}" \
    -e "MODEL_PATH=${MODEL}" \
    -e SERVED_MODEL_NAME=deepseek-v4-flash-0731 \
    -e "PORT=${port}" \
    "${IMAGE}" /launch.sh >"${STATE}/${suffix}-container-id.txt"

  # Compile graph-heavy replicas sequentially to avoid startup contention.
  ready=0
  for _ in $(seq 1 360); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1; then
      ready=1
      break
    fi
    state=$(docker inspect "ds4-${suffix}" --format '{{.State.Status}} {{.State.OOMKilled}} {{.State.ExitCode}}')
    [[ "${state}" == "running false 0" ]] || {
      echo "startup_failure backend=${suffix} state=${state}" >&2
      docker logs --tail 200 "ds4-${suffix}" >&2
      exit 1
    }
    sleep 5
  done
  [[ ${ready} -eq 1 ]] || { echo "readiness_timeout backend=${suffix}" >&2; exit 1; }
  docker logs "ds4-${suffix}" >"${STATE}/${suffix}-startup.log" 2>&1
  index=$((index + 1))
done

docker run -d --name ds4-lb --restart no --network host \
  -v "${HERE}/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro" \
  haproxy:3.2-alpine >"${STATE}/lb-container-id.txt"

docker inspect ds4-a ds4-b ds4-c ds4-d ds4-lb >"${STATE}/container-inspect.json"

for suffix in a b c d; do
  grep -q "max_num_seqs.: ${EXPECTED_MAX_SEQS}" "${STATE}/${suffix}-startup.log" || {
    echo "VERIFY max_num_seqs backend=${suffix} expected=${EXPECTED_MAX_SEQS}" >&2
    exit 1
  }
  grep -q "max_cudagraph_capture_size.: ${EXPECTED_GRAPH}" "${STATE}/${suffix}-startup.log" || {
    echo "VERIFY graph backend=${suffix} expected=${EXPECTED_GRAPH}" >&2
    exit 1
  }
  grep -q "num_spec_tokens=5" "${STATE}/${suffix}-startup.log" || {
    echo "VERIFY speculative tokens backend=${suffix} expected=5" >&2
    exit 1
  }
done

echo "profile_ready=${PROFILE} frontend=http://127.0.0.1:8084 time=$(date -u --iso-8601=seconds)"
