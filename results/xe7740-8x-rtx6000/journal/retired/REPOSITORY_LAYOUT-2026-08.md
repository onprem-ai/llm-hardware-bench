<!--
  RETIRED 2026-09-06. Repository layout is generated now: INDEX.md is the map and
  PIPELINE.md owns the chapters. A hand-maintained layout document is a second owner
  for the tree, which is the failure R-PIPE-1 exists to prevent. Kept as evidence
  per R-PIPE-4.
-->

---
kind: rule
step: cross
title: Superseded by INDEX.md; kept for citations
---

# Repository Information Architecture

This repository separates reusable benchmark machinery from records about a
particular study, host, deployment, or campaign.

## Reusable framework

The following top-level paths must remain host- and campaign-independent:

```text
PROCEDURE.md       Normative benchmark method
analysis/          Reusable analysis programs
bootstrap/         Generic installation inputs and guidance
collectors/        Reusable telemetry collectors
configs/           Generic defaults, policies, and metric definitions
deployments/       Parameterized deployment templates
schemas/           Machine-readable contracts
reports/           Generic report contract, templates, and approved visual reference
runners/           Reusable campaign runners
preflight/         Generic readiness checks
docs/              Cross-study methodology and contracts
tests/             Tests for framework code
```

Generic documents may use clearly marked placeholders or synthetic examples.
They must not silently prescribe a particular hostname, user home directory,
active campaign, model revision, container name, or observed image digest.

Comparable reporting is governed by `harness/7-report-and-feedback/REPORT_SPEC.md`. Campaign-specific
facts enter through a validated `report-config.json`, while analysis adapters
produce normalized data conforming to `harness/7-report-and-feedback/schemas/normalized-report-data.schema.json`.
The approved HTML under `harness/7-report-and-feedback/code/reference/` is a golden visual baseline, not a
place to store current campaign results.

## Study records

Committed information specific to a hardware investigation belongs under:

```text
results/<study-id>/
├── README.md
├── study.yaml
├── configs/
│   ├── concurrency-grids.yaml
│   └── other frozen study-level decisions
├── hosts/
│   └── <host>.yaml
├── campaigns/
│   └── <campaign-id>.yaml
├── journal/
│   └── YYYY-MM-DD.md
├── todos/
│   └── <action>.md
└── completed/
    └── <retired-action>.md
```

A study ID is a stable lowercase slug describing the investigation, not merely
a date. A study can involve one or more hosts and model campaigns.

### `README.md`

States the study objective, scope, status, owners if applicable, and links to
its configurations, host records, campaign pointers, journal, and TODOs.

### `study.yaml`

Machine-readable study identity and policy selections. It may reference generic
framework documents but must not duplicate raw benchmark output.

### `configs/`

Frozen study decisions such as selected model families, concurrency grids,
SLOs, and topology assumptions. These are not global defaults.

### `hosts/`

Observed host facts and reference toolchain versions: OS, kernel, GPUs, driver,
container runtime, telemetry images, paths, and known limitations. Values are
snapshots and must include an observation date where practical.

### `campaigns/`

Small campaign pointer records only: campaign ID, status, external path or URI,
manifest hash when available, and relationships to the study. Raw results do
not belong here.

### `journal/`

Append-only, dated operational notes and decisions. Journal entries can record
what was observed, attempted, deferred, or learned. They are not normative
procedure and must link to authoritative artifacts where possible.

### `todos/`

Deferred work with an explicit trigger, entry gates, procedure references,
acceptance criteria, and completion/retirement instructions.

### `completed/`

Retired TODOs retained as audit records after their status, completion journal,
and result pointer are updated. Completed actions must not remain under
`todos/` as ambiguous standing work.

## Campaign artifacts

Raw and derived benchmark artifacts remain outside Git under the hierarchy in
`harness/5-formal-campaign/RULES.md`. On the authoritative workstation, local legacy/raw
evidence may be physically consolidated under ignored
`local-artifacts/<host>/`; this does not make it a Git artifact:

```text
<results-root>/<host>/<model-slug>/<revision>/<deployment-id>/<campaign-id>/
```

The committed study tree describes and points to campaigns; it does not mirror
the result tree. Host or campaign facts discovered during execution should be
written to the external manifest first, then summarized in the study journal if
they have lasting methodological value.

## Publication outputs

Tracked distilled publication JSON and source presentation assets belong under:

```text
results/<study-id>/publications/
```

Generated standalone HTML and static-site output may be consolidated under the
ignored repository-local path:

```text
published/<hardware-label>/
```

`published/` is a build/output location, not an authoritative Git input. The
site must be reproducible from tracked schemas, generator source, publication
JSON, source assets, and resolvable report inputs.

## Promotion rule

When a host-specific lesson is broadly applicable:

1. preserve the original observation in the study journal;
2. formulate a host-independent rule;
3. add that rule to the appropriate generic procedure or tool;
4. retain a link between the generic rule and its motivating study record.

Do not copy a machine-specific command, path, threshold, or workaround into the
generic procedure without stating its applicability and qualification method.
