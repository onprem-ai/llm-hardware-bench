---
kind: record
produced_by: 7
title: Pipeline extraction and rule ownership
date: 2026-09-06
scope: process work, not a measurement campaign
---

# Pipeline extraction and rule ownership

Process journal entry. It records a repo restructure, so its evidence is commit history and
the behaviour of the checks that were built, not measured throughput. Where a number here is
weak, it says so.

## TL;DR

Procedure was duplicated as **concepts without owners**, not as copied text: verbatim overlap
between tracked docs measured near 0%, while `max_num_seqs` was restated in 13 documents,
warm-up/preflight in 10, repetitions and image digest in 9, idle baseline in 7. No numeric
contradictions were found - restatements drift silently rather than clashing, which is why the
problem was invisible until a remembered number was quoted as a comparator.

`PIPELINE.md` now owns chapter order, ownership, budgets, gates and the naming contract. Each
of seven chapters owns its rules with stable IDs. `PROCEDURE.md` went from 1879 to 240 lines
and is now a routing file.

## What was built

| Artifact | Purpose |
|---|---|
| `PIPELINE.md` | 7 chapters, mechanical vs agentic, one wall-clock budget per step, critical-path overlap, entry/exit gates, R-PIPE-1..7, naming contract, 200-line cap (enforced) |
| `harness/<n>-*/RULES.md` | one owner per rule; 90 rule IDs total (1:13, 2:20, 3:18, 4:9, 5:11, 6:9, 7:10) |
| `harness/MOVED.md` | 74 legacy sections mapped to rule IDs; journals citing `PROCEDURE §4.1` still resolve (that citation is now `R-02-12`) |
| `results/xe7740-8x-rtx6000/comparators.json` + `harness/6-accept-and-publish/code/validate_claims.py` | R-PIPE-2: registry stores artifact **addresses**, values resolved at check time, deltas recomputed |
| `harness/check_repo.py` | ownership, dangling/malformed links, lost sections, duplicate rule definitions, pointer drift, claims validation, comparator resolution, shrink ratchet - baselined so only new violations fail |
| `INDEX.md` | generated from the same classification table the checker enforces, so map and rule cannot disagree |
| `tools.yaml` | every tool declares its chapter and whether it is mechanical |

Rule IDs assigned: `{"1-model-qualification": 13, "2-preflight-conformance": 20, "3-deployment-raster": 18, "4-confirmation": 9, "5-formal-campaign": 11, "6-accept-and-publish": 9, "7-report-and-feedback": 10}`.

## Two kinds, no third bucket

Everything is either `kind: rule` (normative, owned by exactly one of the 7 chapters, chosen
as the step where it must be true regardless of how many later steps consume it) or
`kind: record` (output, append-only). An earlier draft had a cross-cutting "policy" category;
that was a dodge for "I have not decided who owns this". Pipeline-level rules live in
`PIPELINE.md` and nowhere else.

Pointer stubs are `kind: pointer` and capped at 30 lines by the checker, because a pointer that
grows has silently become a second owner of the thing it points at.

## Retired rather than deleted

`docs/HANDOFF.md`, `docs/REPOSITORY_LAYOUT.md` and the `results/` stub are in `docs/retired/`
with banners (`R-PIPE-4`). The `local-artifacts/xe7740-04/BENCHMARK_PROCEDURE.md` fork is an
**89% verbatim ancestor** of `PROCEDURE.md` but sits in a gitignored tree; it got a banner and
is excluded from instruction searches. Deleting the fork would have destroyed the only evidence
about how the procedure got forked in the first place.

## Errors made by this restructure, recorded as required

1. **The checker declared PASS on a broken link.** A reference rewrite I had run 40 minutes
   earlier produced a link whose target contained spaces - invalid markdown - and the target
   regex stopped at whitespace, so it resolved to something that existed. Found because I
   planted a defect to test the checker, which is the only reason I looked.
2. **The checker swept journals into "instruction docs"**, demanding front matter from 29
   records. Records are identified by path, not by a header.
3. **The shrink ratchet used `max()`**, so it could only ever ratchet upward - the opposite of
   its purpose - and printed a tightened number while storing the old loose one.
4. **Duplicate rule-ID detection could not see numeric IDs** (`R-02-7` style, which is what
   this repo now uses) and separately misread a line-wrapped prose mention as a definition.
5. **`git checkout` destroyed uncommitted work** mid-test, reverting the §7.1 move. The line
   count in the checker output (294 where the tree should have been 240) is what revealed it.
   Lesson recorded: the ratchet is also a regression tripwire for careless VCS use.
6. **`MOVED.md` cited rule IDs that did not exist.** The crosswalk claimed `R-RASTER-1..18`;
   chapter 3 was an unnumbered ordered list, so the mapping was aspirational. Chapter 3 now has
   literal `R-03-1..R-03-18` headings.

Five of these six were found by planting known-bad input and checking that the tool objected.
A validator that has never been shown a deliberate failure is not trusted, which is also the
lesson from `validate_claims.py`'s phantom-comparator test.

## Deliberately left undone

- `PROCEDURE.md` still holds the execution-gate preamble; deleting the file requires moving it
  into `PIPELINE.md`, which is at 192 of its 200-line cap.
- The chapter-mirrored campaign record directory (`5-campaign/`, `6-acceptance/`, ...) exists
  only for `6-acceptance/` of the GLM raster. Full layout is a chapter 5 task; until then a
  missing gate is a prose absence rather than an empty directory.
- `preflight.sh` as a single unified gate emitting `preflight.json` is specified in
  `R-02-11`/`R-02-14` but not implemented; `harness/2-preflight-conformance/code/check-host.sh` covers ambient load only.
- Chapter 5 carries two descriptions of the artifact layout (former §13 and `ARTIFACT_LAYOUT`)
  named in its own "remaining tasks" rather than being silently merged.
- Chapter 5 was moved **verbatim** with IDs assigned in move order, not rewritten. Some of it
  restates chapter 2 definitions; those duplicates are now named debt, not invisible drift.

## Relationship to the measurement work

The reason this happened today, in order: a +19.8% decode claim was drafted against a
comparator of 1111 tok/s that existed in no artifact; three designed experiments and roughly an
hour of eight-GPU time went into explaining a gap that had been invented; and the rules that
would have caught it had been re-derived from memory twice because they had no owner. `R-PIPE-2`
and `validate_claims.py` would have failed the build at authoring time. See
`2026-09-06-glm53-host-ram-floor-and-parameter-raster.md` §4.3 and §5.4.

## Two more self-errors, both of the same family (2026-09-07)

**A patch script that reports success unconditionally.** I "fixed" `tracked()` twice in a row and
printed a confirmation both times. Neither fix happened. `str.replace()` returns the original
string when the pattern does not match, and my script printed its success line after the replace
without testing that anything changed. In one case an `&&` chain short-circuited on a `grep` that
found nothing and the patch script never ran at all. Consequence: I believed the checker scanned
untracked documents for two rounds, and a planted root-level `kind: rule` document kept passing
clean, which is precisely the property the function was written to provide.

Fix in force: every edit in a patch script is now followed by an assertion re-reading the file for
the text it claims to have written, and multi-step shell chains avoid `&&` where a no-match is
expected.

**Silent parsing and absence look identical.** `tracked("*.md")` never saw an untracked file, and a
schema-1.4 AIPerf export parsed to nothing; both were indistinguishable from "there is nothing
here". Both are now explicit defects: the checker asks git for cached+others, and section 5.10's
R-05-12 forbids treating zero-values-parsed as a null result.

Also caught by the derived-ownership work: `INSTRUCTION` had become a hand-maintained table naming
two of seven chapters, still listing `docs/REPOSITORY_LAYOUT.md` four commits after `docs/` was
deleted. It is derived from the pipeline layout now, which is the whole argument for deriving
layout instead of declaring it — a declared list rots the moment the thing it describes moves, and
it rots *silently*, because the list itself keeps looking authoritative.

## PROCEDURE.md deleted: two documents describing one thing (2026-09-07)

You cannot have a governing document and a legacy procedure describing the same workflow; the
second one will be read as an escape hatch from the first. `PROCEDURE.md` had been shrunk to 240
lines, of which ~57 were tombstones and ~150 were live substance that had never had a home:

| Content | Owner now |
|---|---|
| Execution gate (QUALIFY → freeze contract → approval → formal → report), fail-closed | `PIPELINE.md` **Execution gate** |
| Freeze contract | merged into that same section — it only restated the gate |
| Study perspective | chapter 2 **R-02-21** |
| Fast qualification rules, raster-row fields, journal requirement | chapter 3 **R-03-23**, **R-03-24**, **R-03-25** |
| Sources | `PIPELINE.md` **Sources** |
| 17 `## n. … — moved` tombstones | `harness/MOVED.md`, which was always their proper home |

Adding the gate pushed `PIPELINE.md` to 231 lines against a 200 cap, so the cap did the job it
exists for: the per-chapter sub-step budget tables (35 rows) moved **into the seven chapter
files**, which is where a chapter's time should be owned anyway. `PIPELINE.md` is 178 lines and
keeps only cross-cutting rules: document kinds, chapter order, B/O accounting, waste metric, the
naming contract, the execution gate, pipeline-level rules and the cap.

Also removed: the shrinking-only ratchet on `PROCEDURE.md` and its `procedure_max_lines` baseline
field. It existed to force this migration, and leaving it behind would have been a machine-checked
rule about a file that no longer exists.

Two pre-existing errors surfaced by deletion rather than by reading:

- `results/xe7740-8x-rtx6000/DEPLOYMENTS.md` cited `PROCEDURE.md:343` and `:1423`. Both were already wrong —
  the file had gone from 1879 to 240 lines weeks earlier, so a citation that looked precise had
  long since pointed at nothing. Now names the owning chapter rule.
- `results/xe7740-8x-rtx6000/study.yaml` still declared `procedure: ../../PROCEDURE.md`.

Journals keep their `PROCEDURE.md` mentions: they are records of what was true, not pointers.

## A regression I shipped by not running the flag I changed (2026-09-07)

`check_repo.py --emit-index` was broken by the ownership-derivation refactor: it still referenced
`INSTRUCTION` and `RECORD_PREFIXES`, both of which I deleted. I verified that commit by running
`--full` and `--update-baseline`, which passed, and never ran `--emit-index` again — so a code path
I had edited went unexercised for several commits. Caught only because I regenerated the index for
the PROCEDURE retirement. Same lesson as R-PIPE-8, one level up: *exercise the thing you changed*,
not merely the thing that reports success.

