#!/usr/bin/env bash
# Preserve timestamped raw HAProxy Prometheus samples until terminated.
set -euo pipefail
OUT=${1:?usage: sample-prometheus.sh OUTPUT.promjsonl [INTERVAL_SECONDS] [URL]}
INTERVAL=${2:-1}
URL=${3:-http://127.0.0.1:8404/metrics}
mkdir -p "$(dirname "$OUT")"
trap 'exit 0' TERM INT
while :; do
  stamp=$(date -u --iso-8601=ns)
  body=$(curl -fsS --max-time 5 "$URL" || true)
  python3 - "$stamp" "$body" >> "$OUT" <<'PY'
import json,sys
print(json.dumps({"timestamp_utc":sys.argv[1],"prometheus_text":sys.argv[2]},separators=(',',':')))
PY
  sleep "$INTERVAL" & wait $! || exit 0
done
