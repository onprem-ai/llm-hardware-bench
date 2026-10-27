#!/usr/bin/env bash
# comino-8x-rtx6000 / GLM-5.3 NVFP4 - corrected-cold 7-point grid, frozen 2026-09-24.
# Contract: axis [1 8 16 24 32 48 64] x {decode, prefill} x 3 reps; 60 s windows; grace inf;
# seeds 600000+C*1000+rep; warmup seeds 953601/953602 (disjoint pools, no priming);
# decode spliced: C<=24 on seq32/graph128, C>24 on seq64/graph256; prefill on seq32/graph128;
# measured path AIPerf -> haproxy (8084) -> engine; fail-closed prefix-cache gate (<=1%/rep).
set -uo pipefail
STATE=${STATE:?set STATE to the campaign evidence directory}
A=~/bench/llm-bench/aiperf-venv/bin/aiperf
MODEL=~/bench/models/RadixArk--GLM-5.3-NVFP4--model
URL=http://127.0.0.1:8084
H=~/bench/llm-bench/repo/harness/2-preflight-conformance/code
ENG=~/bench/llm-bench/repo/raster-harness-glm
IMG_LOW=local/radixark-glm53-r18-graph128:canary
IMG_HIGH=local/radixark-glm53-r18-seq64-graph256:canary
NAME=glm53-engine
WIN=60; REPS=3; GATE_PCT=1.0
AXIS="1 8 16 24 32 48 64"
mkdir -p "$STATE"; cd "$STATE"
exec > >(tee -a "$STATE/controller.log") 2>&1
trap 'rc=$?; kill "$(cat "$STATE/telemetry.pid" 2>/dev/null)" 2>/dev/null || true; if [ "$rc" -ne 0 ] && [ ! -f "$STATE/COMPLETE" ]; then date -u +%FT%TZ > "$STATE/ABORTED"; fi; echo "$(date -u +%FT%TZ) controller_exit=$rc"; exit $rc' EXIT
echo "$(date -u +%FT%TZ) start" > "$STATE/STARTED"

mkdir -p telemetry
bash "$H/gpu/sample-nvidia-smi.sh" "$STATE/telemetry/gpu.csv" 1 & G1=$!
bash "$H/host/sample-host.sh" "$STATE/telemetry/host.csv" 1 & G2=$!
( while :; do printf '%s,%s\n' "$(date -u +%FT%T.%N)" "$(docker stats --no-stream --format '{{.MemUsage}},{{.CPUPerc}}' $NAME 2>/dev/null | tr -d ' ')"; sleep 5; done ) > "$STATE/telemetry/docker.csv" 2>/dev/null & G3=$!
echo "$G1 $G2 $G3" > "$STATE/telemetry.pid"

fail() { echo "$(date -u +%FT%TZ) FATAL: $*" | tee -a "$STATE/progress.log"; echo "$*" > "$STATE/INVALID.reason"; exit 1; }

wait_ready() { # outdir
  local od=$1 n
  mkdir -p "$od"
  for n in $(seq 1 180); do
    curl -fsS --max-time 3 "$URL/health" >/dev/null 2>&1 && break
    sleep 5
  done
  curl -fsS --max-time 3 "$URL/health" >/dev/null 2>&1 || fail "engine not ready within 900s ($od)"
  docker logs "$NAME" > "$od/startup.log" 2>&1 || true
  grep -oE "'(max_num_seqs|max_cudagraph_capture_size|num_speculative_tokens|max_num_batched_tokens|tensor_parallel_size|kv_cache_dtype)': '?[^,]*" "$od/startup.log" | sort -u > "$od/params.txt" || true
  echo "ready $od $(date -u +%FT%TZ)" | tee -a "$STATE/progress.log"
}

drain() { # wait until engine reports zero running requests
  local n v
  for n in $(seq 1 90); do
    v=$(curl -fsS --max-time 5 "$URL/metrics" 2>/dev/null | awk '/^vllm:num_requests_running\{/ {print $NF+0}' | head -1)
    [ "${v:-1}" = "0" ] && return 0
    sleep 2
  done
  fail "engine did not drain (running=${v:-NA})"
}

metrics_snap() { # file
  curl -fsS --max-time 10 "$URL/metrics" > "$1" 2>/dev/null || fail "metrics snapshot failed: $1"
}

prefix_counters() { # file -> "hits queries"
  awk '/^vllm:prefix_cache_hits(_total)?\{/ {h=$NF} /^vllm:prefix_cache_queries(_total)?\{/ {q=$NF} END {printf "%.0f %.0f", h+0, q+0}' "$1"
}

gate_check() { # before after label -> gate.json ; fail-closed
  local b="$1" a="$2" lb="$3" bh bq ah q d
  read bh bq < <(prefix_counters "$b"); read ah q < <(prefix_counters "$a")
  d=$((ah - bh + q - bq))
  if [ "$d" -le 0 ]; then
    printf '{"label":"%s","hits_delta":%d,"queries_delta":%d,"served_pct":null,"pass":false,"reason":"no prefix queries recorded"}\n' "$lb" $((ah-bh)) $((q-bq)) > "$lb/gate.json"
    fail "cache gate $lb: no prefix queries recorded (fail-closed)"
  fi
  python3 - "$lb" $((ah-bh)) $((q-bq)) "$GATE_PCT" <<'PYEOF'
import json, sys
lb, h, q, lim = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
pct = 100.0 * h / (h + q)
ok = pct <= lim
json.dump({"label": lb, "hits_delta": h, "queries_delta": q, "served_pct": round(pct, 4), "limit_pct": lim, "pass": ok}, open(lb + "/gate.json", "w"), indent=2)
sys.exit(0 if ok else 1)
PYEOF
  [ $? -eq 0 ] || { cat "$lb/gate.json"; fail "cache gate violated at $lb (limit ${GATE_PCT}%)"; }
}

run_correctness() { # outdir
  mkdir -p "$1"
  python3 "$ENG/correctness.py" "$URL" "$1/correctness.json" || fail "correctness gate failed ($1)"
  echo "correctness 7/7 $1" | tee -a "$STATE/progress.log"
}

baseline() { # tag seconds
  local tag=$1 secs=$2
  local od="$STATE/baselines/$tag"
  [ -f "$od/COMPLETE" ] && { echo "baseline $tag resume_skip" | tee -a "$STATE/progress.log"; return 0; }
  mkdir -p "$od"
  bash "$H/gpu/sample-nvidia-smi.sh" "$od/gpu.csv" 1 & local p1=$!
  bash "$H/host/sample-host.sh" "$od/host.csv" 1 & local p2=$!
  sleep "$secs"; kill $p1 $p2 2>/dev/null
  date -u +%FT%TZ > "$od/COMPLETE"
  echo "baseline $tag done rows_gpu=$(wc -l < "$od/gpu.csv")" | tee -a "$STATE/progress.log"
}

boot() { # image outdir
  docker rm -f "$NAME" >/dev/null 2>&1
  sleep 5
  docker run -d --name "$NAME" --ipc host --gpus all -v "$MODEL":/model:ro -p 8080:8080 "$1" >/dev/null || fail "docker run failed for $1"
  echo "boot $1 $(date -u +%FT%TZ)" | tee -a "$STATE/progress.log"
  wait_ready "$2"
}

bench_point() { # kind c isl osl
  local kind=$1 c=$2 isl=$3 osl=$4
  local out="$STATE/$kind/c$(printf '%03d' "$c")" wseed
  [ "$kind" = decode ] && wseed=953601 || wseed=953602
  mkdir -p "$out"
  local r seed cli
  for r in $(seq 1 "$REPS"); do
    local rd="$out/r$r"
    if [ -f "$rd/profile_export_aiperf.json" ]; then echo "$(date -u +%FT%TZ) resume_skip $kind C$c r$r" | tee -a "$STATE/progress.log"; continue; fi
    seed=$((600000 + c * 1000 + r))
    mkdir -p "$rd"
    date -u +%FT%TZ > "$rd/STARTED"
    cli="$A profile --model glm-5.3-nvfp4-radixark --url $URL --tokenizer $MODEL --endpoint-type chat --endpoint /v1/chat/completions --streaming --isl $isl --isl-stddev 0 --osl $osl --osl-stddev 0 --concurrency $c --request-count $((c > 32 ? c : 32)) --use-server-token-count --random-seed $wseed --extra-inputs '{\"temperature\": 0, \"ignore_eos\": true}' --request-timeout-seconds 1800 --output-artifact-dir $out/warmup"
    [ -f "$out/warmup/profile_export_aiperf.json" ] || { echo "$cli" | tee -a "$STATE/commands.log"; eval "$cli" > "$out/warmup.log" 2>&1 || fail "warmup failed $kind C$c"; }
    sleep 10; drain
    metrics_snap "$rd/metrics-before.txt"
    cli="$A profile --model glm-5.3-nvfp4-radixark --url $URL --tokenizer $MODEL --endpoint-type chat --endpoint /v1/chat/completions --streaming --isl $isl --isl-stddev 0 --osl $osl --osl-stddev 0 --concurrency $c --benchmark-duration $WIN --benchmark-grace-period inf --use-server-token-count --random-seed $seed --extra-inputs '{\"temperature\": 0, \"ignore_eos\": true}' --request-timeout-seconds 1800 --output-artifact-dir $rd --num-dataset-entries 4000 --dataset-sampling-strategy sequential --server-metrics"
    echo "$cli" | tee -a "$STATE/commands.log"
    printf '%s\n' "$cli" > "$rd/cli.txt"; printf '%s\n' "$seed" > "$rd/seed"
    eval "$cli" > "$rd/aiperf.log" 2>&1 || fail "aiperf nonzero exit $kind C$c r$r"
    drain
    metrics_snap "$rd/metrics-after.txt"
    gate_check "$rd/metrics-before.txt" "$rd/metrics-after.txt" "$rd"
    [ -f "$rd/profile_export_aiperf.json" ] || fail "no aiperf artifact $kind C$c r$r"
    date -u +%FT%TZ > "$rd/FINISHED"
    echo "$(date -u +%FT%TZ) done $kind C$c r$r served_pct=$(python3 -c "import json;print(json.load(open('$rd/gate.json'))['served_pct'])")" | tee -a "$STATE/progress.log"
  done
  echo "$(date -u +%FT%TZ) point_complete $kind C$c" | tee -a "$STATE/progress.log"
}

# ---- segment 1: graph128 canary already serving ----
wait_ready "$STATE/segments/graph128"
run_correctness "$STATE/segments/graph128"
baseline b1-pre 300
for c in $AXIS; do bench_point prefill $c 2048 8; done
for c in 1 8 16 24; do bench_point decode $c 8 768; done

# ---- segment 2: reboot to seq64/graph256 for decode above the splice ----
boot "$IMG_HIGH" "$STATE/segments/graph256"
run_correctness "$STATE/segments/graph256"
for c in 32 48 64; do bench_point decode $c 8 768; done
baseline b1-post 300

# ---- finalize ----
python3 - "$STATE" <<'PYEOF'
import json, os, sys, glob
state = sys.argv[1]
runs, gates = [], []
for kind in ("decode", "prefill"):
    for d in sorted(glob.glob(os.path.join(state, kind, "c*", "r*"))):
        r = os.path.basename(d)
        if os.path.exists(os.path.join(d, "profile_export_aiperf.json")):
            g = json.load(open(os.path.join(d, "gate.json"))) if os.path.exists(os.path.join(d, "gate.json")) else {}
            runs.append({"run": f"{kind}/{os.path.basename(os.path.dirname(d))}/{r}", "gate": g.get("served_pct")})
            gates.append(g.get("served_pct") is not None and g.get("pass", False))
summary = {"runs": len(runs), "expected": 42, "gates_pass": sum(1 for g in gates if g), "gate_violations": sum(1 for g in gates if not g), "detail": runs}
json.dump(summary, open(os.path.join(state, "result.json"), "w"), indent=2)
print(json.dumps({k: summary[k] for k in ("runs", "expected", "gates_pass", "gate_violations")}))
PYEOF
find "$STATE" -type f ! -name SHA256SUMS -exec sha256sum {} + > "$STATE/SHA256SUMS" 2>/dev/null
date -u +%FT%TZ > "$STATE/COMPLETE"
echo "$(date -u +%FT%TZ) CAMPAIGN_COMPLETE" | tee -a "$STATE/progress.log"
