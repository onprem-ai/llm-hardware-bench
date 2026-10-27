#!/usr/bin/env bash
# COLD-PREFILL campaign: every measured request must carry a prompt the server has not seen.
#
# Why: AIPerf's own run log states `unique conversations: 100, sampling strategy: sequential`
# for every formal-campaign prefill run, while the 60 s windows issued 312-470 requests at
# 2,048 tokens each - the pool was replayed 3-5 times per window, and the server reported
# 65-89% of prompt tokens as prefix-cache reads. R-05-2 required a freshly generated prompt
# per measured request throughout; the harness simply never asked for one. The controlling
# option is --num-dataset-entries and it was never passed, so the default of 100 applied.
#
# The pool here is larger than any window can consume, and correctness is not assumed:
# every run is checked against the server's own prefix_cache_hits/queries counters, and the
# campaign halts if the measured served fraction exceeds COLD_MAX_SERVED_PCT. Warm-up is
# switchable because a warm-up drawing from the same pool is a cache priming step; which
# setting is right is decided by that measurement, not argued in advance.
# One bench definition, seven arguments, explicit window and repetitions.
# One bench definition, seven arguments, explicit window and repetitions.
set -uo pipefail
STATE=${STATE:?set STATE to the campaign evidence directory}
CONTAINER_NAME=${CONTAINER_NAME:?set CONTAINER_NAME}
CORPUS=${CORPUS:-}                      # JSONL custom dataset; empty selects synthetic
GATE=${GATE:-/home/demouser/benchmarks/cold_gate.py}
# raster root: the base harness never defined R, and set -u killed the first attempt
R=/home/demouser/glm53-raster
# STATE is the evidence root. An empty value silently retargets every artifact to /,
# which happened here on 2026-09-07 after a sed with & expansion mangled this line.
[[ -n "${STATE:-}" && -d "$STATE" ]] || { echo "STATE invalid: [$STATE]" >&2; exit 1; }   # STATE must not be empty
MODEL=/home/demouser/models/RadixArk--GLM-5.3-NVFP4--model
IMAGE=local/radixark-glm53-r18-seq64-graph256:canary
A=/home/demouser/benchmarks/aiperf/.venv/bin/aiperf
URL=http://127.0.0.1:8080
NAME=$CONTAINER_NAME
exec > >(tee -a "$STATE/controller.log") 2>&1
trap 'rc=$?; kill "$(cat "$STATE/telemetry.pid" 2>/dev/null)" 2>/dev/null || true; if [ "$rc" -ne 0 ] && [ ! -f "$STATE/COMPLETE" ]; then date -u +%FT%TZ > "$STATE/ABORTED"; fi; echo "$(date -u +%FT%TZ) controller_exit=$rc"; exit $rc' EXIT
echo "$(date -u +%FT%TZ) start" > "$STATE/STARTED"
bash /home/demouser/glm53-raster/telemetry.sh "$STATE/telemetry.csv" "$NAME" & echo $! > "$STATE/telemetry.pid"
wait_ready() { # cs
  local cs=$1 ready=0 n st
  for n in $(seq 1 "${READY_ITERS:-200}"); do
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

# ------------------------------------------------------------------
# Formal campaign driver, 2026-09-07. Approved contract:
#   results/xe7740-8x-rtx6000/glm5.3/5-campaign/formal-20260907-freeze-contract.md
# Grid is shared by every primary profile. Token shapes come from the recorded
# spec file, not from anyone's memory (R-02-10).
# ------------------------------------------------------------------
FORMAL=$STATE
SPEC=${SPEC:-/tmp/radixark-glm53-formal.yaml}
GRID=${GRID_OVERRIDE:-1 8 32 64 96 128 160 192}
DATASET_ENTRIES=${DATASET_ENTRIES:-4000}
if [[ -n "$CORPUS" ]]; then
  [[ -s "$CORPUS" ]] || { echo "corpus given but unreadable: $CORPUS" >&2; exit 2; }
  INPUT_ARGS=(--dataset-type custom --input-file "$CORPUS")
else
  INPUT_ARGS=(--dataset-type synthetic --num-dataset-entries "$DATASET_ENTRIES")
fi
COLD_MAX_SERVED_PCT=${COLD_MAX_SERVED_PCT:-2.0}
WARMUP=${WARMUP:-1}
PEAK_POINTS=()                # uniform repetitions for a cold-cache sweep
WINDOW=60
CONTROL_WINDOW=90             # 3 reps at C128 to re-measure the window-class offset

mkdir -p "$FORMAL/runs"
python3 - "$SPEC" > "$FORMAL/profiles.tsv" <<'PY'
import re,sys
text=open(sys.argv[1]).read()
block=text.split('profiles:',1)[1]
for m in re.finditer(r'-\s*name:\s*(\w+)(.*?)(?=\n\s*-\s*name:|\Z)', block, re.S):
    name, body = m.group(1), m.group(2)
    isl=re.search(r'input_tokens_mean:\s*(\d+)', body)
    osl=re.search(r'output_tokens_mean:\s*(\d+)', body)
    if name in ('decode','prefill','balanced') and isl and osl:
        print(f"{name}\t{isl.group(1)}\t{osl.group(1)}")
PY
echo "$(date -u +%FT%TZ) profiles: $(tr '\n' ' ' < "$FORMAL/profiles.tsv" | tr '\t' '=')" | tee -a "$FORMAL/progress.log"

# one run: writes artifacts plus a manifest naming the command, seed, units and identity
run_one() { # profile conc rep window seed_base
  local prof=$1 c=$2 rep=$3 win=$4 seed_base=${5:-700000}
  [[ "$c" =~ ^[0-9]+$ ]]            || { echo "$(date -u +%FT%TZ) guard_bad_concurrency '$c'" | tee -a "$FORMAL/progress.log"; return 3; }
  [[ "$win" =~ ^[0-9]+$ ]]          || { echo "$(date -u +%FT%TZ) guard_bad_window '$win'"   | tee -a "$FORMAL/progress.log"; return 3; }
  [[ "$rep" =~ ^[0-9]+$ ]]          || { echo "$(date -u +%FT%TZ) guard_bad_repetition '$rep'" | tee -a "$FORMAL/progress.log"; return 3; }
  (( win >= 10 && win <= 300 ))     || { echo "$(date -u +%FT%TZ) guard_window_out_of_range $win" | tee -a "$FORMAL/progress.log"; return 3; }
  (( seed_base % 1000 == 0 ))       || { echo "$(date -u +%FT%TZ) guard_seed_base_collides $seed_base" | tee -a "$FORMAL/progress.log"; return 3; }
  local out
  if [[ "$seed_base" != "700000" ]]; then
    out="$FORMAL/controls/$prof/c$(printf '%03d' "$c")/r${rep}-w${win}s"
  else
    out="$FORMAL/runs/$prof/c$(printf '%03d' "$c")/r$rep"
  fi
  mkdir -p "$out"
  [[ -f "$out/profile_export_aiperf.json" ]] && { echo "$(date -u +%FT%TZ) resume_skip $prof C$c r$rep" | tee -a "$FORMAL/progress.log"; return 0; }
  local isl osl; IFS=$'\t' read -r _ isl osl <<<"$(grep -P "^$prof\t" "$FORMAL/profiles.tsv")"
  local seed=$(( seed_base + c*100 + rep ))
  # warm-up: 2x concurrency requests, discarded
  "$A" profile --model glm-5.3-nvfp4-radixark --tokenizer "$MODEL" --endpoint-type chat \
    --endpoint /v1/chat/completions --streaming --url "$URL" \
    --synthetic-input-tokens-mean "$isl" --synthetic-input-tokens-stddev 0 \
    --output-tokens-mean "$osl" --output-tokens-stddev 0 --concurrency "$c" \
    --request-count "$((c*2))" --num-dataset-entries 200 --use-server-token-count --random-seed $((seed+1)) \
    --extra-inputs '{"temperature":0,"ignore_eos":true}' --request-timeout-seconds 1800 \
    --output-artifact-dir "$out/warmup" > "$out/warmup.log" 2>&1
  [[ "$WARMUP" == "1" ]] || echo "$(date -u +%FT%TZ) warmup_skipped pool_isolation $prof C$c r$rep" | tee -a "$FORMAL/progress.log"
  sleep 10
  "$A" profile --model glm-5.3-nvfp4-radixark --tokenizer "$MODEL" --endpoint-type chat \
    --endpoint /v1/chat/completions --streaming --url "$URL" \
    --synthetic-input-tokens-mean "$isl" --synthetic-input-tokens-stddev 0 \
    --output-tokens-mean "$osl" --output-tokens-stddev 0 --concurrency "$c" \
    --benchmark-duration "$win" --benchmark-grace-period inf \
    "${INPUT_ARGS[@]}" \
    --use-server-token-count --random-seed "$seed" \
    --extra-inputs '{"temperature":0,"ignore_eos":true}' --request-timeout-seconds 1800 \
    --output-artifact-dir "$out" > "$out/run.log" 2>&1
  local cid; cid=$(docker inspect -f '{{.Id}}' "$NAME" 2>/dev/null || echo unknown)
  local peak=NA
  [[ -f "/sys/fs/cgroup/system.slice/docker-${cid}.scope/memory.peak" ]] && \
    peak=$(cat "/sys/fs/cgroup/system.slice/docker-${cid}.scope/memory.peak")
  printf '{"profile":"%s","concurrency":%s,"repetition":%s,"window_s":%s,"isl":%s,"osl":%s,"seed":%s,"token_source":"server","time_units":"ms","container_id":"%s","container_mem_peak_bytes":%s,"utc":"%s","measurement":"profile_export_aiperf.json"}\n' \
    "$prof" "$c" "$rep" "$win" "$isl" "$osl" "$seed" "$cid" "$peak" "$(date -u +%FT%TZ)" > "$out/manifest.json"
  if [[ -f "$out/profile_export_aiperf.json" ]]; then
    served=$(python3 "$GATE" "$out" --max-served-pct "$COLD_MAX_SERVED_PCT" | sed -n 's/.*served_prompt_pct=\([0-9.]*\).*/\1/p')
    echo "$(date -u +%FT%TZ) cold_check $prof C$c r$rep served_prompt_pct=$served entries=$DATASET_ENTRIES warmup=$WARMUP" | tee -a "$FORMAL/progress.log"
    if [[ -z "$served" ]]; then
      echo "$(date -u +%FT%TZ) COLD_GATE_UNKNOWN $prof C$c r$rep counters absent" | tee -a "$FORMAL/progress.log"
      printf '%s\n' "This run produced no prefix-cache counters, so it cannot be shown to be cold. An unverified run may not be reported as prefill capacity (R-05-2, R-PIPE-8)." > "$FORMAL/INVALID.cold-cache"
      return 9
    fi
    if awk -v a="$served" -v b="$COLD_MAX_SERVED_PCT" "BEGIN{exit !(a>b)}"; then
      echo "$(date -u +%FT%TZ) COLD_GATE_FAIL $prof C$c r$rep served=$served limit=$COLD_MAX_SERVED_PCT" | tee -a "$FORMAL/progress.log"
      printf '%s\n' "Measured ${served}% of prompt tokens as prefix-cache reads; the cold-prefill limit is ${COLD_MAX_SERVED_PCT}%. The prompt pool was not unique per request, so this is warm-cache throughput and must not be reported as prefill capacity (R-05-2)." > "$FORMAL/INVALID.cold-cache"
      return 9
    fi
    echo "$(date -u +%FT%TZ) run_ok $prof C$c r$rep mem_peak=${peak} served_prompt_pct=$served" | tee -a "$FORMAL/progress.log"
  else
    echo "$(date -u +%FT%TZ) run_FAIL $prof C$c r$rep" | tee -a "$FORMAL/progress.log"
    printf '%s\t%s\tC%s\tr%s\n' "$(date -u +%FT%TZ)" "$prof" "$c" "$rep" >> "$FORMAL/run-failures.tsv"
  fi
  sleep 15
}

if ! launch formal -e MAX_NUM_SEQS=128 -e GRAPH=512 -e MTP=3 -e GPU_MEMORY_UTILIZATION=0.95; then
  echo "$(date -u +%FT%TZ) formal_launch_failed" | tee -a "$FORMAL/progress.log"
else
  quality formal || echo "$(date -u +%FT%TZ) quality_gate_FAILED halting formal run" | tee -a "$FORMAL/progress.log"
  if grep -q quality_PASS "$FORMAL/progress.log" 2>/dev/null || [[ -f "$FORMAL/formal/correctness.json" ]]; then
    # Probe the installed binary before measuring anything: a flag name that this
    # build does not accept would otherwise fall back to the default 100-prompt pool
    # and produce warm numbers carrying cold labels.
    if ! timeout 600 "$A" profile --model "$SERVED_ID" --tokenizer "$MODEL" --endpoint-type chat \
         --endpoint /v1/chat/completions --url "$URL" "${INPUT_ARGS[@]}" \
         --synthetic-input-tokens-mean 512 --synthetic-input-tokens-stddev 0 \
         --output-tokens-mean 4 --output-tokens-stddev 0 --request-count 1 \
         --use-server-token-count --request-timeout-seconds 300 \
         --output-artifact-dir "$FORMAL/probe" > "$FORMAL/probe.log" 2>&1; then
      echo "$(date -u +%FT%TZ) probe_failed see $FORMAL/probe.log" | tee -a "$FORMAL/progress.log"
      printf '%s\n' "The installed AIPerf rejected the cold-input argument set (see probe.log); refusing to measure rather than emit warm numbers labelled cold." > "$FORMAL/INVALID.probe"
      docker stop "$NAME" >/dev/null 2>&1 || true
      exit 2
    fi
    echo "$(date -u +%FT%TZ) probe_ok input_args=${INPUT_ARGS[*]}" | tee -a "$FORMAL/progress.log"

    while IFS=$'\t' read -r prof isl osl; do
      [[ "$prof" == "prefill" ]] || continue      # prefill is the profile the cache confounds
      for c in "${GRID[@]}"; do
        reps=3
        for r in $(seq 1 "$reps"); do
          if ! run_one "$prof" "$c" "$r" "$WINDOW" "$(( 600000 + c*1000 ))"; then
            echo "$(date -u +%FT%TZ) halting on cold-gate failure at $prof C$c r$r" | tee -a "$FORMAL/progress.log"
            docker stop "$NAME" >/dev/null 2>&1 || true; exit 9
          fi
        done
      done
      # window-class controls are out of scope for a cold-prefill sweep
    done < "$FORMAL/profiles.tsv"
    # Window-class control, same launch, both classes back to back. run_one takes
    # (profile concurrency repetition window_seconds seed_base) -- argument order here
    # has already caused one defect, so it is spelled positionally and guarded below.
    echo "$(date -u +%FT%TZ) controls_skipped out_of_scope_for_cold_prefill" | tee -a "$FORMAL/progress.log"

  fi
  docker stop "$NAME" >/dev/null 2>&1 || true
fi

# B1-post idle baseline, same sampler as B0
B1=$FORMAL/B1-post-idle.csv
printf 'utc,gpu_power_w,gpu_util_pct,mem_used_gib,mem_available_gib\n' > "$B1"
sleep 60
for i in $(seq 1 12); do
  pw=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits | awk '{s+=$1} END{print s/NR}')
  echo "$(date -u +%FT%TZ),$pw,0,$(free -g | awk 'NR==2{print $3}'),$(free -g | awk 'NR==2{print $7}')" >> "$B1"
  sleep 25
done

total=$(find "$FORMAL/runs" -name profile_export_aiperf.json -not -path '*/warmup/*' 2>/dev/null | wc -l | tr -d ' ')
parsed=$(find "$FORMAL/runs" -name profile_export_aiperf.json -not -path '*/warmup/*' -exec grep -l 'output_token_throughput\|"results"' {} \; 2>/dev/null | wc -l | tr -d ' ')
echo "$(date -u +%FT%TZ) cold_complete runs=$total parseable=$parsed" | tee -a "$FORMAL/progress.log"
if [[ "$total" -eq 0 ]]; then
  echo "Null result: no formal run artifacts. Check formal/startup.log before reading this as capacity." > "$FORMAL/INVALID.reason"
elif [[ "$parsed" -ne "$total" ]]; then
  echo "Validator defect: $total artifacts, $parsed parseable. Silence is not absence (R-05-12)." > "$FORMAL/INVALID.validator"
else
  date -u +%FT%TZ > "$FORMAL/COMPLETE"
fi

echo "STATE=[$STATE] R=[$R]" >> "$STATE/progress.log"
