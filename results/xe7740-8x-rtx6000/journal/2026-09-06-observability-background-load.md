# Observability agent inflated background load and confounds campaign comparison

Date: 2026-09-06
Host: `xe7740-04`
Status: diagnosed; host remediation pending an active-campaign gap

## Finding

The local observability stack's container metric agent runs unbounded and consumes
24–45 CPU cores continuously, mostly on recursive filesystem-usage walks that
produce metrics no dashboard consumes. Its load is not constant: it varied by
about 2.5× across the days on which campaigns in this study were measured. That
makes it an uncontrolled covariate in cross-campaign and cross-model comparisons.

It is not currently starving the serving stack. Measured runqueue wait for the
serving threads was zero, and aggregate GPU-side throughput is limited elsewhere.
The exposure is tail latency at low concurrency and, more seriously, comparability
between campaigns measured on different days.

## Direct evidence

Ten-second differential of `/proc/<pid>/stat` and `/proc/<pid>/task/*/schedstat`
while the GLM-5.3 TP8 server was loaded:

```text
process                 cores   runqueue-wait cores
obs-cadvisor             42.96                 0.17
vLLM TP worker            0.64                 0.00
vLLM EngineCore           0.41                 0.00
vLLM API front end        0.06                 0.00
runnable tasks            15 of 344 CPUs
```

Aggregate ambient load cross-checked three ways during the same period:

```text
ambient busy CPU (delta of /proc/stat over wall-clock window) = 34.93 cores
load1 = 2.50
vmstat us/sy = 7%/1% of 344 CPUs  (~24-34 cores)
```

`obs-cadvisor` accounted for essentially all of it. Its lifetime average was
2,444% CPU, having accumulated 230 CPU-days in the 9 days since it started.

## Root cause

```text
image      ghcr.io/google/cadvisor:v0.60.5
started    2026-08-27T21:40:09Z   privileged   no CPU/pids quota
compose    /home/demouser/observability/compose.yaml  (no `command:` key)
```

With no `command:` override the agent runs stock defaults. Two of them are
expensive here: `-housekeeping_interval` defaults to `1s`, and the `disk` metric
is enabled by default (the default `-disable_metrics` list is
`advtcp,cpu_topology,cpuset,hugetlb,memory_numa,process,referenced_memory,resctrl,sched,tcp,udp`,
which does not include `disk` or `diskIO`). The `disk` collector recursively walks
each container's overlayfs writable layer to publish `container_fs_usage_bytes`,
and the `radixark-glm53-ram96` layer holds 28 GB:

```text
fs: disk usage and inodes count on following dirs took 3.885s  (repeated, ~7 per 10 min)
failed to collect filesystem stats - could not stat "/var/lib/docker/rootfs/overlayfs/..."
```

Only ~227 MB came from the block device; the tree is resident in page cache, so
this is CPU spin, not I/O wait. The work buys almost nothing: no Grafana dashboard
references `container_fs`, and the surviving series in VictoriaMetrics are only
root pseudo-entries, because the paths it derives from `/rootfs` fail to stat.

## Ambient load by campaign day

`max by(name)(rate(container_cpu_usage_seconds_total{name="obs-cadvisor"}[10m]))`,
hourly samples, from VictoriaMetrics:

```text
date        mean cores   max cores   campaigns measured that day
2026-08-29        21.2        35.3   RadixArk qualification; Qwen model correction
2026-08-30        34.5        35.2   GLM-5.3 seq64/graph256 canary
2026-08-31        18.7        34.5   seq64/graph256 finding
2026-09-01        13.7        15.1   Qwen3.8-Flash-Next aggressive tuning
2026-09-02        18.7        32.3   DeepSeek-V4-Flash evolutionary + formal
2026-09-03        31.3        36.9   none
2026-09-04        33.4        34.5   GLM-5.3 raster
2026-09-05        33.8        34.5   GLM-5.3 raster
2026-09-06        33.7        34.5   glm53-raster gen1/gen2 sweeps
```

The Sep 1 tuning campaign ran with roughly 14 background cores; the Sep 5–6
raster runs at roughly 34. Model-vs-model claims spanning those dates inherit the
difference unless it is accounted for.

## Related measurement-integrity findings

1. **Five scrape targets are down:** `haproxy` (`host.docker.internal:8405`) and
   `vllm_a`–`vllm_d` (`host.docker.internal:9400-9403`), left over from the
   dual-server layout (`scrape.yaml.before-glm53-dual-20260827T221353`). The live
   server exposes metrics on `:8080/metrics`, so the `glm53-raster` sweeps in
   progress capture host and GPU telemetry but no server-side telemetry.
2. **`utilization.gpu` is not a busy signal on this server.** It read 93–100%
   while `vllm:num_requests_running` was 1, because the server spins on CUDA
   graphs and asynchronous scheduling. Idle state must be asserted from power
   draw and allocated frame memory.

## Comparability of existing data

`harness/2-preflight-conformance/code/host/sample-host.sh` already records `load1`, `load5`, and `load15`
every second and is wired into
`configs/radixark-glm53-seq64-graph256-formal-direct.yaml`,
`configs/radixark-glm53-graph128-missing-decode.yaml`, and
`configs/deepseek-v4-flash-formal-20260902.yaml`. Combined with the retained
cadvisor CPU series in VictoriaMetrics, every prior campaign window can be
screened for its actual background load instead of assuming it was equal.

## Remediation

Apply between campaigns only. Never restart or reconfigure telemetry while a
campaign is being measured; that splits one result set across two environments.

Remove the work rather than throttling it, in
`/home/demouser/observability/compose.yaml` under the `cadvisor` service:

```yaml
command:
  - -docker_only=true
  - -housekeeping_interval=10s
  - -max_housekeeping_interval=1m
  - -disable_metrics=disk,diskIO,app,perf_event,pressure
  - -max_procs=2
```

A `docker update --cpus=2` alone is not sufficient: it caps the agent without
removing the walks, so they run back-to-back, `container_*` metrics go stale, and
the scrape target can flip to down.

Verification after the change: agent below two cores, no `disk usage and inodes`
lines across ten minutes of logs, and `harness/2-preflight-conformance/code/check-host.sh` reporting a clean
background-load gate. Then quantify the effect with a present/absent A/B on one
frozen configuration across the concurrency range, comparing P50/P99 TTFT and ITL
as well as throughput, before deciding whether any published figure needs a caveat
or a rerun.

## Reproduction

```bash
# ambient load, top foreign consumers, per-container CPU with quota
LLM_BENCH_BG_SAMPLE_SECONDS=10 harness/2-preflight-conformance/code/check-host.sh /tmp/preflight-bg

# who is burning CPU, excluding the serving stack
pidstat -u 1 10 | awk '/^Average:/{f=1} f && $8+0>1 {print $NF, $8/100" cores"}'

# agent cost and history
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}'
curl -sG http://127.0.0.1:8428/api/v1/query_range \
  --data-urlencode 'query=max by(name)(rate(container_cpu_usage_seconds_total[10m]))' \
  --data-urlencode "start=$(date -d '-8 days' +%s)" --data-urlencode "end=$(date +%s)" \
  --data-urlencode step=3600

# filesystem-walk evidence
docker logs --since 10m obs-cadvisor 2>&1 | grep -c "disk usage and inodes"
```

## Framework changes made

- `PROCEDURE.md` §4.1 defines background-load qualification, the "low queueing is
  not proof of no interference" and "drift breaks comparability" rules, and the
  prohibition on mid-campaign telemetry changes.
- `PROCEDURE.md` §7.1 B0 now requires asserting GPU idleness from power and
  allocated memory rather than utilization percent.
- `PROCEDURE.md` §8.2 requires ambient CPU in the collected and reported set.
- `harness/2-preflight-conformance/code/check-host.sh` now samples ambient load, per-container CPU with cgroup
  quota, and the largest non-serving process, and fails the gate on an unbounded
  multi-core foreign consumer.
