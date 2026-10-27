#!/usr/bin/env bash
set -uo pipefail
# Stop anything publishing 8080. The raster owns this port exclusively.
stopped=()
for c in $(docker ps --filter publish=8080 --format '{{.Names}}'); do
  docker stop -t 20 "$c" >/dev/null 2>&1 || true
  stopped+=("$c")
done
for _ in $(seq 1 60); do
  ss -ltn 2>/dev/null | grep -q ':8080 ' || break
  sleep 2
done
if ss -ltn 2>/dev/null | grep -q ':8080 '; then
  echo "free8080_failed listeners_remain"; exit 1
fi
echo "free8080_ok stopped=[${stopped[*]:-}]"
