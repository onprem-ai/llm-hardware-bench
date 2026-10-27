#!/usr/bin/env bash
# Host-RAM cost of the 4xTP2 Qwen3.8-Flash-Next deployment.
#
# What it measures, per phase, from the engine containers' own cgroups plus host MemAvailable:
#   B0            idle reference, no engine running
#   loaded-idle   all four replicas loaded, before any request
#   C1/C8/C32/C64 load applied at the haproxy front, so all four replicas are active
#   B1-post       idle reference after teardown of load
# Per-replica detail lands in telemetry-ram.csv; the summed columns answer "what does the
# topology cost", the detail answers "is one replica heavier".
set -uo pipefail

IMAGE="local/qwen38-flash-next-sm120@sha256:380144b218f5e3c1c5e672e75248708f21cae135fac5497d3d3888f1aac5c668"
MODEL="/home/demouser/models/RadixArk--Qwen3.8-Flash-Next-NVFP4--model"
MODEL_ID="qwen3.8-flash-next-nvfp4"
BENCH=/home/demouser/benchmarks
OUT=/home/demouser/qwen38-ram-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$OUT"
# Append to the log directly. The first version used `exec > >(tee ...)`, and tee inherited the
# SSH stdout pipe, so the remote session never saw EOF and every launch over this link appeared to
# hang for the entire run. A benchmark that cannot be observed is a benchmark that gets killed.
exec >>"$OUT/run.log" 2>&1

die() { echo "REFUSE: $*" >&2; echo "$*" > "$OUT/REFUSED"; exit 2; }

[[ -d $MODEL ]] || die "model directory absent: $MODEL"
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "qualified SM120 image absent: $IMAGE"
busy=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)
(( busy == 0 )) || die "$busy compute processes still hold the GPUs; stop them deliberately, not here"

idle() {
  timeout "${2:-12}" nvidia-smi --query-gpu=timestamp,power.draw \
    --format=csv,noheader,nounits -lms 500 > "$OUT/$1" 2>/dev/null
  sed -i '1i timestamp,power_w' "$OUT/$1"
  echo "  $1: $(($(wc -l < "$OUT/$1")-1)) samples"
}
host_avail() { awk '/MemAvailable/{print $2}' /proc/meminfo; }

idle B0-idle.csv
base_avail=$(host_avail)
echo "  host MemAvailable before any engine: $((base_avail/1048576)) GiB"

names=(); ports=()
for i in 0 1 2 3; do
  cid=$(docker run -d --name "qwen38-ram-r$i" --gpus "\"device=$((i*2)),$((i*2+1))\"" \
    --ipc host --shm-size 32g --ulimit memlock=-1:-1 --network host \
    -v "$MODEL":/models/qwen:ro "$IMAGE" \
    python3 -m sglang.launch_server --model-path /models/qwen \
      --served-model-name "$MODEL_ID" --host 127.0.0.1 --port $((30000+i)) \
      --tp 2 --trust-remote-code --mem-fraction-static 0.95 --context-length 262144 \
      --max-running-requests 48 --max-prefill-tokens 32768 --quantization modelopt_fp4 \
      --fp4-gemm-backend flashinfer_cutlass --page-size 64 --chunked-prefill-size 4096 \
      --no-ple-offload-embedding --linear-attn-prefill-backend triton \
      --linear-attn-decode-backend flashinfer --mamba-ssm-dtype bfloat16 \
      --mamba-radix-cache-strategy extra_buffer --mamba-track-interval 64 \
      --max-mamba-cache-size 240 --cuda-graph-max-bs-decode 48 \
      --speculative-algorithm NEXTN --speculative-num-steps 3 --speculative-eagle-topk 1 \
      --speculative-num-draft-tokens 4 --reasoning-parser auto --tool-call-parser auto \
      --enable-metrics) || die "replica $i failed to start"
  [[ -n $cid ]] || die "replica $i produced no container id"
  names+=("qwen38-ram-r$i"); ports+=($((30000+i)))
done

echo "  waiting for four /health endpoints (weights load takes minutes)"
for i in 0 1 2 3; do
  for t in $(seq 1 180); do
    curl -fsS --max-time 5 "http://127.0.0.1:$((30000+i))/health" >/dev/null 2>&1 && break
    sleep 10
    docker inspect -f '{{.State.Running}}' "qwen38-ram-r$i" | grep -q true \
      || die "replica $i died during load; see docker logs"
    (( t == 180 )) && die "replica $i never became healthy in 30 min"
  done
  echo "    replica $i healthy after ${t}0s"
done

docker run -d --name qwen38-ram-lb --network host \
  -v /home/demouser/benchmarks/haproxy-4xtp2.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro \
  haproxy:2 >/dev/null || die "haproxy front failed"

sampler_args=(--container "$(IFS=,; echo "${names[*]}")")
"$BENCH/aiperf/.venv/bin/python3" "$BENCH/telemetry-sampler.py" \
  "${sampler_args[@]}" --out "$OUT/telemetry.csv" --interval 1 &
SAMP=$!
sleep 1
kill -0 $SAMP || die "sampler exited before the first sample"

sleep 15; idle loaded-idle.csv 8
echo "  loaded-idle: $(tail -1 "$OUT/telemetry.csv" | awk -F, '{printf "engine anon %.1f GiB, file %.1f GiB, current %.1f GiB, n=%s", $46/1073741824, $47/1073741824, $49/1073741824, $51}')"

for C in 1 8 32 64; do
  echo "  === C$C ==="
  "$BENCH/aiperf/.venv/bin/aiperf" profile --model "$MODEL_ID" \
    --url http://127.0.0.1:8100 --endpoint-type chat --endpoint /v1/chat/completions \
    --streaming --dataset-type synthetic --synthetic-input-tokens-mean 2048 \
    --output-tokens-mean 1 --concurrency "$C" --benchmark-duration 45 \
    --use-server-token-count --extra-inputs '{"temperature":0,"ignore_eos":false}' \
    --random-seed $((500000+C)) --generate-profile-export --profile-export-folder "$OUT/c$C" \
    > "$OUT/c$C.log" 2>&1
  echo "    exit=$?  tok/s=$(grep -oE '[0-9]+\.[0-9]+' "$OUT/c$C.log" | head -1)"
  sleep 5
done

kill $SAMP 2>/dev/null; wait $SAMP 2>/dev/null
docker rm -f qwen38-ram-lb "${names[@]}" >/dev/null 2>&1
sleep 20; idle B1-post-idle.csv 12
end_avail=$(host_avail)
echo "  host MemAvailable after teardown: $((end_avail/1048576)) GiB  (delta $(( (base_avail-end_avail)/1048576 )) GiB)"
python3 - "$OUT" <<'PY'
import csv, json, sys, statistics
out=sys.argv[1]
rows=list(csv.DictReader(open(f"{out}/telemetry.csv")))
need=("engine_ram_anon_bytes","engine_ram_current_bytes","engine_container_count")
if not rows or not all(k in rows[0] for k in need):
    sys.exit("telemetry lacks engine RAM fields -- sampler is the pre-RAM version")
peak=max(int(r["engine_ram_current_bytes"]) for r in rows if r["engine_ram_current_bytes"].isdigit())
anon=max((int(r["engine_ram_anon_bytes"]) for r in rows if r["engine_ram_anon_bytes"].isdigit()), default=0)
summary={"samples":len(rows),
         "containers":int(rows[0]["engine_container_count"]),
         "engine_current_peak_gib":round(peak/2**30,2),
         "engine_anon_peak_gib":round(anon/2**30,2),
         "per_replica_peak_gib":{}}
try:
    det=list(csv.DictReader(open(f"{out}/telemetry-ram.csv")))
    per={}
    for r in det:
        if r["memory_current_bytes"].isdigit():
            per[r["container"]]=max(per.get(r["container"],0), int(r["memory_current_bytes"]))
    summary["per_replica_peak_gib"]={k:round(v/2**30,2) for k,v in per.items()}
except FileNotFoundError:
    summary["per_replica"]="no telemetry-ram.csv written"
json.dump(summary, open(f"{out}/ram-summary.json","w"), indent=2)
print(json.dumps(summary, indent=2))
PY
echo "  DONE: $OUT"
