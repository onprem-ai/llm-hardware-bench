#!/usr/bin/env bash
# Read-only PCIe/GPU/NUMA topology and negotiated-link capture.
set -uo pipefail

OUT=${1:-pcie-topology-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$OUT/gpus"
exec > >(tee "$OUT/capture.log") 2>&1
printf 'captured_at=%s\n' "$(date -u --iso-8601=ns)"
printf 'hostname=%s\n' "$(hostname)"

capture() { local file=$1; shift; "$@" > "$OUT/$file" 2>&1 || printf 'WARN failed: %q\n' "$*"; }
capture uname.txt uname -a
capture lscpu.txt lscpu
capture lscpu-topology.csv lscpu -p=CPU,NODE,SOCKET,CORE,ONLINE
command -v numactl >/dev/null && capture numactl-hardware.txt numactl --hardware
capture lspci-tree.txt lspci -tv
capture lspci-numeric.txt lspci -Dnn
capture nvidia-topology.txt nvidia-smi topo -m
capture nvidia-p2p-read.txt nvidia-smi topo -p2p r
capture nvidia-p2p-write.txt nvidia-smi topo -p2p w
capture nvidia-nvlink-status.txt nvidia-smi nvlink --status
capture gpu-link-summary.csv nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max --format=csv
capture gpu-bar1.txt nvidia-smi -q -d MEMORY

nvidia-smi --query-gpu=index,pci.bus_id --format=csv,noheader,nounits 2>/dev/null |
while IFS=, read -r index bdf; do
  index=${index// /}; bdf=${bdf// /}; bdf=${bdf,,}
  [[ -n $bdf ]] || continue
  sys="/sys/bus/pci/devices/$bdf"
  lspci -Dvv -s "$bdf" > "$OUT/gpus/gpu-${index}-${bdf}.lspci-vv.txt" 2>&1 || true
  {
    printf 'gpu_index=%s\npci_bus_id=%s\n' "$index" "$bdf"
    for key in numa_node current_link_speed current_link_width max_link_speed max_link_width; do
      [[ -r "$sys/$key" ]] && printf '%s=%s\n' "$key" "$(cat "$sys/$key")" || printf '%s=unavailable\n' "$key"
    done
    printf 'iommu_group='; readlink "$sys/iommu_group" 2>/dev/null || printf 'unavailable\n'
  } > "$OUT/gpus/gpu-${index}-${bdf}.sysfs.txt"
done

capture iommu-kernel-command-line.txt cat /proc/cmdline
# shellcheck disable=SC2016 # Expansion intentionally occurs inside the child bash.
capture iommu-groups.txt bash -c 'for d in /sys/kernel/iommu_groups/*/devices/*; do [[ -e "$d" ]] && printf "%s %s\n" "$(basename "$(dirname "$(dirname "$d")")")" "$(basename "$d")"; done | sort -V'
printf 'output=%s\n' "$(realpath "$OUT")"
