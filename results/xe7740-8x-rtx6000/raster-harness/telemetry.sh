#!/usr/bin/env bash
set -uo pipefail
OUT=$1; NAME=${2:-radixark-glm53-raster}
[[ -s "$OUT" ]] || printf 'utc,memory_current_bytes,power_w,util_pct\n' > "$OUT"
while true; do
 mem=NA
 id=$(docker inspect --format '{{.Id}}' "$NAME" 2>/dev/null || true)
 if [[ -n "$id" ]]; then
   cur="/sys/fs/cgroup/system.slice/docker-${id}.scope/memory.current"
   [[ -f "$cur" ]] && mem=$(cat "$cur" 2>/dev/null || echo NA)
 fi
 pw=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits 2>/dev/null | paste -sd, - || true)
 ut=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | paste -sd, - || true)
 printf '%s,%s,%s,%s\n' "$(date -u +%FT%TZ)" "${mem:-NA}" "${pw:-NA}" "${ut:-NA}" >> "$OUT"
 sleep 5
done
