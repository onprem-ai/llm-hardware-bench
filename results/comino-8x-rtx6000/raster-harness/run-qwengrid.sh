#!/usr/bin/env bash
# comino-8x-rtx6000 / Qwen3.8-Flash-Next NVFP4 - Dell xe7740 recipe, 4x TP2 replicas behind
# haproxy leastconn (8000). Frozen 2026-09-24 per user: Dell params verbatim.
# Phase 1 decode-optimized (radix ON, NEXTN 3/1/4, mamba 240, graph 48, ISL 8 / OSL 512).
# Phase 2 prefill-optimized-uncached (radix OFF, no spec, mamba 120, graph 24, ISL 4096 / OSL 8).
# Grid [1 32 64 96 128 160 192 224] x {decode, prefill} x 3 reps; 60 s; grace inf;
# seeds 600000+C*1000+rep; warmup seeds 953601/953602 (disjoint pools).
# Prefill gate: client-side cache reads must be 0 (radix disabled by launch flags as well).
set -uo pipefail
STATE=${STATE:?set STATE to the campaign evidence directory}
A=~/bench/llm-bench/aiperf-venv/bin/aiperf
MODEL=~/bench/models/RadixArk--Qwen3.8-Flash-Next-NVFP4--model
URL=http://127.0.0.1:8000
H=~/bench/llm-bench/repo/harness/2-preflight-conformance/code
ENG=~/bench/llm-bench/repo/raster-harness-qwen
IMG=local/qwen38-flash-next-sm120:comino-patched
LB=qwen38-flash-lb
WIN=60; REPS=3
AXIS="1 32 64 96 128 160 192 224"
PAIRS=("0,1" "2,3" "4,5" "6,7"); PORTS=(8101 8102 8103 8104)
NAMES=(qwen38-flash-a qwen38-flash-b qwen38-flash-c qwen38-flash-d)
mkdir -p "$STATE"; cd "$STATE"
exec >> "$STATE/controller.log" 2>&1
trap 'rc=$?; kill "$(cat "$STATE/telemetry.pid" 2>/dev/null)" 2>/dev/null || true; if [ "$rc" -ne 0 ] && [ ! -f "$STATE/COMPLETE" ]; then date -u +%FT%TZ > "$STATE/ABORTED"; fi; echo "$(date -u +%FT%TZ) controller_exit=$rc"; exit $rc' EXIT
echo "$(date -u +%FT%TZ) start" > "$STATE/STARTED"

mkdir -p telemetry
bash "$H/gpu/sample-nvidia-smi.sh" "$STATE/telemetry/gpu.csv" 1 & G1=$!
bash "$H/host/sample-host.sh" "$STATE/telemetry/host.csv" 1 & G2=$!
( while :; do printf '%s,%s,%s,%s,%s\n' "$(date -u +%FT%T.%N)" \
    "$(docker stats --no-stream --format '{{.MemUsage}},{{.CPUPerc}}' ${NAMES[*]} 2>/dev/null | tr '\n' ';')" \
    "$(docker ps --format '{{.Names}}:{{.Status}}' --filter name=qwen38-flash 2>/dev/null | tr '\n' ';')"; sleep 5; done ) > "$STATE/telemetry/docker.csv" 2>/dev/null & G3=$!
echo "$G1 $G2 $G3" > "$STATE/telemetry.pid"

fail() { echo "$(date -u +%FT%TZ) FATAL: $*" | tee -a "$STATE/progress.log"; echo "$*" > "$STATE/INVALID.reason"; exit 1; }

boot_fleet() { # profile outdir
  local prof=$1 od=$2 i
  docker rm -f glm53-engine glm53-lb >/dev/null 2>&1
  docker rm -f "${NAMES[@]}" "$LB" >/dev/null 2>&1
  sleep 5
  for i in 0 1 2 3; do
    docker run -d --name "${NAMES[$i]}" --network host --ipc host --gpus "\"device=${PAIRS[$i]}\"" \
      -v "$MODEL":/model:ro -v "$ENG":/eng:ro -e PORT="${PORTS[$i]}" \
      --entrypoint bash "$IMG" "/eng/$prof-launch.sh" >/dev/null || fail "docker run ${NAMES[$i]} ($prof)"
  done
  docker run -d --name "$LB" --network host -v "~/bench/llm-bench/qwen-infra/haproxy.cfg":/usr/local/etc/haproxy/haproxy.cfg:ro \
    haproxy:3.2-alpine -f /usr/local/etc/haproxy/haproxy.cfg -V >/dev/null || fail "haproxy run"
  local n
  for n in $(seq 1 240); do
    curl -fsS --max-time 3 "$URL/health" >/dev/null 2>&1 && break
    sleep 5
  done
  curl -fsS --max-time 3 "$URL/health" >/dev/null 2>&1 || fail "fleet not ready within 1200s ($prof)"
  mkdir -p "$od"
  for i in 0 1 2 3; do docker logs "${NAMES[$i]}" > "$od/${NAMES[$i]}.log" 2>&1 || true; done
  grep -hE "max.running.requests|max.mamba.cache.size|cuda.graph.max.bs|disable.radix|speculative" "$od"/*.log 2>/dev/null | sort -u > "$od/params.txt" || true
  echo "fleet_ready $prof $(date -u +%FT%TZ)" | tee -a "$STATE/progress.log"
}

drain() {
  local n v
  for n in $(seq 1 150); do
    v=$(curl -fsS --max-time 5 "$URL/metrics" 2>/dev/null | awk '$0 !~ /^#/ && /num_running_reqs/ {print $NF+0; exit}')
    [ "${v:-1}" = "0" ] && return 0
    sleep 2
  done
  fail "fleet did not drain (running=${v:-NA})"
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
  echo "baseline $tag done" | tee -a "$STATE/progress.log"
}

run_correctness() { # outdir
  mkdir -p "$1"
  python3 "$ENG/correctness.py" "$URL" "$1/correctness.json" qwen38-flash-next-nvfp4 || fail "correctness gate failed ($1)"
  echo "correctness 7/7 $1" | tee -a "$STATE/progress.log"
}

bench_point() { # kind c isl osl  (kind: decode -> gate-off (radix on by design); prefill -> gate client cache==0)
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
    if [ ! -f "$out/warmup/profile_export_aiperf.json" ]; then
      cli="$A profile --model qwen38-flash-next-nvfp4 --url $URL --tokenizer $MODEL --endpoint-type chat --endpoint /v1/chat/completions --streaming --isl $isl --isl-stddev 0 --osl $osl --osl-stddev 0 --concurrency $c --request-count $((c > 32 ? c : 32)) --use-server-token-count --random-seed $wseed --extra-inputs '{\"temperature\": 0, \"ignore_eos\": true}' --request-timeout-seconds 1800 --output-artifact-dir $out/warmup"
      echo "$cli" | tee -a "$STATE/commands.log"
      eval "$cli" > "$out/warmup.log" 2>&1 || fail "warmup failed $kind C$c"
    fi
    sleep 10; drain
    cli="$A profile --model qwen38-flash-next-nvfp4 --url $URL --tokenizer $MODEL --endpoint-type chat --endpoint /v1/chat/completions --streaming --isl $isl --isl-stddev 0 --osl $osl --osl-stddev 0 --concurrency $c --benchmark-duration $WIN --benchmark-grace-period inf --use-server-token-count --random-seed $seed --extra-inputs '{\"temperature\": 0, \"ignore_eos\": true}' --request-timeout-seconds 1800 --output-artifact-dir $rd --num-dataset-entries 4000 --dataset-sampling-strategy sequential --server-metrics"
    echo "$cli" | tee -a "$STATE/commands.log"
    printf '%s\n' "$cli" > "$rd/cli.txt"; printf '%s\n' "$seed" > "$rd/seed"
    eval "$cli" > "$rd/aiperf.log" 2>&1 || fail "aiperf nonzero exit $kind C$c r$r"
    drain
    [ -f "$rd/profile_export_aiperf.json" ] || fail "no aiperf artifact $kind C$c r$r"
    python3 - "$rd" "$kind" <<'PYEOF'
import json, sys
rd, kind = sys.argv[1], sys.argv[2]
d = json.load(open(rd + "/profile_export_aiperf.json"))
cache_rd = d.get("usage_prompt_cache_read_tokens", {}).get("avg", 0) or 0
gate = {"kind": kind, "client_cache_read_tokens": cache_rd}
if kind == "prefill":
    gate["pass"] = (cache_rd == 0)
    gate["reason"] = "prefill profile requires zero client-side cache reads (radix disabled by launch)"
else:
    gate["pass"] = True
    gate["reason"] = "decode profile runs radix-on by design (ISL 8); cache reads recorded, not gated"
json.dump(gate, open(rd + "/gate.json", "w"), indent=2)
sys.exit(0 if gate["pass"] else 1)
PYEOF
    [ $? -eq 0 ] || { cat "$rd/gate.json"; fail "prefill cache gate violated at $kind C$c r$r"; }
    date -u +%FT%TZ > "$rd/FINISHED"
    echo "$(date -u +%FT%TZ) done $kind C$c r$r cache_rd=$(python3 -c "import json;print(json.load(open('$rd/gate.json'))['client_cache_read_tokens'])")" | tee -a "$STATE/progress.log"
  done
  echo "$(date -u +%FT%TZ) point_complete $kind C$c" | tee -a "$STATE/progress.log"
}

# ---- phase 1: decode-optimized fleet ----
boot_fleet decode "$STATE/segments/decode-fleet"
run_correctness "$STATE/segments/decode-fleet"
baseline b1-pre 300
for c in $AXIS; do bench_point decode $c 8 512; done

# ---- phase 2: prefill-optimized-uncached fleet ----
boot_fleet prefill "$STATE/segments/prefill-fleet"
run_correctness "$STATE/segments/prefill-fleet"
for c in $AXIS; do bench_point prefill $c 4096 8; done
baseline b1-post 300

python3 - "$STATE" <<'PYEOF'
import json, os, sys, glob
state = sys.argv[1]
runs = []
for kind in ("decode", "prefill"):
    for d in sorted(glob.glob(os.path.join(state, kind, "c*", "r*"))):
        if os.path.exists(os.path.join(d, "profile_export_aiperf.json")):
            g = json.load(open(os.path.join(d, "gate.json"))) if os.path.exists(os.path.join(d, "gate.json")) else {}
            runs.append({"run": d.replace(state + "/", ""), "cache_rd": g.get("client_cache_read_tokens"), "pass": g.get("pass")})
summary = {"runs": len(runs), "expected": 48, "gate_failures": sum(1 for r in runs if not r["pass"]), "detail": runs}
json.dump(summary, open(os.path.join(state, "result.json"), "w"), indent=2)
print(json.dumps({k: summary[k] for k in ("runs", "expected", "gate_failures")}))
PYEOF
find "$STATE" -type f ! -name SHA256SUMS -exec sha256sum {} + > "$STATE/SHA256SUMS" 2>/dev/null
date -u +%FT%TZ > "$STATE/COMPLETE"
echo "$(date -u +%FT%TZ) CAMPAIGN_COMPLETE" | tee -a "$STATE/progress.log"
