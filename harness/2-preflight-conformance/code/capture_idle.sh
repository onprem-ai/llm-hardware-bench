#!/usr/bin/env bash
# Capture an unloaded- or loaded-model no-request baseline.
# Caller must verify model state, load-balancer state, and zero request traffic.
set -euo pipefail
OUT=${1:?usage: capture_idle.sh OUTPUT_DIR [DURATION_SECONDS] [unloaded|loaded]}
DURATION=${2:-300}
STATE=${3:-loaded}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[[ $DURATION =~ ^[0-9]+$ && $DURATION -ge 1 ]] || { echo 'duration must be a positive integer' >&2; exit 2; }
[[ $STATE == unloaded || $STATE == loaded ]] || { echo 'state must be unloaded or loaded' >&2; exit 2; }
mkdir -p "$OUT"
"$ROOT/harness/2-preflight-conformance/code/pcie/capture-link-state.sh" "$OUT/link-start.json"
printf '%s\n' "$(date -u --iso-8601=ns)" > "$OUT/start-time.txt"
"$ROOT/harness/2-preflight-conformance/code/gpu/sample-nvidia-smi.sh" "$OUT/gpu.csv" 1 >"$OUT/gpu-collector.log" 2>&1 & gp=$!
"$ROOT/harness/2-preflight-conformance/code/host/sample-host.sh" "$OUT/host.csv" 1 >"$OUT/host-collector.log" 2>&1 & hp=$!
"$ROOT/harness/2-preflight-conformance/code/host/sample-process-memory.py" "$OUT/process-memory.csv" 1 >"$OUT/process-memory-collector.log" 2>&1 & mp=$!
cleanup(){ kill "$gp" "$hp" "$mp" 2>/dev/null || true; wait "$gp" "$hp" "$mp" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
sleep "$DURATION"
cleanup; trap - EXIT INT TERM
printf '%s\n' "$(date -u --iso-8601=ns)" > "$OUT/end-time.txt"
"$ROOT/harness/2-preflight-conformance/code/pcie/capture-link-state.sh" "$OUT/link-end.json"
python3 - "$OUT/manifest.json.tmp" "$DURATION" "$STATE" <<'PY'
import datetime,json,pathlib,socket,sys
p=pathlib.Path(sys.argv[1]); state=sys.argv[3]
p.write_text(json.dumps({
 "schema_version":1,
 "kind":"unloaded-idle-baseline" if state=="unloaded" else "loaded-model-idle-baseline",
 "baseline_id":"B0" if state=="unloaded" else "B1",
 "state":state,
 "host":socket.gethostname(),
 "finalized_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "requested_duration_seconds":int(sys.argv[2]),
 "request_metrics_applicability":"not_applicable",
 "operator_assertions":{
   "model_loaded":None,
   "no_request_traffic":None,
   "load_balancer_running":None,
   "backend_health_expected":None},
 "artifacts":{"gpu":"gpu.csv","host":"host.csv","process_memory":"process-memory.csv","link_start":"link-start.json","link_end":"link-end.json"}},indent=2)+"\n")
PY
mv "$OUT/manifest.json.tmp" "$OUT/manifest.json"
echo "Review manifest operator_assertions before accepting baseline: $(realpath "$OUT")"
