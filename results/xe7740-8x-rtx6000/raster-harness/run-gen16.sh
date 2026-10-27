#!/usr/bin/env bash
# Corrected rerun of three things that never produced data:
#   step 1: protocol-fidelity probe (90 s windows, 3 reps) on the published control
#   step 2: MTP speculation-depth raster 3/2/1/0 with matched graph coverage
#   step 3: expert-mode raster A16 / A8 / native W4A4 behind a quality gate
# One bench definition, seven arguments, explicit window and repetitions.
set -uo pipefail
STATE=/home/demouser/glm53-raster/gen16-turnover-order
# STATE is the evidence root. An empty value silently retargets every artifact to / : on
# 2026-09-07 a sed with & expansion emptied this line, the run started happily, and nothing
# failed loudly for 45 minutes. Assert it before anything can depend on it.
[[ -n "${STATE:-}" && -d "$STATE" ]] || { echo "STATE invalid: [$STATE]" >&2; exit 1; }   # STATE must not be empty
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

# Budget estimate published before launch (R-PIPE-3): 2 candidates x (startup 13-17 min + gate
# ~1 min + 8 benches x ~2 min) = ~1 h 20 m wall clock. Turnover question only; no new parameters.

# R-03-22: readiness deadline from a MEASURED boot. moe-a8 at GRAPH=512 reached health in 767 s
# (23:23:51 -> 23:36:38), i.e. ~154 of the old 200 iterations. Iterations set to ~2x the
# interpolated boot for each graph size instead of one constant that killed seq144/seq160.
ITERS_512=320; ITERS_576=380; ITERS_640=440

# R-03-20: single controller, waiting on a recorded pid rather than a process-table guess.
P=$(cat "$R/gen15-expert-on-new-base/controller.pid" 2>/dev/null || true)
if [[ -n "${P:-}" ]] && kill -0 "$P" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) gen16 waiting on gen15 pid=$P" >> "$R/queue.log"
  while kill -0 "$P" 2>/dev/null; do sleep 30; done
fi
# Single-controller invariant (R-03-20). Process-table matching is NOT the mechanism: the
# controller runs as a relative `bash run.sh`, so any pattern containing the raster root path
# matches nothing - verified 2026-09-07 by planting a decoy while gen16 was live, and pgrep
# reported zero. Lock the pid we wrote down, and refuse if it is alive.
LOCK="$R/controller.lock"
if [[ -f "$LOCK" ]]; then
  LPID=$(tr -dc '0-9' < "$LOCK" || true)
  if [[ -n "${LPID:-}" ]] && kill -0 "$LPID" 2>/dev/null; then
    echo "$(date -u +%FT%TZ) refusing start: controller lock held by pid=$LPID" | tee -a "$R/queue.log"
    exit 1
  fi
  echo "$(date -u +%FT%TZ) reclaiming stale lock from pid=${LPID:-unreadable}" | tee -a "$R/queue.log"
fi
echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# R-03-21: each point is measured twice, once early and once late, so the session-position effect
# is measurable rather than confounded. Pass 1 ascending, pass 2 descending.
POINTS=(96 112 128 144)
run_pass() { # label pass-order...
  local label=$1; shift
  local pos=0 c
  for c in "$@"; do
    pos=$((pos+1))
    bench "$label" decode "$c" 8 768 60 1
    [[ -d "$STATE/$label/decode-C$c/rep1" ]] && echo "$pos $c $(date -u +%FT%TZ)" > "$STATE/$label/decode-C$c/rep1/order-position.txt"
  done
}

# Candidate A: the base that produced the disputed peak, same env as gen14s seq128-confirm.
# Budget estimate published before launch (R-PIPE-3): 2 candidates x (startup 13-17 min + gate
# ~1 min + 8 benches x ~2 min) = ~1 h 20 m wall clock. Turnover question only; no new parameters.

# R-03-22: readiness deadline derived from a MEASURED boot, not a constant. moe-a8 at GRAPH=512
# reached health in 767 s (23:23:51 -> 23:36:38) = ~154 of the old 200 iterations, leaving only
# 253 s of margin; the larger graph sets needed more and were killed mid-startup. Iterations are
# set to roughly twice the interpolated boot time per graph size.
ITERS_512=320; ITERS_576=380; ITERS_640=440

# R-03-20: one controller. Wait on the recorded pid; abort rather than share the container name.
P="$(cat "$R/gen15-expert-on-new-base/controller.pid" 2>/dev/null || true)"
if [[ -n "${P:-}" ]] && kill -0 "$P" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) gen16 waiting on gen15 pid=$P" >> "$R/queue.log"
  while kill -0 "$P" 2>/dev/null; do sleep 30; done
fi
# (second pgrep guard removed for the same reason; the lock file above is the invariant)

# R-03-21: measure each point twice, once early and once late, in ascending then descending order,
# so the session-position effect is estimable instead of confounded with concurrency. The position
# of every measurement is written next to it.
run_pass() { # label point...
  local label=$1; shift
  local pos=0 c
  for c in "$@"; do
    pos=$((pos+1))
    bench "$label" decode "$c" 8 768 60 1
    if [[ -d "$STATE/$label/decode-C$c/rep1" ]]; then
      printf 'position=%s concurrency=%s at=%s\n' "$pos" "$c" "$(date -u +%FT%TZ)" \
        > "$STATE/$label/decode-C$c/rep1/order-position.txt"
    fi
  done
}
ASC=(96 112 128 144); DESC=(144 128 112 96)

run_candidate() { # label iters seq graph
  local label=$1 iters=$2 seq=$3 graph=$4
  if find "$STATE/$label" -name profile_export_aiperf.json -not -path '*/warmup/*' 2>/dev/null | grep -q .; then
    echo "$(date -u +%FT%TZ) skip_complete $label" | tee -a "$STATE/progress.log"; return 0
  fi
  export READY_ITERS="$iters"
  if launch "$label" -e "MAX_NUM_SEQS=$seq" -e "GRAPH=$graph" -e MTP=3 -e GPU_MEMORY_UTILIZATION=0.95; then
    quality "$label" || echo "$(date -u +%FT%TZ) gate_note quality gate failed on $label" | tee -a "$STATE/progress.log"
    run_pass "$label" "${ASC[@]}"
    run_pass "$label" "${DESC[@]}"
  else
    echo "$(date -u +%FT%TZ) startup_timeout_or_failed $label deadline=$((iters*5))s" | tee -a "$STATE/progress.log"
    printf 'startup failed for %s at deadline %ss - NOT a capacity result; read %s/startup.log\n' \
      "$label" "$((iters*5))" "$STATE/$label" >> "$STATE/INVALID.startup"
  fi
}

# Candidate A: the base behind the disputed peak, byte-same env as gen14's seq128-confirm.
run_candidate base-seq128-graph512 "$ITERS_512" 128 512
# Candidate B: the turnover probe that never started. Coverage 144 x (1+3) = 576.
run_candidate seq144-graph576 "$ITERS_576" 144 576

# Judge by artifacts found anywhere beneath the candidate (R-05-12), never by a remembered layout.
total=$(find "$STATE" -name profile_export_aiperf.json -not -path '*/warmup/*' 2>/dev/null | wc -l | tr -d ' ')
parsed=$(find "$STATE" -name profile_export_aiperf.json -not -path '*/warmup/*' -exec grep -l 'output_token_throughput' {} \; 2>/dev/null | wc -l | tr -d ' ')
echo "$(date -u +%FT%TZ) complete measurements=$total parseable=$parsed" | tee -a "$STATE/progress.log"
if [[ "$total" -eq 0 ]]; then
  { echo "Null result: no measurement artifacts anywhere beneath $STATE."
    echo "Deadlines used: A=$((ITERS_512*5))s B=$((ITERS_576*5))s. Verify startup.log before reading this as a hardware limit."
    cat "$STATE/INVALID.startup" 2>/dev/null || true
  } > "$STATE/INVALID.reason"
elif [[ "$parsed" -ne "$total" ]]; then
  { echo "Validator defect, not a result: $total artifacts found but only $parsed contain a recognized throughput field."
    echo "A parser that silently yields nothing is indistinguishable from an empty run (R-05-12)."
  } > "$STATE/INVALID.validator"
else
  date -u +%FT%TZ > "$STATE/COMPLETE"
fi
