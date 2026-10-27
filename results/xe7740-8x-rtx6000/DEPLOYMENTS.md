# Deployment contracts

One directory per published benchmark, named for its publication id. Each
records how the inference servers behind that publication were actually
started: container identity, the launch command per profile, replica topology,
and the load balancer in front of them.

These sit beside `campaigns/` and `publications/` so a reader can go from a
number on the website to the process that produced it without leaving the
repository.

## Why these exist separately

The launch-record rule (chapter 3) already requires the full launch command and environment per run
(the same rule), written to `launch-command.txt` in each run directory
(the same rule). That has not been happening: as of 2026-09-02 the
campaign tree on `xe7740-04` held 402 run manifests and zero `launch-command.txt`,
`environment.txt` or `model-files.txt` files.

The contracts here were recovered afterwards by reading the ad-hoc scripts that
drove the campaigns. They are a backfill, not a substitute for the per-run
receipts. Until the runner writes `launch-command.txt`, nothing ties an
individual run to the deployment that served it — the mapping from a run to a
profile below is inferred from directory layout and the publication's
`selection` block, not recorded as fact.

## Layout

```text
<publication-id>/
├── deployment.yaml     container identity, profiles, topology, provenance
├── launch-replicas.sh  the docker run that starts one profile's replicas
├── <profile>/launch.sh in-container server command, verbatim
└── haproxy.cfg         load balancer the measured traffic passed through
```

A publication whose measurements come from more than one server configuration
has one `<profile>/` per configuration, named to match the `source_id` values in
its `normalized_data.selection`.
