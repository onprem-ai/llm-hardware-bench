#!/usr/bin/env bash
# Continuously sample /proc host CPU and memory counters until terminated.
set -euo pipefail
OUT=${1:?usage: sample-host.sh OUTPUT.csv [INTERVAL_SECONDS]}
INTERVAL=${2:-1}
mkdir -p "$(dirname "$OUT")"
printf '%s\n' 'timestamp_utc,cpu_user,cpu_nice,cpu_system,cpu_idle,cpu_iowait,cpu_irq,cpu_softirq,cpu_steal,mem_total_kib,mem_available_kib,cached_kib,buffers_kib,swap_total_kib,swap_free_kib,load1,load5,load15' > "$OUT"
trap 'exit 0' TERM INT
while :; do
  stamp=$(date -u --iso-8601=ns)
  read -r _ user nice system idle iowait irq softirq steal _ < /proc/stat
  declare -A m=()
  while read -r key value _; do m[${key%:}]=$value; done < /proc/meminfo
  read -r load1 load5 load15 _ < /proc/loadavg
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$stamp" "$user" "$nice" "$system" "$idle" "$iowait" "$irq" "$softirq" "${steal:-0}" \
    "${m[MemTotal]:-}" "${m[MemAvailable]:-}" "${m[Cached]:-}" "${m[Buffers]:-}" \
    "${m[SwapTotal]:-}" "${m[SwapFree]:-}" "$load1" "$load5" "$load15" >> "$OUT"
  sleep "$INTERVAL" & wait $! || exit 0
done
