# DCGM fabric telemetry deployment

This directory provides an **opt-in qualification sidecar**, not an automatic
replacement for an existing exporter. It is deliberately bound to loopback port
`19400` so it cannot silently replace the production scrape target on `9400`.

## Safety contract

- Do not launch, restart, or replace telemetry during a measured campaign.
- First preserve `docker inspect`, image digest, logs, collector configuration,
  and the current `/metrics` response from the production exporter.
- An exporter normally embeds a DCGM host engine. Do not assume two embedded
  host engines can safely own profiling resources concurrently.
- DCGM profiling can conflict with CUPTI/Nsight. Pause one owner before the
  other starts.
- A field selected in CSV but absent from `/metrics` is **unavailable**, not zero.
- Active validation loads belong in an idle qualification window.

## Image selection

Select an exporter/DCGM pair compatible with the target GPU and driver, then pin
its immutable OCI digest in the study host record and campaign manifest. Do not
copy a digest from another host without qualification.

```bash
export DCGM_EXPORTER_IMAGE='<registry>/<image>@sha256:<digest>'
docker compose -f harness/2-preflight-conformance/code/deployments/observability/dcgm-exporter.compose.yaml config
```

Do not run `up` until inference and the existing exporter can be stopped in an
approved idle window. Prefer replacing the existing exporter temporarily over
running two embedded host engines.

## Idle-window qualification sequence

1. Capture the current deployment and topology.
2. Stop the existing exporter only after campaign completion.
3. Start this sidecar and retain its startup logs.
4. Confirm `curl -f http://127.0.0.1:19400/metrics`.
5. Run `harness/2-preflight-conformance/code/dcgm/discover-fields.sh` using a matching DCGM utility image
   or package. The exporter image may not contain `dcgmi`.
6. Take an idle before/after validation without `--load-executed`.
7. Separately run a controlled CUDA P2P or NCCL load, then validate with
   `--load-executed`. Never run that load alongside inference measurements.
8. Record all field states in `metric-availability.json`.
9. Stop the qualification exporter and restore the original exporter exactly.
10. Verify the original scrape target and archive rollback evidence.

Example passive snapshot:

```bash
harness/2-preflight-conformance/code/dcgm/validate-fields.sh \
  --endpoint http://127.0.0.1:19400/metrics \
  --output "$CAMPAIGN/fabric/dcgm-idle"
```

For controlled-load validation, start the load separately and ensure it spans
the snapshot interval:

```bash
harness/2-preflight-conformance/code/dcgm/validate-fields.sh --load-executed --wait 30 \
  --endpoint http://127.0.0.1:19400/metrics \
  --output "$CAMPAIGN/fabric/dcgm-controlled-load"
```

The script does not claim which load ran; the fabric manifest must record its
command, binary hash, GPU set, timing, and result path.
