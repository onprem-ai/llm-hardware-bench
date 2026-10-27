#!/usr/bin/env bash
# Capture a read-only software, hardware, container, and process inventory.
set -uo pipefail
OUT=${1:-environment-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$OUT"
exec > >(tee "$OUT/capture.log") 2>&1
capture(){ local name=$1; shift; "$@" >"$OUT/$name" 2>&1 || printf 'WARN failed: %q\n' "$*"; }
printf 'captured_at=%s\nhostname=%s\n' "$(date -u --iso-8601=ns)" "$(hostname)"
capture os-release.txt cat /etc/os-release
capture uname.txt uname -a
capture lscpu.txt lscpu
capture memory.txt cat /proc/meminfo
capture mounts.txt findmnt --real
capture filesystems.txt df -hT
capture block-devices.json lsblk --json --output NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL,ROTA
capture network-links.txt ip -details link
capture network-addresses.txt ip -details address
capture routes.txt ip route show table all
capture nvidia-smi-q.txt nvidia-smi -q
capture nvidia-apps-clocks.txt nvidia-smi --query-gpu=index,uuid,persistence_mode,compute_mode,power.limit,clocks.current.graphics,clocks.current.memory --format=csv
capture docker-version.txt docker version
capture docker-info.txt docker info
capture docker-ps.txt docker ps --no-trunc
capture python-version.txt python3 --version
command -v aiperf >/dev/null && capture aiperf-version.txt aiperf --version
command -v nvidia-ctk >/dev/null && capture nvidia-ctk-version.txt nvidia-ctk --version
command -v chronyc >/dev/null && capture chrony-tracking.txt chronyc tracking
capture kernel-cmdline.txt cat /proc/cmdline
capture sysctl-selected.txt sysctl kernel.numa_balancing vm.swappiness vm.min_free_kbytes vm.watermark_scale_factor kernel.perf_event_paranoid kernel.kptr_restrict
printf 'output=%s\n' "$(realpath "$OUT")"
