#!/usr/bin/env bash
# Continuously sample portable nvidia-smi fields until terminated.
set -euo pipefail
OUT=${1:?usage: sample-nvidia-smi.sh OUTPUT.csv [INTERVAL_SECONDS]}
INTERVAL=${2:-1}
mkdir -p "$(dirname "$OUT")"
printf '%s\n' 'timestamp_utc,index,uuid,pci_bus_id,gpu_util_pct,memory_util_pct,memory_used_mib,memory_total_mib,power_w,temperature_c,sm_clock_mhz,memory_clock_mhz,pcie_gen,pcie_width' > "$OUT"
trap 'exit 0' TERM INT
while :; do
  stamp=$(date -u --iso-8601=ns)
  nvidia-smi --query-gpu=index,uuid,pci.bus_id,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu,clocks.sm,clocks.mem,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader,nounits 2>/dev/null |
    while IFS= read -r line; do printf '%s,%s\n' "$stamp" "$line"; done >> "$OUT" || true
  sleep "$INTERVAL" & wait $! || exit 0
done
