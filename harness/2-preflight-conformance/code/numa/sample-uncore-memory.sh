#!/usr/bin/env bash
# Sample aggregate Intel memory-controller traffic using kernel-named PMU events.
set -euo pipefail
OUT=${1:?usage: sample-uncore-memory.sh OUTPUT.csv [DURATION_SECONDS] [INTERVAL_MS]}
DURATION=${2:-60}
INTERVAL=${3:-1000}
mkdir -p "$(dirname "$OUT")"
for event in cas_count_read_sch0 cas_count_read_sch1 cas_count_write_sch0 cas_count_write_sch1; do
  compgen -G "/sys/bus/event_source/devices/uncore_imc_*/events/$event" >/dev/null || { echo "named IMC event unavailable: $event" >&2; exit 3; }
done
sudo -n true >/dev/null 2>&1 || { echo 'passwordless sudo is required for system-wide uncore PMUs' >&2; exit 4; }
# perf CSV includes interval,value,unit,event,...; retain raw output and stderr.
sudo -n perf stat -a -x, -I "$INTERVAL" \
  -e uncore_imc/cas_count_read_sch0/ \
  -e uncore_imc/cas_count_read_sch1/ \
  -e uncore_imc/cas_count_write_sch0/ \
  -e uncore_imc/cas_count_write_sch1/ \
  -o "$OUT" -- sleep "$DURATION" 2>"$OUT.stderr"
