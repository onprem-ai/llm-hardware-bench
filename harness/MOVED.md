---
kind: rule
step: cross
title: Old PROCEDURE.md section to new home map
status: in-progress
---

# Where PROCEDURE.md sections went

Journals cite `PROCEDURE §4.1` and similar. Dissolving PROCEDURE.md without this map
silently breaks every citation, so the mapping is part of the migration, not an
afterthought. `chapter` names the owning chapter; `moved` is checked as each chapter
file receives the text.

| Old section | Chapter | Owner | Moved |
|---|---:|---|---|
| # Authority | 2 | harness/2-*/RULES.md | no |
| ## Study perspective | 2 | harness/2-*/RULES.md | no |
| ## Benchmark freeze contract | 2 | harness/2-*/RULES.md | no |
| ## Mandatory evolutionary deployment raster | 3 | harness/3-*/RULES.md | yes (ch.3) |
| ## Fast qualification rules | 3 | harness/3-*/RULES.md | no |
| # 1. Goals | 2 | harness/2-*/RULES.md | no |
| # 2. Terminology and Metric Definitions | 2 | harness/2-*/RULES.md | no |
| ## Generation/decode throughput | 2 | harness/2-*/RULES.md | no |
| ## Prefill throughput | 2 | harness/2-*/RULES.md | no |
| ## Total token throughput | 2 | harness/2-*/RULES.md | no |
| ## TTFT | 2 | harness/2-*/RULES.md | no |
| ## ITL / TPOT | 2 | harness/2-*/RULES.md | no |
| ## Request throughput | 2 | harness/2-*/RULES.md | no |
| ## Measurement scopes | 2 | harness/2-*/RULES.md | no |
| ## Goodput | 2 | harness/2-*/RULES.md | no |
| # 3. Required Test Record | 2 | harness/2-*/RULES.md | no |
| ## Model | 2 | harness/2-*/RULES.md | no |
| ## Serving stack | 2 | harness/2-*/RULES.md | no |
| ## Hardware | 2 | harness/2-*/RULES.md | no |
| ## Workload | 2 | harness/2-*/RULES.md | no |
| # 4. Preflight Checks | 2 | harness/2-*/RULES.md | no |
| ## 4.1 Background-load qualification | 2 | harness/2-*/RULES.md | no |
| # 5. Randomized Inputs and Cache Control | 2 | harness/2-*/RULES.md | no |
| # 6. Workload Profiles | 2 | harness/2-*/RULES.md | no |
| ## 6.1 Decode-focused profile | 2 | harness/2-*/RULES.md | no |
| ## 6.2 Prefill-focused profile | 2 | harness/2-*/RULES.md | no |
| ## 6.3 Balanced profile | 2 | harness/2-*/RULES.md | no |
| ## 6.4 Optional long-context qualification | 2 | harness/2-*/RULES.md | no |
| ## 6.5 Optional fixed token-shape compatibility profile | 2 | harness/2-*/RULES.md | no |
| # 7. Warm-Up and Run Policy | 2 | harness/2-*/RULES.md | no |
| ## 7.1 Mandatory idle baseline states | 2 | harness/2-*/RULES.md | no |
| # 8. Resource Telemetry | 5 | harness/5-*/RULES.md | no |
| ## 8.0 VictoriaMetrics correlation and delayed export | 5 | harness/5-*/RULES.md | no |
| ### Required per-run VictoriaMetrics snapshot | 5 | harness/5-*/RULES.md | no |
| ## 8.1 GPU metrics | 5 | harness/5-*/RULES.md | no |
| ## 8.2 CPU metrics | 5 | harness/5-*/RULES.md | no |
| ## 8.3 System RAM | 5 | harness/5-*/RULES.md | no |
| ## 8.4 Network and mandatory load-balancer boundary | 5 | harness/5-*/RULES.md | no |
| ## 8.5 Disk and filesystem | 5 | harness/5-*/RULES.md | no |
| ## 8.6 Server/runtime metrics | 5 | harness/5-*/RULES.md | no |
| ## 8.7 PCIe, collective, and NUMA fabric qualification | 5 | harness/5-*/RULES.md | no |
| ### 8.7.1 Static topology and negotiated-link record | 2 | harness/2-*/RULES.md | no |
| ### 8.7.2 Per-run passive fabric telemetry | 5 | harness/5-*/RULES.md | no |
| ### 8.7.3 Campaign-level active microbenchmarks | 2 | harness/2-*/RULES.md | no |
| ### 8.7.4 Fabric interpretation rules | 5 | harness/5-*/RULES.md | no |
| ## 8.8 Optional deep-compute and scheduler metrics | 5 | harness/5-*/RULES.md | no |
| # 9. KV-Cache Capacity and Constraint Analysis | 5 | harness/5-*/RULES.md | no |
| ## 9.1 Static campaign-level capacity record | 2 | harness/2-*/RULES.md | no |
| ## 9.2 Runtime KV metrics | 5 | harness/5-*/RULES.md | no |
| ## 9.3 Capacity calculations | 5 | harness/5-*/RULES.md | no |
| ## 9.4 Identifying KV constraints | 5 | harness/5-*/RULES.md | no |
| # 10. Deployment Topology Comparison | 5 | harness/5-*/RULES.md | no |
| ## Topology A: one GPU, one replica | 2 | harness/2-*/RULES.md | no |
| ## Topology B: four GPUs, four independent replicas | 2 | harness/2-*/RULES.md | no |
| ## Topology C: four GPUs, one distributed replica | 2 | harness/2-*/RULES.md | no |
| ## Topology D: two replicas across two GPUs each | 2 | harness/2-*/RULES.md | no |
| ## Fair comparison rules | 5 | harness/5-*/RULES.md | no |
| ## Concurrency interpretation | 5 | harness/5-*/RULES.md | no |
| ## Metrics for topology comparison | 5 | harness/5-*/RULES.md | no |
| ## Expected questions the comparison should answer | 5 | harness/5-*/RULES.md | no |
| # 11. Benchmark API Examples | 5 | harness/5-*/RULES.md | no |
| ## Start a benchmark | 2 | harness/2-*/RULES.md | no |
| ## Check results | 2 | harness/2-*/RULES.md | no |
| ## Delete a stuck job | 2 | harness/2-*/RULES.md | no |
| ## Inspect Kubernetes resources | 7 | harness/7-*/RULES.md | no |
| # 12. Manual TTFT Verification | 5 | harness/5-*/RULES.md | no |
| # 13. Result Artifacts | 6 | harness/6-*/RULES.md | no |
| # 14. Required Summary Table | 6 | harness/6-*/RULES.md | no |
| # 15. Charts | 6 | harness/6-*/RULES.md | no |
| ## Generation chart | 2 | harness/2-*/RULES.md | no |
| ## Prefill chart | 2 | harness/2-*/RULES.md | no |
| # 16. Acceptance and Data-Quality Checks | 6 | harness/6-*/RULES.md | no |
| # 17. Reporting Conclusions | 7 | harness/7-*/RULES.md | no |
| # Sources | 7 | harness/7-*/RULES.md | no |

## Rule ID crosswalk

| Former rule | New ID |
|---|---|
| Raster rules 1-12 (pre-existing) | R-RASTER-1 .. R-RASTER-12 |
| Raster rule 13 OFAT interaction probe | R-RASTER-13 |
| Raster rule 14 turnover before a peak | R-RASTER-14 |
| Raster rule 15 window-class comparability | R-RASTER-15 |
| Raster rule 16 re-baseline across env change | R-RASTER-16 |
| Raster rule 17 evidence over markers | R-RASTER-17 |
| Raster rule 18 falsified hypothesis is a finding | R-RASTER-18 |
| Raster rule 19 traceable comparators | R-PIPE-2 (promoted to pipeline level) |
| Naming contract | PIPELINE.md |
| Chapter budgets and breach protocol | PIPELINE.md (moved out of PROCEDURE) |

## Migrated so far

| Old text | New home | Status |
|---|---|---|
| Pipeline chapters / ownership / budgets / naming contract | `PIPELINE.md` | moved |
| Raster rules 1-19 + naming contract | `harness/3-deployment-raster/RULES.md` | moved (IDs R-RASTER-1..18; 19 promoted to R-PIPE-2) |
| `CLAUDE.md` "Hugging Face model downloads" steps 1-9 | `harness/1-model-qualification/RULES.md` R-01-1..R-01-8 | moved; CLAUDE.md keeps a pointer + the two unrecoverable rules |
| `harness/1-model-qualification/RULES.md` whole file | `harness/1-model-qualification/RULES.md` R-01-11..R-01-13 | moved; file is now `kind: pointer` |
| `PROCEDURE.md` §3 -> Model bullet list | `harness/1-model-qualification/RULES.md` R-01-9 | moved; section is now a pointer |
| `docs/HANDOFF.md` | `docs/retired/HANDOFF-2026-08.md` | retired as record, inbound refs repointed |

Chapters 2, 4, 5, 6, 7 are still scaffolds: their `RULES.md` names the sources to absorb
but does not yet hold the text. `harness/check_repo.py` keeps `PROCEDURE.md` from
growing while that work proceeds.

## Migrated (continued)

| Old text | New home | Status |
|---|---|---|
| `PROCEDURE.md` §1 Goals | `harness/2-preflight-conformance/RULES.md` R-02-1 | moved |
| `PROCEDURE.md` §2 Terminology and Metric Definitions | chapter 2 R-02-2..R-02-4 | moved |
| `harness/2-preflight-conformance/RULES.md` availability tiers, collection rules, scope semantics | chapter 2 R-02-5..R-02-8 | moved; file is now `kind: pointer` |
| `PROCEDURE.md` §4 Preflight Checks (13 items) | chapter 2 R-02-11 | moved |
| `PROCEDURE.md` §4.1 Background-load qualification | chapter 2 R-02-12 | moved; **§4.1 citations resolve here** |
| new in chapter 2 | R-02-9 grid freeze, R-02-10 workload identity, R-02-13 digest pinning, R-02-14 preflight comparator resolution, R-02-15..R-02-18 client traps | new |

Citation note: the most-cited legacy section, `PROCEDURE §4.1`, is now `R-02-12`.
`PROCEDURE.md` §4 remains as a pointer so journals citing §4.1 still land on the rule.

## Migrated (continued 2)

| Old text | New home | Status |
|---|---|---|
| `PROCEDURE.md` §16 Acceptance and Data-Quality Checks | `harness/6-accept-and-publish/RULES.md` R-06-1, R-06-2 | moved |
| `harness/6-accept-and-publish/RULES.md` | chapter 6 R-06-7 | moved; file is now `kind: pointer` |
| comparator/claims contract (R-PIPE-2) | chapter 6 R-06-3..R-06-6, R-06-8, R-06-9 | new, implemented by `harness/6-accept-and-publish/code/validate_claims.py` + `results/<host>/comparators.json` |

## Migrated (continued 3)

| Old text | New home | Status |
|---|---|---|
| `PROCEDURE.md` §14 Required Summary Table | chapter 7 R-07-5 | moved (full field list moved) |
| `PROCEDURE.md` §15 Charts | chapter 7 R-07-6 | moved |
| `PROCEDURE.md` §17 Reporting Conclusions | chapter 7 R-07-7, R-07-8 | moved |
| `harness/7-report-and-feedback/RULES.md` whole file | chapter 7 R-07-1..R-07-4 | moved; file is now `kind: pointer` |
| `harness/7-report-and-feedback/REPORT_SPEC.md` | stays as the reader-facing spec, now owned by step 7 | reassigned |
| new in chapter 7 | R-07-9 report falsified hypotheses, R-07-10 PROCEDURE feedback is a deliverable | new |
| `PROCEDURE.md` §16 + `harness/6-accept-and-publish/RULES.md` | chapter 6 R-06-1..R-06-9 | moved (see previous table) |

## Migrated (continued 4)

| Old text | New home | Status |
|---|---|---|
| `PROCEDURE.md` §7 items 1-9, 12 | `harness/4-confirmation/RULES.md` R-04-1..R-04-5 | moved |
| new in chapter 4 | R-04-6 straddling median, R-04-7 control-first, R-04-9 grade non-mixing | new |
| `PROCEDURE.md` §7 item 10 + §7.1 | stays here until chapter 5 absorbs it (definitions already at R-02-7) | pending |

## Chapter 5 mapping (mechanical move, text preserved verbatim)

| Former section | New rule |
|---|---|
| §3 Required Test Record | R-05-1 |
| §5 Randomized Inputs and Cache Control | R-05-2 |
| §6 Workload Profiles | R-05-3 |
| §8 Resource Telemetry | R-05-4 |
| §9 KV-Cache Capacity and Constraint Analysis | R-05-5 |
| §10 Deployment Topology Comparison | R-05-6 |
| §11 Benchmark API Examples | R-05-7 |
| §12 Manual TTFT Verification | R-05-8 |
| §13 Result Artifacts | R-05-9 |

## docs/ removed 2026-09-06 — what its files became

The pointer stubs existed so pre-extraction citations kept resolving. Once every inbound
reference was rewritten to the owning chapter, the stubs were pure indirection, so they were
deleted and this table became the redirect. Nothing in `docs/` was ever deleted from history.

| Old path | Now owned by |
|---|---|
| `docs/METRICS.md` | `harness/2-preflight-conformance/RULES.md` R-02-5..R-02-8 |
| `docs/PREREQUISITES.md` | `harness/2-preflight-conformance/RULES.md` R-02-19 |
| `docs/CONCURRENCY_GRID_DESIGN.md` | `harness/2-preflight-conformance/RULES.md` R-02-20 |
| `docs/INTEGRITY_POLICY.md` | `harness/1-model-qualification/RULES.md` R-01-11..R-01-13 |
| `docs/ARTIFACT_LAYOUT.md` | `harness/5-formal-campaign/RULES.md` R-05-10 |
| `docs/REPORTING.md` | `harness/7-report-and-feedback/RULES.md` R-07-1..R-07-4 |
| `docs/REPOSITORY_LAYOUT.md` | superseded by derived ownership (`harness/check_repo.py`); copy in `results/xe7740-8x-rtx6000/journal/retired/` |
| `docs/HANDOFF.md` | retired copy in `results/xe7740-8x-rtx6000/journal/retired/` |
| `results/README.md` | retired copy in `results/xe7740-8x-rtx6000/journal/retired/` |

Placeholder directories `published/` (renamed `website/` on 2026-09-07), `results/`, `tests/` and `local-artifacts/` lost their
`.gitignore`/`.gitkeep` seeds and are now created on demand: `build-site.sh` does
`mkdir -p`, `check-host.sh` creates its own output root, and `run_campaign.py` has **no
default** `--results-root`, which is proof `results/` was never used. The ignore rules for
generated output live in the root `.gitignore`; the negations that existed only to keep those
stubs tracked were removed.

## Checker self-errors found while enforcing the ratchet

Recorded here rather than in `PIPELINE.md` because the cap on that file is the point of it.

- Swept journals into instruction docs, because it used `max()` as the ratchet and so could only
  ever grow; and it read only `git ls-files`, missing untracked docs.
- Declared PASS while a link mangled by an automated reference rewrite was still broken: a
  multi-word link target is invalid markdown. That class is reported explicitly now.
- The size ceiling used the deliberately untracked-inclusive file list, so it flagged the entire
  ignored evidence cache on every run; it must judge only what git tracks.
- Its document-owner table named only two of seven chapters and still listed `docs/`, so it missed
  a chapter being overwritten with another chapter's text and passed a copied chapter outright.
  Ownership is derived from the pipeline layout now.
- `tracked("*.md")` skipped its untracked branch because `"*.md"` is not a directory, so newly
  written documents were never checked until they were committed - the exact case the function
  existed for. It now asks git for `--cached --others --exclude-standard`.

## PROCEDURE.md retired 2026-09-06 — final disposition

The file is deleted. Everything it still held went somewhere with an owner; this table is that
somewhere, and it is the reason the deletion is not a loss.

| Remaining PROCEDURE section | Where it lives now |
|---|---|
| Intro + `## Authority` | deleted: `PIPELINE.md` governs, and a second authority statement was the conflict this removal ends |
| `## Mandatory execution gate` | `PIPELINE.md` **Execution gate** (cross-step, compressed; fail-closed wording preserved) |
| `### Study perspective` | `harness/2-preflight-conformance/RULES.md` **R-02-21** |
| `### Benchmark freeze contract` | `PIPELINE.md` **Execution gate** (it restated the gate; merged rather than duplicated) |
| `### Mandatory evolutionary deployment raster` | pointer deleted; chapter 3 **R-03-1..25**. The pointer's `R-RASTER-1..19` naming was stale — those are the `R-03-*` IDs |
| `### Fast qualification rules` | `harness/3-deployment-raster/RULES.md` **R-03-23**, **R-03-24**, **R-03-25** |
| `## 1. Goals` … `## 17. Reporting Conclusions` (tombstones) | this file; content owners named in the table above it |
| `## Sources` | `PIPELINE.md` **Sources** |

Two citations into the deleted file were also stale *before* the deletion and are corrected here
rather than left dangling:

- `results/xe7740-8x-rtx6000/DEPLOYMENTS.md` cited `PROCEDURE.md:343` and `PROCEDURE.md:1423`. Those line
  numbers were already meaningless once the file shrank from 1879 to 240 lines, so a pointer that
  looked precise had been wrong for some time. The requirement is chapter 3's launch-record rule.
- `results/xe7740-8x-rtx6000/study.yaml` pointed `procedure:` at `../../PROCEDURE.md`; it now names
  `PIPELINE.md`.

Journals under `results/xe7740-8x-rtx6000/journal/` keep their `PROCEDURE.md` mentions as written, because they
are records of what was true when written. Only live pointers were repointed.

## tools.yaml removed 2026-09-07

A hand-maintained inventory of "every tool, by step". Nothing read it - the only citation was a
journal line describing the file itself - and every fact in it was already answered by
`ls harness/*/code`. It lost the head-to-head against the `Makefile`: commands that run and are
checked for path decay beat a list that must be remembered.

`results/<host>/comparators.json` was considered for the same treatment and **kept**, by test rather than by
argument: with it moved aside, `validate_claims.py` cannot run at all (`FileNotFoundError`), so the
R-PIPE-2 rule - a comparator is an artifact address, never a remembered number - has no
implementation without it. It is also the marker several scripts walk up to when locating the repo
root. It is state with no other home, which is the test the other root files failed.

