# Study Records

This directory contains lightweight, committed context for concrete benchmarking
studies. It is intentionally separate from reusable framework procedure and
code.

Create each study at:

```text
results/<study-id>/
```

Follow `INDEX.md`. At minimum, provide `README.md` and
`study.yaml`. Add these subdirectories as applicable:

```text
configs/    Frozen study decisions
hosts/      Observed machine/toolchain snapshots
campaigns/  Pointers to external result directories or object-store URIs
journal/    Dated observations and decisions
todos/      Deferred actions, triggers, and acceptance criteria
completed/  Retired TODOs retained for auditability
```

Raw benchmark output is never copied here. It remains under the external result
root specified by `harness/5-formal-campaign/RULES.md`.

## Current studies

- [`xe7740-8x-rtx6000/`](xe7740-8x-rtx6000/)
