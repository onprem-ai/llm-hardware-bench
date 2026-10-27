#!/usr/bin/env bash
# Corrected rerun of three things that never produced data:
#   step 1: protocol-fidelity probe (90 s windows, 3 reps) on the published control
#   step 2: MTP speculation-depth raster 3/2/1/0 with matched graph coverage
#   step 3: expert-mode raster A16 / A8 / native W4A4 behind a quality gate
# One bench definition, seven arguments, explicit window and repetitions.
set -uo pipefail
STATE=/home/demouser/glm53-raster/gen15-expert-on-new-base
MODEL=/home/demouser/models/RadixArk--GLM-5.3-NVFP4--model
IMAGE=local/radixark-glm53-r18-seq64-graph256:canary
A=/home/demouser/benchmarks/aiperf/.venv/bin/aiperf
URL=http://127.0.0.1:8080
NAME=radixark-glm53-raster
exec > >(tee -a "$STATE/controller.log") 2>&1
trap 'rc=$?; kill "$(cat "$STATE/telemetry.pid" 2>/dev/null)" 2>/dev/null || true; if [ "$rc" -ne 0 ] && [ ! -f "$STATE/COMPLETE" ]; then date -u +%FT%TZ > "$STATE/ABORTED"; fi; echo "$(date -u +%FT%TZ) controller_exit=$rc"; exit $rc' EXIT
echo "$(date -u +%FT%TZ) start" > "$STATE/STARTED"
bash /home/demouser/glm53-raster/telemetry.sh "$STATE/telemetry.csv" "$NAME" & echo $! > "$STATE/telemetry.pid"
wait_ready() { # cs
  local cs=$1 ready=0 n st
  for n in $(seq 1 200); do
    curl -fsS --max-time 3 "$URL/health" >/dev/null 2>&1 && { ready=1; break; }
    st=$(docker inspect "$NAME" --format '{{.State.Status}} {{.State.OOMKilled}}' 2>/dev/null || true)
    [[ "$st" == 'running false' ]] || break
    sleep 5
  done
  docker logs "$NAME" > "$cs/startup.log" 2>&1 || true
  if [[ $ready -ne 1 ]]; then
    docker inspect "$NAME" > "$cs/container-inspect.json" 2>/dev/null || true
    grep -iE 'out of memory|CUDA error|exceeds|Error' "$cs/startup.log" | tail -5 > "$cs/failure-signals.txt" || true
    return 1
  fi
  grep -oE "'(max_num_seqs|max_cudagraph_capture_size|num_speculative_tokens|max_num_batched_tokens|gpu_memory_utilization|kv_cache_dtype)': '?[^,]*" "$cs/startup.log" | sort -u > "$cs/params.txt" || true
  grep -oE 'GPU KV cache size: [0-9,]+ tokens' "$cs/startup.log" | tail -1 > "$cs/kv-cache.txt" || true
  grep -oE 'Maximum concurrency for [0-9,]+ tokens per request: [0-9.]+x' "$cs/startup.log" | tail -1 >> "$cs/kv-cache.txt" || true
  return 0
}
bench() { # label kind conc isl osl window_seconds reps
  local label=$1 kind=$2 c=$3 isl=$4 osl=$5 win=$6 reps=$7
  local out="$STATE/$label/$kind-C$c"; mkdir -p "$out"
  if [[ -f "$out/rep${reps}/profile_export_aiperf.json" ]]; then
    echo "$(date -u +%FT%TZ) resume_skip $label $kind-C$c" | tee -a "$STATE/progress.log"; return 0
  fi
  "$A" profile --model glm-5.3-nvfp4-radixark --tokenizer "$MODEL" --endpoint-type chat --endpoint /v1/chat/completions --streaming --url "$URL" \
   --synthetic-input-tokens-mean "$isl" --synthetic-input-tokens-stddev 0 --output-tokens-mean "$osl" --output-tokens-stddev 0 --concurrency "$c" --request-count "$((c>32?c:32))" \
   --use-server-token-count --random-seed 953601 --extra-inputs '{"temperature":0,"ignore_eos":true}' --request-timeout-seconds 1800 --output-artifact-dir "$out/warmup" > "$out/warmup.log" 2>&1
  sleep 10
  curl -fsS "$URL/metrics" > "$out/metrics-before.txt" 2>/dev/null || true
  local r
  for r in $(seq 1 "$reps"); do
    "$A" profile --model glm-5.3-nvfp4-radixark --tokenizer "$MODEL" --endpoint-type chat --endpoint /v1/chat/completions --streaming --url "$URL" \
     --synthetic-input-tokens-mean "$isl" --synthetic-input-tokens-stddev 0 --output-tokens-mean "$osl" --output-tokens-stddev 0 --concurrency "$c" --benchmark-duration "$win" \
     --benchmark-grace-period inf --use-server-token-count --random-seed $((953600+r)) --extra-inputs '{"temperature":0,"ignore_eos":true}' --request-timeout-seconds 1800 --output-artifact-dir "$out/rep${r}" > "$out/rep${r}.log" 2>&1
    sleep 5
  done
  curl -fsS "$URL/metrics" > "$out/metrics-after.txt" 2>/dev/null || true
  python3 /home/demouser/glm53-raster/gen1-fine-concurrency/metrics-delta.py "$out/metrics-before.txt" "$out/metrics-after.txt" > "$out/spec-delta.txt" 2>&1 || true
  docker logs --tail 4000 "$NAME" 2>&1 | grep -oE 'Mean acceptance length: .*' | tail -4 > "$out/spec-log.txt" || true
  if [[ ! -f "$out/rep${reps}/profile_export_aiperf.json" ]]; then
    printf '%s\t%s\n' "$(date -u +%FT%TZ)" "$out" >> "$STATE/bench-failures.tsv"
    echo "$(date -u +%FT%TZ) bench_incomplete $label $kind-C$c" | tee -a "$STATE/progress.log"
    return 0
  fi
  echo "$(date -u +%FT%TZ) bench_done $label $kind-C$c" | tee -a "$STATE/progress.log"
}
quality() { # label
  local label=$1
  if python3 "/home/demouser/glm53-raster/gen4-expert-mode/correctness.py" "$URL" "$STATE/$label/correctness.json" > "$STATE/$label/quality-line.txt" 2>&1; then
    echo "$(date -u +%FT%TZ) quality_pass $label $(cat "$STATE/$label/quality-line.txt")" | tee -a "$STATE/progress.log"; return 0
  fi
  echo "$(date -u +%FT%TZ) quality_FAIL $label $(cat "$STATE/$label/quality-line.txt")" | tee -a "$STATE/progress.log"; return 1
}
launch() { # label env...
  local label=$1; shift
  local cs="$STATE/$label"; mkdir -p "$cs"
  echo "$(date -u +%FT%TZ) launch $label" | tee -a "$STATE/progress.log"
  /home/demouser/glm53-raster/free-8080.sh | tee -a "$STATE/progress.log"
  # free-8080 stops but does not remove; a stopped container still owns the name.
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  if docker inspect "$NAME" >/dev/null 2>&1; then
    echo "$(date -u +%FT%TZ) name_still_taken $label" | tee -a "$STATE/progress.log"; return 1
  fi
  if ! docker run -d --name "$NAME" --restart no --memory 96g --memory-swap 96g --gpus all \
    --ipc host --security-opt label=disable -p 8080:8080 \
    -e MAX_BATCHED_TOKENS=8192 "$@" \
    -v "$MODEL:/model:ro" -v radixark-glm53-canary-cache:/cache "$IMAGE" > "$cs/container-id.txt"; then
    echo "$(date -u +%FT%TZ) docker_run_failed $label" | tee -a "$STATE/progress.log"; return 1
  fi
  # Stream logs to disk immediately: if the container dies, the reason survives.
  docker logs -f "$NAME" > "$cs/server.log" 2>&1 &
  local logpid=$!; echo "$logpid" > "$cs/log-pid.txt"
  if ! wait_ready "$cs"; then
    kill "$logpid" 2>/dev/null || true
    # wait_ready's own capture may find the container gone; prefer the stream.
    [[ -s "$cs/server.log" ]] || cp "$cs/startup.log" "$cs/server.log" 2>/dev/null || true
    tail -n 40 "$cs/server.log" > "$cs/failure-tail.txt" 2>/dev/null || true
    grep -iE 'out of memory|CUDA error|exceeds|Traceback|RuntimeError|not supported|assert' "$cs/failure-tail.txt" | tail -8 > "$cs/failure-signals.txt" 2>/dev/null || true
    echo "$(date -u +%FT%TZ) startup_failed $label" | tee -a "$STATE/progress.log"; return 1
  fi
  kill "$logpid" 2>/dev/null || true
  if ! curl -fsS "$URL/v1/chat/completions" -H 'Content-Type: application/json' \
       -d '{"model":"glm-5.3-nvfp4-radixark","messages":[{"role":"user","content":"What is 17*23? Answer with only the number."}],"temperature":0,"max_tokens":64}' \
       > "$cs/smoke.json" || ! grep -q '391' "$cs/smoke.json"; then
    echo "$(date -u +%FT%TZ) smoke_failed $label" | tee -a "$STATE/progress.log"; return 1
  fi
  grep -oE 'B12X_MOE_[A-Z0-9_]*' "$cs/server.log" 2>/dev/null | sort -u | head -5 > "$cs/mode-evidence.txt" || true
  echo "$(date -u +%FT%TZ) ready $label $(tr '\n' ' ' < "$cs/kv-cache.txt" 2>/dev/null)" | tee -a "$STATE/progress.log"
  return 0
}

# Budget estimate published before launch (R-PIPE-3): 3 startups ~11 min + 3 gates + 6 bench points = ~1 h 05 m wall clock; expert width measured at the seq128 base so it is comparable with the current peak

# gen15: establish the gate on the control FIRST (it refused three healthy candidates
# on a defective `spell` expectation), then A8 and native W4A4 on the seq128 base.
if [[ ! -f "$STATE/control-a16/decode-C128/profile_export_aiperf.json" ]]; then
  if launch control-a16 -e MAX_NUM_SEQS=128 -e GRAPH=512 -e MTP=3 -e GPU_MEMORY_UTILIZATION=0.95 -e B12X_MOE_FORCE_A16=1; then
    if quality control-a16; then bench control-a16 decode 128 8 768 60 2
    else echo "$(date -u +%FT%TZ) gate_invalid control_a16_failed - gate cannot discriminate; measuring anyway and labelling the gate suspect" | tee -a "$STATE/progress.log"; bench control-a16 decode 128 8 768 60 2; fi
  fi
fi
if [[ ! -f "$STATE/moe-a8/decode-C128/profile_export_aiperf.json" ]]; then
  if launch moe-a8 -e MAX_NUM_SEQS=128 -e GRAPH=512 -e MTP=3 -e GPU_MEMORY_UTILIZATION=0.95 -e B12X_MOE_FORCE_A8=1; then
    if quality moe-a8; then bench moe-a8 decode 128 8 768 60 2
    else echo "$(date -u +%FT%TZ) skipping_moe-a8_perf_gate_failed" | tee -a "$STATE/progress.log"; fi
  fi
fi
if [[ ! -f "$STATE/moe-w4a4-native/decode-C128/profile_export_aiperf.json" ]]; then
  if launch moe-w4a4-native -e MAX_NUM_SEQS=128 -e GRAPH=512 -e MTP=3 -e GPU_MEMORY_UTILIZATION=0.95 -e B12X_MOE_FORCE_A16= -e B12X_MOE_FORCE_A8=; then
    if quality moe-w4a4-native; then bench moe-w4a4-native decode 128 8 768 60 2
    else echo "$(date -u +%FT%TZ) skipping_moe-w4a4-native_perf_gate_failed" | tee -a "$STATE/progress.log"; fi
  fi
fi

docker rm -f "$NAME" >/dev/null 2>&1 || true
