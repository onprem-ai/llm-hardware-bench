#!/usr/bin/env bash
# Snapshot an existing exporter before/after an optional externally generated load.
# This script never starts a load and never changes the exporter.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: validate-fields.sh --output DIR [options]
  --endpoint URL       exporter metrics URL (default http://127.0.0.1:19400/metrics)
  --collector FILE     requested collector CSV
  --wait SECONDS       delay between snapshots (default 15)
  --load-executed      assert a controlled load ran during the interval
  --discovery FILE     optional dcgmi profile/dmon output

Start controlled load separately. Active PCIe tests must not overlap inference runs.
EOF
}
ENDPOINT=http://127.0.0.1:19400/metrics
COLLECTOR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/harness/2-preflight-conformance/code/configs/dcgm-custom.csv
WAIT=15
OUT=
DISCOVERY=
LOAD=0
while (($#)); do
  case "$1" in
    --endpoint) ENDPOINT=$2; shift 2;;
    --collector) COLLECTOR=$2; shift 2;;
    --wait) WAIT=$2; shift 2;;
    --output) OUT=$2; shift 2;;
    --discovery) DISCOVERY=$2; shift 2;;
    --load-executed) LOAD=1; shift;;
    -h|--help) usage; exit 0;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 2;;
  esac
done
[[ -n $OUT ]] || { usage >&2; exit 2; }
[[ $WAIT =~ ^[0-9]+$ ]] || { printf 'wait must be an integer\n' >&2; exit 2; }
mkdir -p "$OUT"
printf '%s\n' "$(date -u --iso-8601=ns)" > "$OUT/before.timestamp"
curl --fail --silent --show-error --max-time 30 "$ENDPOINT" > "$OUT/before.prom"
sleep "$WAIT"
printf '%s\n' "$(date -u --iso-8601=ns)" > "$OUT/after.timestamp"
curl --fail --silent --show-error --max-time 30 "$ENDPOINT" > "$OUT/after.prom"
args=(--collector "$COLLECTOR" --before "$OUT/before.prom" --after "$OUT/after.prom"
      --output "$OUT/metric-availability.json" --endpoint "$ENDPOINT")
((LOAD)) && args+=(--load-executed)
[[ -n $DISCOVERY ]] && args+=(--discovery "$DISCOVERY")
"$(dirname "${BASH_SOURCE[0]}")/metric-availability.py" "${args[@]}"
cat "$OUT/metric-availability.json"
