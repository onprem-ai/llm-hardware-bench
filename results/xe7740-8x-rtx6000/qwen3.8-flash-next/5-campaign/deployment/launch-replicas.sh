#!/usr/bin/env bash
# Start one profile's four TP2 replicas plus the load balancer.
#
# Recovered from /home/demouser/qwen38-grid-completion.sh on xe7740-04, which
# generated the per-replica launch scripts and ran the containers. Reconstructed
# here as a standalone script; the docker run flags, environment and mounts are
# reproduced exactly.
#
# The runtime admission check at the end is not optional. max-running-requests
# is a request: SGLang uses five Mamba state slots per active request for this
# model, so max-mamba-cache-size silently caps admission to floor(cache / 5).
# A campaign that requested 96 was capped to 3 and produced a spurious
# throughput plateau. See ../deployment.yaml.
set -euo pipefail

PROFILE="${1:?usage: launch-replicas.sh <decode|prefill>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${MODEL:-/home/demouser/models/RadixArk--Qwen3.8-Flash-Next-NVFP4--model}"
IMAGE="${IMAGE:-local/qwen38-flash-next-sm120:operator-patched}"
STATE="${STATE:-$HERE/.run}"

case "$PROFILE" in
  decode)  EXPECTED_MAXSEQ=48 ;;
  prefill) EXPECTED_MAXSEQ=24 ;;
  *) echo "unknown profile: $PROFILE" >&2; exit 2 ;;
esac

[[ -d $MODEL ]] || { echo "model path not found: $MODEL" >&2; exit 1; }
mkdir -p "$STATE"

for x in a b c d; do
  docker stop -t 45 "qwen38-flash-$x" >/dev/null 2>&1 || true
  docker rm "qwen38-flash-$x" >/dev/null 2>&1 || true
done
docker stop -t 20 qwen38-flash-lb >/dev/null 2>&1 || true
docker rm qwen38-flash-lb >/dev/null 2>&1 || true

idx=0
for x in a b c d; do
  g0=$((idx * 2)); g1=$((g0 + 1)); port=$((8101 + idx))
  # The campaign generated a per-replica launch.sh with the port baked in; here
  # one script is shared and the port passed as PORT.
  docker run -d --name "qwen38-flash-$x" --restart no \
    --gpus "\"device=$g0,$g1\"" \
    --ipc host --network host \
    --ulimit memlock=-1:-1 --cap-add IPC_LOCK --cap-add SYS_NICE \
    -v "$MODEL:/model:ro" \
    -v "$HERE/$PROFILE/launch.sh:/launch.sh:ro" \
    -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e NCCL_P2P_LEVEL=SYS \
    -e "PORT=$port" \
    "$IMAGE" bash /launch.sh >"$STATE/$x-container-id.txt"
  idx=$((idx + 1))
done

docker run -d --name qwen38-flash-lb --restart no --network host \
  -v "$HERE/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro" \
  haproxy:3.2-alpine >"$STATE/lb-container-id.txt"

# Wait for all four backends to accept connections.
for _ in $(seq 1 600); do
  good=0
  for x in a b c d; do
    state=$(docker inspect "qwen38-flash-$x" --format '{{.State.Status}} {{.State.OOMKilled}} {{.State.ExitCode}}')
    [[ $state == 'running false 0' ]] || {
      echo "startup_failure profile=$PROFILE backend=$x state=$state" >&2
      docker logs --tail 200 "qwen38-flash-$x" >&2
      exit 1
    }
  done
  for port in 8101 8102 8103 8104; do
    timeout 2 bash -c "</dev/tcp/127.0.0.1/$port" 2>/dev/null && good=$((good + 1)) || true
  done
  [[ $good -eq 4 ]] && break
  sleep 5
done

# Admission actually granted, not merely requested.
rc=0
for x in a b c d; do
  docker logs "qwen38-flash-$x" >"$STATE/$x-startup.log" 2>&1
  grep -Eq "max_running_requests.?[=: ]+$EXPECTED_MAXSEQ|max_running_requests is capped to $EXPECTED_MAXSEQ" \
    "$STATE/$x-startup.log" || {
      echo "VERIFY_MAXSEQ profile=$PROFILE backend=$x expected=$EXPECTED_MAXSEQ" | tee -a "$STATE/manual-review.txt" >&2
      rc=1
    }
done
[[ $rc -eq 0 ]] || { echo "admission ceiling not confirmed; measurements would be invalid" >&2; exit 1; }

echo "profile_ready=$PROFILE frontend=http://127.0.0.1:8000 time=$(date -u --iso-8601=seconds)"
