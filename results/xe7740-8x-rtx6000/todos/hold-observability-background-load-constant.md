# Hold the Observability Background Load Constant

```yaml
status: open
trigger: no measured campaign in progress on xe7740-04
owner: unassigned
created_at: 2026-09-06T08:14:30Z
evidence: ../journal/2026-09-06-observability-background-load.md
```

## Purpose

The container metric agent in the local observability stack consumes 24–45 CPU
cores continuously and its load varied roughly 2.5× across campaign days
(13.7 cores mean on 2026-09-01 versus 33.8 on 2026-09-05). Bound it, verify the
bound, and quantify whether any existing result needs a caveat.

## Blocking constraint

Do not start until the in-progress `glm53-raster` sweep closes. Changing telemetry
mid-campaign splits one result set across two environments, which is harder to
interpret than uniform contamination.

## Steps

1. Add the `command:` block from the evidence journal to the `cadvisor` service in
   `/home/demouser/observability/compose.yaml` (`-disable_metrics=disk,diskIO` is
   the load-bearing option). Throttling with `docker update --cpus=2` is not
   sufficient: it leaves the filesystem walks running back-to-back and starves
   their own metrics.
2. Recreate the service and confirm the agent sits below two cores, that no
   `disk usage and inodes` line appears in ten minutes of its logs, and that its
   VictoriaMetrics target stays `up`.
3. Re-run `harness/2-preflight-conformance/code/check-host.sh` and confirm the background-load gate passes;
   retain `mpstat-background.txt`, `pidstat-background.txt`,
   `container-background.tsv`, and `preflight-summary.json`.
4. Re-point the five dead scrape targets (`haproxy` on 8405, `vllm_a`–`vllm_d` on
   9400–9403) at the current server metrics endpoint, so a future sweep captures
   server-side telemetry.
5. Run a present/absent A/B for one frozen configuration across the concurrency
   grid and compare P50/P99 TTFT and ITL as well as throughput.
6. Screen prior campaigns for their actual background load using the retained
   `host.csv` load columns and the agent's CPU series in VictoriaMetrics. Record
   which comparisons survive unchanged and which need a caveat or a rerun.

## Acceptance criteria

- Ambient non-benchmark CPU below two cores at preflight and in B0/B1 baselines.
- Every remaining non-benchmark container either cgroup-bounded or documented.
- All scrape targets `up` during a measured run.
- A recorded ambient-load figure accompanies each new result.
- A written statement on whether pre-2026-09-06 comparisons need caveats.
