---
kind: record
status: current
date: 2026-09-19
purpose: how to work in this repository
produced_by: cross
---

# Contributing

This repository is a measurement instrument first and a codebase second. The
rules below exist because each one guards a failure the project actually hit.

## The machine

- `python3 harness/check_repo.py` — the repository checks itself: document
  ownership, link integrity, publication completeness (reproducibility +
  procedure blocks), and journal scope. It fails on **new** violations against
  a baseline; `--update-baseline` is for accepting a new floor deliberately,
  never for silencing a complaint you do not understand.
- `make test` — the chapter test suites. `make mock-e2e` exercises the whole
  pipeline on a mock campaign.
- Instruction documents carry frontmatter (`kind: rule|record`, `step`), and
  every rule has exactly one owning chapter. A rule stated in two places will
  drift; the checker refuses that.

## Adding a study

1. `results/<host>/` with a `study.yaml`; campaigns and their evidence
   summaries live under `results/<host>/<model>/`.
2. A published benchmark requires a `publication.json` carrying a
   `reproducibility` block (pinned container identity, model revision,
   **verbatim** launch commands read from the tracked deployment scripts,
   measurement client, corpus) and a `procedure` digest distilled from the
   journals. Gaps are declared in-band — `null` plus a note — never omitted.
3. Cold series only: every measured run served by a freshly launched engine.
   A warm-cache number is a different measurement and is labeled as one or
   not published.

## Journal scope

Journals and study records describe the LLM, the serving stack, and the
benchmark — nothing else. No IP addresses, no VPN/tunnel/SSH/BMC product
names or configuration, no credentials, no network topology. A host or
network event is recorded by its effect on the measurement, never by its
configuration. `check_repo` rule 10 enforces this; the fix for a violation is
rewriting the passage to the measurement effect, not silencing the check.

## Records and honesty

- Journals record what happened, including failures, outages, and withdrawn
  hypotheses. A wrong diagnosis is withdrawn explicitly, in place.
- Evidence payloads live off-repo (`_local-evidence/`, git-ignored) and are
  manifested; the repository carries the aggregated record plus the
  reproduction path.
