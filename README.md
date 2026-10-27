---
kind: rule
step: cross
title: Repository front door
---

# LLM Inference Hardware Bench

Independent, reproducible benchmarks of LLM serving capacity on bare-metal GPU
servers: the measurements, the pipeline that produced them, and the static site
that publishes them.

> **How to proceed: see [`PIPELINE.md`](PIPELINE.md).** It owns chapter order,
> ownership, budgets, gates and the execution gate. Substance lives in the
> chapter files `harness/<n>-*/RULES.md`.

## What is measured

Prefill and decode throughput against closed-loop global concurrency,
TTFT/ITL latency percentiles, energy per token, KV-cache and scheduler
behavior, speculative-decoding acceptance, and host/fabric telemetry —
**cold series only**: every measured run is served by a freshly launched
engine, so no number silently benefits from a warm cache. Each operating
point is repeated; spreads and rerun triggers are recorded, not averaged away.

## Studies

| Host | Models | Status |
|---|---|---|
| Dell PowerEdge XE7740 — 8× RTX PRO 6000 Blackwell 96 GB | GLM-5.3 (NVFP4, TP8) · GLM-5.3 Flash (NVFP4, 2×TP4 + HAProxy) · Qwen3.8-Flash-Next (NVFP4, 4×TP2 + HAProxy) · DeepSeek-V4-Flash (FP8, 4×TP2 + HAProxy) | published |

Every published model has a page on the generated site with a **Reproduce
section** (pinned container, model revision, verbatim launch commands,
measurement client, corpus) and a **Procedure journal** (what was tried, what
failed, what worked — distilled from the study journals).

## The site

```bash
make build-site        # validates inputs, builds, writes website/site/
python3 -m http.server 4321 --directory website/site --bind 127.0.0.1
open http://127.0.0.1:4321/benchmarks/
```

Publications are the only per-model input; every chart, table and headline on
a page is rendered from the publication's embedded, schema-validated
normalized data, and the source files are published beside each page as
downloadable receipts.

## Repository map

- [`PIPELINE.md`](PIPELINE.md) — the governing document (chapters, gates, budgets)
- `harness/<n>-*/` — the seven chapters: rules, code, tests, schemas
- `results/<host>/<model>/` — spec, campaign evidence summaries, acceptance,
  reports, and `publication.json` per published benchmark
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to work in this repository

## Quickstart

```bash
make test                # 92 tests across the pipeline chapters
make validate            # schema-validate every study spec and example
make mock-e2e            # end-to-end pipeline exercise on a mock campaign
python3 harness/check_repo.py   # the repository checks itself
```

## Provenance

This repository was born on 2026-09-20 as a single commit re-boxing the private
working repository: the instrument became `harness/`, the per-host measurements
became `results/` with the host named in the directory (`<host>-<gpus>`). All
pre-publication history — the working journals, the history rewrite of
2026-09-18, and every intermediate commit — stays in that private archive and
is intentionally not part of this history. Nothing measured was altered by the
re-boxing; paths and pointers were.

## Data and integrity policy

- A few MB of aggregated or selected data per study, **no raw payloads**: the
  corpora are reproducible from recorded provenance, work-ID lists and the
  versioned fetchers in this repository.
- Gaps are declared in-band, never omitted: an unpinned revision, an
  unrecorded client version, an uncollected metric is named on the page that
  needs it, with the reason.
- Falsified and withdrawn hypotheses stay in the record.
- Journals and study records describe the LLM and the benchmark only; access
  infrastructure never appears in them (enforced by `check_repo` rule 10).

## License

Apache-2.0, for code and data together. See [`LICENSE`](LICENSE).
