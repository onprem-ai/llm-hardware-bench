#!/usr/bin/env bash
# Read-only DCGM capability discovery. Does not start, stop, or reconfigure DCGM.
set -uo pipefail

OUT=${1:-dcgm-discovery-$(date -u +%Y%m%dT%H%M%SZ)}
DCGM_CONTAINER=${DCGM_CONTAINER:-}
mkdir -p "$OUT"
exec > >(tee "$OUT/discovery.log") 2>&1

run_dcgmi() {
  if command -v dcgmi >/dev/null 2>&1; then dcgmi "$@"
  elif [[ -n "$DCGM_CONTAINER" ]]; then docker exec "$DCGM_CONTAINER" dcgmi "$@"
  else return 127
  fi
}

printf 'captured_at=%s\n' "$(date -u --iso-8601=ns)"
printf 'hostname=%s\n' "$(hostname)"
nvidia-smi -L > "$OUT/nvidia-smi-L.txt" 2>&1 || true
nvidia-smi --query-gpu=index,uuid,pci.bus_id --format=csv,noheader > "$OUT/gpus.csv" 2>&1 || true

if ! run_dcgmi --version > "$OUT/dcgmi-version.txt" 2>&1; then
  printf 'ERROR: dcgmi unavailable. Set DCGM_CONTAINER to a matching utility container containing dcgmi.\n'
  printf 'Do not assume the dcgm-exporter image contains dcgmi.\n'
  exit 2
fi
run_dcgmi dmon --list > "$OUT/dmon-fields.txt" 2>&1 || true
: > "$OUT/profile-index.tsv"
while IFS=, read -r index _; do
  index=${index// /}
  [[ $index =~ ^[0-9]+$ ]] || continue
  status=ok
  run_dcgmi profile --list --entity-id "gpu:$index" --json \
    > "$OUT/profile-gpu-${index}.json" 2> "$OUT/profile-gpu-${index}.stderr" || status=failed
  if [[ $status == failed || ! -s "$OUT/profile-gpu-${index}.json" ]]; then
    run_dcgmi profile --list --entity-id "gpu:$index" \
      > "$OUT/profile-gpu-${index}.txt" 2>> "$OUT/profile-gpu-${index}.stderr" || status=failed
  fi
  printf '%s\t%s\n' "$index" "$status" >> "$OUT/profile-index.tsv"
done < "$OUT/gpus.csv"
printf 'output=%s\n' "$(realpath "$OUT")"
