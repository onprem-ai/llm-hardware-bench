---
kind: rule
step: cross
title: Pipeline chapters, ownership, budgets, gates
---

# Benchmark Pipeline

**Precedence.** This file owns **order, ownership, budgets, gates, and the naming
contract**. Each `harness/N-*/RULES.md` owns the **substance** of its chapter.
`PROCEDURE.md` was retired on 2026-09-06; every surviving section has an owner in a chapter file, and it
still holds the detail, and `harness/MOVED.md` maps old section numbers to rule IDs.

Rules have exactly one authoring home: the chapter where the rule **must be true**,
regardless of how many later chapters consume it. Everything else is a reference by rule
ID. A document that paraphrases a rule it does not own is a defect, because restatements
drift silently while verbatim copies fail loudly.

## Document kinds

| Kind | Lives in | May contain |
|---|---|---|
| **rule** | `PIPELINE.md` or `harness/N-*/RULES.md` | normative requirements, each with a stable rule ID |
| **record** | `results/<host>/<model>/campaigns/<id>/N-chapter/`, `journal/` | evidence. Append-only. Never normative |

Every markdown file declares front matter: `kind: rule | record` and `step: 1-7` (rules)
or `step: produced-by-N` (records). A file with no declaration is unowned and is failed
by `harness/6-accept-and-publish/code/validate_claims.py`.

## The seven chapters

| # | Chapter | Entry gate | Exit gate |
|---|---|---|---|
| 1 | Model qualification | repo ID + revision requested | pinned commit verified, load canary passed, provenance verdict recorded |
| 2 | Preflight conformance | model qualified | `preflight.json` = PASS or PASS_WITH_EXCEPTION, B0 captured, ambient bounded |
| 3 | Deployment raster | preflight passed | a candidate that survives with errors=0, and the winner's curve has **turned over** |
| 4 | Confirmation | raster winner | peak re-measured at protocol length, >=3 reps, spread within threshold |
| 5 | Formal campaign | profile frozen, spec validated | `RUNS_COMPLETE`, grid complete, B1-post captured |
| 6 | Accept and publish | campaign complete, gate passes | `ACCEPTANCE.json`, `claims.yaml` validated, publication + site built |
| 7 | Report and feedback | published | conclusions reviewed, pipeline rule changes filed |

## Sub-step ownership and budgets

One budget per step: **wall-clock minutes**. The machine is rented and running for the
whole campaign, so reasoning and measuring cost the same. The only distinction that
matters is critical path:

* **B (blocking)** - next measurement waits; charged in full.
* **O (off-path)** - can overlap measurement; ~0 against the campaign, so it **must be
  scheduled inside a measurement window**. A 9-15 min startup is dead time; filling it is
  the whole optimisation.

Waste metric is `gpu_busy / campaign_wall_clock`, target > 70%. Below that, steps are
serialised that should overlap. Never "minimise GPU minutes" - the box is paid either way.

Per-chapter sub-step budgets live in each chapter's `RULES.md` under **Sub-step budgets** - the chapter owns its own time. Cross-cutting rules and
the breach protocol stay here.
Two chapter-specific formulas live with their chapters: chapter 3's **45-minute
per-candidate cap** and chapter 5's **campaign estimate**.

### Budget breach protocol

1. Stop at the current boundary; write `BUDGET_EXCEEDED.md`: step, budget, elapsed, done,
   remaining.
2. If independent measurement work can proceed, start it - do not pay for an idle machine.
3. Escalate with the artefact. Never extend a budget from inside the step that breached it.
4. Resume must be idempotent: mechanical steps take a state directory and skip completed
   units, so restart-after-breach costs nothing.

An agentic step is bounded only if it has a **named artefact**. "Analyse the results"
drifts; "write `claims.yaml` naming the headline point and every comparator by ID" is
finishable, and drift is visible when the file is still empty at 80% of budget.

## Naming contract

Use these terms across journals, deployment contracts, publications and commit messages.

| Phase | Term | Meaning |
|---|---|---|
| Search | **deployment raster** | Mechanism-guided sequential search where each candidate is chosen from a causal model of the runtime and written so it can refute the current hypothesis |
| Decisive single test | **falsification** | A candidate whose purpose is to test a claim, with the refuting margin recorded |
| Peak finding | **turnover-based peak localisation** | Locating an optimum by measuring past it until throughput falls - not the maximum measured point |
| Final numbers | **protocol-grade confirmation** | Re-measurement at published window length, >=3 repetitions, before a figure is publishable |
| Outcome | **operating-point selection** | Choosing among points on the throughput / TTFT / ITL frontier, reported as a set |

The result of a raster is a **deployment profile** plus an **operating point**.

Do **not** call it: **grid search / full sweep** (implies enumeration); **autotuning**
(runtime-internal, e.g. kernel or attention autotune, which may be enabled *inside* a
profile); **Bayesian optimisation / hyperparameter tuning** (implies surrogate model and
maximised objective - none used); **"optimised parameters"** (implies a converged optimum
under a stated objective). The wording becomes legitimate only with a fractional factorial
design over high-impact factors and an objective of **SLO-constrained goodput**.

## Pipeline-level rules

These constrain the whole pipeline and are the only rules with no chapter owner.

* **R-PIPE-1 One owner per rule.** A rule lives in the chapter where it must be true. All
  other mentions cite its rule ID. Restating a rule you do not own is a defect.
* **R-PIPE-2 Comparators must resolve.** Every stated delta names a comparator ID in
  `results/<host>/comparators.json`; `harness/6-accept-and-publish/code/validate_claims.py` recomputes the delta and fails the
  build on mismatch or unresolvable ID. A remembered number is not a comparator. Verify
  the comparator *before* investigating any apparent gap, and be most suspicious of a
  comparator that flatters the hypothesis.
* **R-PIPE-3 Evidence, not markers.** Completion is the count of expected artifacts.
  A marker with zero artifacts is a null result. Terminal state is explicit:
  `COMPLETE`, `ABORTED`, `INVALID`, `DEFERRED`; retroactive markers must say so in the file.
* **R-PIPE-4 Archive, never delete.** Defective runs, discarded sweeps and superseded
  configs are kept with a reason file. Never publish a measurement from a defective run.
* **R-PIPE-5 Environment changes take a candidate boundary.** Stop between candidates,
  record before/after, and make the next chapter measurement a control re-measurement.
  Never reconfigure a background telemetry agent mid-candidate.
* **R-PIPE-6 Never tune inside a frozen campaign.** A mid-campaign improvement request is
  an escalation, not an action.
* **R-PIPE-7 Records are not instructions.** Journals and publications describe what
  happened; they never define procedure.

## Execution gate

One state machine for every model. It fails closed: with no recorded, explicitly approved freeze
contract there is no formal campaign - stop and ask, and never infer a grid from tuning points,
runtime ceilings, prior models, or report convenience.

```text
QUALIFY -> PRESENT FREEZE CONTRACT -> HUMAN APPROVAL -> FORMAL RUNS -> REPORT
```

Qualification tunes aggressively with short runs; any repetition count is still qualification, and
an unapproved formal grid is not a result. The freeze contract is exactly seven lines -
deployment(s) with HAProxy endpoint and backend count, profiles and token shapes, one shared global
concurrency grid for every primary profile, repetitions, `total = profiles x grid x repetitions`,
estimated duration, final deliverable. "Continue" or "finish overnight" is not approval of a missing
contract, and the workflow must not auto-transition across it. Formal runs use the approved grid
unchanged; profile-specific extra points are supplemental qualification evidence. A capacity-
affecting change is a new contract and a new campaign. Before reporting, verify every primary
profile holds every approved grid point and repetition, keep telemetry attached to its source
deployment, never mutate the contract after formal measurement starts, and never relabel
qualification as formal. One repetition is qualification; three is the normal formal minimum.

## What a study is for

Hardware serving capacity, not model ranking: chapter 2 owns the detail (**R-02-21**). Do not
compare results unless weights, quantization, engine, request shape, sampling, hardware and method
are all documented.

## Length budget

This file is capped at 200 lines. The original cap was 150 and was broken on the day
the extraction landed, because verification became part of the contract; a cap that is
silently exceeded is worse than a larger cap that is enforced. `check_repo.py` fails on
growth beyond the cap. Chapter `RULES.md` files are exempt: chapter 5 is 1200+ lines of
telemetry contract that cannot be compressed without losing a collection rule.

## Machine-checked invariants

`harness/check_repo.py` derives layout from the filesystem and fails on new violations; the
authoritative list of invariants is its source, and this document deliberately does not mirror
it -- a prose copy of a code-enforced list decays into a second, contradicting authority, which
is a defect already recorded once (R-07-8, R-07-9). What the checks are for: document `kind`
and single ownership, chapter rule-ID ranges with no ID defined twice, link and path
resolution, comparators resolving to real artifacts, tracked content confined to chapter and
`results/` directories, generated output ignored, no document repeating chapter content, and
published model labels undecorated (R-PIPE-9).

`make` at the repository root is the only cross-step entry point (`test`, `validate`,
`render-report-example`, `build-site`, `mock-e2e`); its path literals are checked for decay.

## Sources

External ancestor: [llmapibenchmark](https://github.com/Yoosu-L/llmapibenchmark). Most rules were
derived from measured failures on this hardware - see the journals under `results/xe7740-8x-rtx6000/journal/`.

---

---

## Mechanical and agentic work

R-PIPE-10: writing a measurement definition is agentic work; only executing it is mechanical.
A hand-written harness is authored code needing review, because a deterministic run of a wrong
definition returns the same wrong number reliably, and reproducibility reads as evidence.

R-PIPE-11: a prose rule that constrains a measurement is unenforced until code applies it to
the artifact and can invalidate a result. The prefill-cache case and its gates live in
`R-03-28` (harness) and `R-06-12` (independent re-check on the mirrored artifact).

- **R-PIPE-12** Capability is evidence, never a declaration: a panel is renderable only when the
  run artifacts and sampled metrics that back it exist, and a report whose panel has no backing
  evidence fails to build rather than rendering empty. Hand-authored capability flags in report
  configs are the defect this rule removes.

- **R-PIPE-13** A benchmark input may be versioned, under explicit caps: a measurement must be
  reproducible from declared inputs, so a prompt corpus lives in `harness/<chapter>/data/` with a
  `PROVENANCE.md` naming its producers, capped at 64 MiB per file and 100 MiB in total. Raw run
  evidence still belongs in the ignored evidence cache; the allowance is for inputs, never outputs.
