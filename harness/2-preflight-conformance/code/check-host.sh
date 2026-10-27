#!/usr/bin/env bash
set -uo pipefail

OUT=${1:-preflight-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$OUT"
FAIL=0
WARN=0
pass(){ printf 'PASS %s\n' "$*"; }
warn(){ printf 'WARN %s\n' "$*"; WARN=$((WARN+1)); }
fail(){ printf 'FAIL %s\n' "$*"; FAIL=$((FAIL+1)); }
have(){ command -v "$1" >/dev/null 2>&1; }

exec > >(tee "$OUT/check-host.log") 2>&1
printf 'benchmark_host_preflight_utc=%s\n' "$(date -u --iso-8601=ns)"
printf 'output=%s\n' "$(realpath "$OUT")"

for x in bash git curl jq python3 docker nvidia-smi tmux numactl lspci mpstat pidstat vmstat perf; do
  if have "$x"; then pass "tool:$x=$(command -v "$x")"; else fail "missing-tool:$x"; fi
done
for x in dcgmi cmake mpirun pcm-memory nvidia-ctk ethtool lstopo chronyc; do
  if have "$x"; then pass "optional-tool:$x=$(command -v "$x")"; else warn "optional-tool-missing:$x"; fi
done

hostname > "$OUT/hostname.txt"
uname -a > "$OUT/uname.txt"
cat /etc/os-release > "$OUT/os-release.txt"
lscpu > "$OUT/lscpu.txt"
numactl --hardware > "$OUT/numactl.txt" 2>&1 || true
lspci -tv > "$OUT/lspci-tree.txt" 2>&1 || true
nvidia-smi -q > "$OUT/nvidia-smi-q.txt" 2>&1 || fail "nvidia-smi-query"
nvidia-smi topo -m > "$OUT/nvidia-topology.txt" 2>&1 || fail "nvidia-topology"
nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,driver_version,memory.total,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max,power.limit --format=csv > "$OUT/gpu-links.csv" 2>&1 || warn "gpu-link-query-partially-unsupported"

gpus=$(nvidia-smi -L 2>/dev/null | wc -l | tr -d ' ')
if [[ ${gpus:-0} -gt 0 ]]; then pass "gpu-count=$gpus"; else fail "no-gpus"; fi

if docker info > "$OUT/docker-info.txt" 2>&1; then pass docker-info; else fail docker-info; fi
if docker ps >/dev/null 2>&1; then pass docker-access; else fail docker-access; fi

if docker run --rm --gpus all --entrypoint nvidia-smi "${CUDA_PROBE_IMAGE:-nvidia/cuda:13.0.2-base-ubuntu24.04}" -L > "$OUT/container-gpu-probe.txt" 2>&1; then
  pass container-gpu-access
else
  warn "container-gpu-probe-failed (set CUDA_PROBE_IMAGE to a pinned available image)"
fi

if have chronyc && chronyc tracking > "$OUT/time-sync.txt" 2>&1; then pass chrony; else
  timedatectl show > "$OUT/time-sync.txt" 2>&1 || true
  if grep -q 'NTPSynchronized=yes' "$OUT/time-sync.txt"; then pass ntp-sync; else fail ntp-sync; fi
fi

# --- background-load (noisy-neighbour) gate --------------------------------
# Every always-on agent that consumes CPU is part of every measured latency and
# throughput number. Ambient load must be sampled, recorded, and approximately
# constant across all members of a comparison set; drift between campaigns
# invalidates cross-campaign comparison even when aggregate throughput looks
# unaffected. Thresholds are overridable so a host may qualify its own baseline.
bg_seconds=${LLM_BENCH_BG_SAMPLE_SECONDS:-10}
bg_ambient_warn=${LLM_BENCH_BG_AMBIENT_WARN_CORES:-2}
# Colocated serving and load-generation processes are exempt by name; extend the
# regex for locally chosen container names so exemptions stay deliberate.
serving_re=${LLM_BENCH_SERVING_PROCESS_REGEX:-'(vllm|sglang|trtllm|triton|tgi|llm-|haproxy|nginx|aiperf|bench|genai)'}
core_count=$(nproc)
# On large hosts a fixed core count is either noisy or blunt, so the default scales
# with core count. Setting the variable explicitly is honoured exactly.
bg_max_foreign_cores=${LLM_BENCH_BG_MAX_FOREIGN_CORES:-}
if [[ -z "$bg_max_foreign_cores" ]]; then
  bg_max_foreign_cores=$(awk -v c="$core_count" 'BEGIN{ m=int(c*0.02+0.5); if (m<4) m=4; printf "%d", m }')
fi
# Sampler/self and kernel worker threads cannot be reconfigured by an operator, so
# they are excluded from the per-process gate; ambient load still reports them.
self_re='^(pidstat|mpstat|vmstat|iostat|sadc|perf|tee|cat|sleep|awk|bash|sh|check-host\.sh)$'
kernel_re='^(kworker|ksoftirqd|rcu_|migration/|kswapd|khugepaged|kcompactd|jbd2|kthreadd|systemd|sshd|rsyslogd)'

read -r _ bu bn bs bi bw bq bsq bst _ < /proc/stat
window_start_ns=$(date +%s%N)
if have mpstat; then
  mpstat -P ALL 1 "$bg_seconds" > "$OUT/mpstat-background.txt" 2>&1 || warn "mpstat-background-sample-failed"
fi
if have pidstat; then
  pidstat -u 1 "$bg_seconds" > "$OUT/pidstat-background.txt" 2>&1 || warn "pidstat-background-sample-failed"
fi
if have docker && [[ -n "$(docker ps -q 2>/dev/null)" ]]; then
  {
    printf 'name\tcpu_percent\tcpu_cores\tcpu_quota_cores\tmemory\n'
    docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' 2>/dev/null \
    | while IFS='|' read -r cname cperc cmem; do
        [[ -z "$cname" ]] && continue
        ccores=${cperc%\%}; ccores=${ccores:-0}
        nano=$(docker inspect -f '{{.HostConfig.NanoCpus}}' "$cname" 2>/dev/null || echo 0)
        quota=$(awk -v n="${nano:-0}" 'BEGIN{ if (n>0) printf "%.2f", n/1000000000; else printf "unlimited" }')
        printf '%s\t%s\t%s\t%s\t%s\n' "$cname" "$cperc" "$(awk -v c="$ccores" 'BEGIN{printf "%.2f", c/100}')" "$quota" "$cmem"
      done
  } > "$OUT/container-background.tsv" 2>&1 || warn "docker-stats-sample-failed"
fi
read -r _ eu en es ei ew eq esq est _ < /proc/stat
window_end_ns=$(date +%s%N)
# Load is sampled after the window so it reflects the sampled interval, whose real
# length is wall-clock elapsed time (the samplers above each run for bg_seconds).
read -r load1 load5 load15 _ < /proc/loadavg

ambient_cores=$(awk -v b1=$((bu+bn+bs+bq+bsq)) -v b2=$((eu+en+es+eq+esq)) \
  -v t1=$((bu+bn+bs+bi+bw+bq+bsq+bst)) -v t2=$((eu+en+es+ei+ew+eq+esq+est)) \
  -v hz="$(getconf CLK_TCK)" -v ns=$((window_end_ns - window_start_ns)) \
  'BEGIN{ span=t2-t1; if (span<=0 || ns<=0) { printf "0.00"; exit } printf "%.2f", ((b2-b1)*1000000000/hz)/ns }')

# Highest-CPU non-serving process over the sample window. sysstat releases differ
# in column order and the Average section repeats the header, so %CPU is located
# by header name and rows are keyed on the Average: prefix.
foreign_line=$(awk -v re="$serving_re" -v self="$self_re" -v kern="$kernel_re" '
  { for (i = 1; i <= NF; i++) if ($i == "%CPU") cpu = i }
  /^Average:/ { avg = 1 }
  avg && cpu > 0 && $1 == "Average:" && $2 ~ /^[0-9]+$/ && NF >= cpu {
    c = $cpu / 100.0
    name = $NF
    if (name !~ re && name !~ self && name !~ kern && name != "-" && c > max) { max = c; who = name }
  }
  END { printf "%.2f %s", max + 0, (who ? who : "none") }' "$OUT/pidstat-background.txt" 2>/dev/null)
foreign_cores=${foreign_line%% *}
foreign_proc=${foreign_line#* }
if [[ -z "$foreign_cores" ]]; then foreign_cores=0.00; foreign_proc=unknown; fi

if awk -v c="$foreign_cores" -v m="$bg_max_foreign_cores" 'BEGIN{ exit !(c > m) }'; then
  fail "background-noisy-neighbour=${foreign_proc}=${foreign_cores}cores>${bg_max_foreign_cores}cores"
else
  pass "background-foreign-max=${foreign_proc}=${foreign_cores}cores"
fi
if awk -v c="$ambient_cores" -v w="$bg_ambient_warn" 'BEGIN{ exit !(c > w) }'; then
  warn "ambient-background-load=${ambient_cores}cores>${bg_ambient_warn}cores (load ${load1}/${load5}/${load15} on ${core_count} cpus)"
else
  pass "ambient-background-load=${ambient_cores}cores load ${load1}/${load5}/${load15} cpus=${core_count}"
fi
printf 'INFO background-gate-threshold=%score foreign_consumer_max (override with LLM_BENCH_BG_MAX_FOREIGN_CORES)\n' "$bg_max_foreign_cores"
if [[ -s "$OUT/container-background.tsv" ]]; then
  # Collect in the parent shell so findings reach the summary counters.
  bg_names=(); bg_cores_list=(); bg_quota_list=()
  while IFS='|' read -r bname bcores bquota; do
    [[ -z "$bname" ]] && continue
    bg_names+=("$bname"); bg_cores_list+=("$bcores"); bg_quota_list+=("$bquota")
  done < <(
    awk -v re="$serving_re" 'NR > 1 && $3 != "" {
        cores = $3 + 0
        if (cores <= 1 || $1 ~ re) next
        printf "%s|%.2f|%s\n", $1, cores, $4
      }' "$OUT/container-background.tsv"
  )
  n=${#bg_names[@]}
  for ((k = 0; k < n; k++)); do
    bname=${bg_names[$k]}; bcores=${bg_cores_list[$k]}; bquota=${bg_quota_list[$k]}
    if awk -v c="$bcores" -v m="$bg_max_foreign_cores" 'BEGIN{ exit !(c > m) }'; then
      fail "container-background-noisy-neighbour=${bname}=${bcores}cores>${bg_max_foreign_cores}cores(quota=${bquota})"
    elif [[ "$bquota" == "unlimited" ]]; then
      warn "container-unbounded-background=${bname} cores=${bcores} quota=none"
    else
      printf 'INFO container-background-bounded=%s cores=%s quota=%s\n' "$bname" "$bcores" "$bquota"
    fi
  done
fi

root=${LLM_BENCH_RESULTS_ROOT:-${HOME}/llm-benchmark-results}
if mkdir -p "$root" 2>/dev/null && [[ -w "$root" ]]; then pass "results-root=$root"; else fail "results-root-not-writable:$root"; fi
df -B1 "$root" > "$OUT/results-filesystem.txt" 2>&1 || true
avail=$(df -B1 --output=avail "$root" 2>/dev/null | tail -1 | tr -d ' ')
if [[ ${avail:-0} -ge ${MIN_FREE_BYTES:-107374182400} ]]; then pass "free-bytes=$avail"; else fail "insufficient-free-bytes=${avail:-unknown}"; fi

for port in 9400 8428; do
  if curl -fsS --max-time 3 "http://127.0.0.1:$port/metrics" > "$OUT/metrics-$port.txt" 2>/dev/null; then pass "metrics-port:$port"; else warn "metrics-port-unreachable:$port"; fi
done

if [[ -s "$OUT/metrics-9400.txt" ]]; then
  for metric in DCGM_FI_DEV_GPU_UTIL DCGM_FI_DEV_POWER_USAGE DCGM_FI_PROF_PCIE_RX_BYTES DCGM_FI_PROF_PCIE_TX_BYTES DCGM_FI_DEV_PCIE_REPLAY_COUNTER; do
    if grep -q "^$metric" "$OUT/metrics-9400.txt"; then pass "dcgm-metric:$metric"; else warn "dcgm-metric-unavailable:$metric"; fi
  done
fi

find "${NCCL_TESTS_ROOT:-/opt/nccl-tests}" -type f \( -name all_reduce_perf -o -name all_gather_perf -o -name reduce_scatter_perf \) -executable 2>/dev/null | sort > "$OUT/nccl-tests-binaries.txt"
if [[ $(wc -l < "$OUT/nccl-tests-binaries.txt") -ge 3 ]]; then pass nccl-tests; else warn nccl-tests-missing; fi

python3 - "$OUT/preflight-summary.json" "$FAIL" "$WARN" "$gpus" "$root" "$ambient_cores" "$load1" "$load5" "$load15" "$foreign_cores" "$foreign_proc" <<'PY'
import json,sys,datetime,os
p,fail,warn,gpus,root,ambient,load1,load5,load15,foreign_cores,foreign_proc=sys.argv[1:]
d={"schema_version":1,"checked_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"failures":int(fail),"warnings":int(warn),"gpu_count":int(gpus or 0),"results_root":os.path.abspath(root),
   "background_load":{"ambient_cores":float(ambient or 0),
                      "load_average":[float(load1 or 0),float(load5 or 0),float(load15 or 0)],
                      "top_foreign_process":foreign_proc,"top_foreign_cores":float(foreign_cores or 0)},
   "ready":int(fail)==0}
open(p,"w").write(json.dumps(d,indent=2)+"\n")
PY

printf 'SUMMARY failures=%d warnings=%d\n' "$FAIL" "$WARN"
[[ $FAIL -eq 0 ]]
