---
kind: rule
step: 6
title: Accept and publish rules
absorbs:
  - PROCEDURE.md §16 Acceptance and Data-Quality Checks
  - harness/6-accept-and-publish/RULES.md (published filename grammar)
  - the comparator/claims contract introduced 2026-09-06 (R-PIPE-2)
---

# Chapter 6 — Accept and publish

Pipeline order, budgets and gates: `PIPELINE.md`. One chapter does both jobs because they
share one input — the set of accepted runs — and splitting them is what let a *reporting*
claim survive on 2026-09-06 with no validator able to catch it: acceptance validated data,
not claims. Agent judgement still belongs here, but expressed as checkable data
(`claims.yaml`), not prose.

Consumed by chapter 7 and by the site; that does not transfer ownership (`R-PIPE-1`).

## What this chapter produces

| Artifact | Role |
|---|---|
| `6-acceptance/acceptance.json` | per-point verdicts and exclusions with reasons |
| `6-acceptance/claims.yaml` | every number this campaign intends to state, with its comparator |
| `publication.json` | the machine-readable published result set |
| `deployment.yaml` | the deployment profile the numbers belong to |

## Acceptance

### R-06-1 A result is valid only if all of the following hold

**Identity and topology** — the intended model and revision were served (`R-01-9`); the
requested topology was actually active; no unrelated GPU process consumed meaningful
resources.

**Workload** — actual input/output token counts match the profile; random prompts were used
for uncached tests; warm-up completed at the same concurrency; cache-hit behaviour is known.

**Resources** — error rate is reported; the load generator was not CPU- or network-bound; no
GPU thermal or power throttling occurred, or it is documented; KV capacity and peak use were
captured.

**Baselines** — B0 unloaded idle, B1-pre loaded idle and B1-post loaded idle captured as
separate intervals, or an unavailable baseline explicitly justified; baseline request
throughput and latency marked *not applicable*, never zero (definitions: `R-02-7`).

**Proxy boundary** — the benchmark targeted the load-balancer frontend including for a
one-backend deployment; frontend/backend byte and request counters changed under controlled
preflight and during measured work; directional proxy MiB/s and bytes per successful request
derived from exact measured-window counter deltas.

**Stability** — the test reached steady state.

**Evidence** — raw request and telemetry artifacts retained; a completion marker is
corroborated by the expected count of exported artifacts, and a marker with no artifacts is a
null result, not a pass (the acceptance-side form of `R-RASTER-17`).

**Comparability** — every reported figure states its measured-window length and repetition
count and is not compared against a figure from a different window class (`R-02-18`).

**Peaks** — a peak claim is supported by at least one measured point beyond it that is lower
(`R-RASTER-14`).

**Comparators** — any stated comparison against another campaign names artifact path, field,
statistic and repetition count, and the comparator was read from the artifact rather than
from memory or a secondary document (`R-PIPE-2`).

### R-06-2 Rerun a point when

Throughput differs materially between repetitions; GPU utilisation is unexpectedly low;
replicas are imbalanced; output lengths differ substantially; queue depth grows throughout
the entire run; cache-hit behaviour is unknown; telemetry has gaps; the server restarts,
OOMs, preempts, or rejects requests.

## Claims

### R-06-3 Nothing gets stated that does not recompute

Every number a campaign intends to publish is written to `claims.yaml` before it appears in
prose, and must pass:

```bash
python3 harness/6-accept-and-publish/code/validate_claims.py <campaign>/6-acceptance/claims.yaml
```

The validator enforces: every delta names a comparator `id` registered in `results/<host>/comparators.json`;
comparators store **artifact addresses, not values**, and are resolved from the artifact at
check time; the stated percentage is recomputed and must match within tolerance; a headline
value equals the median of its listed repetitions; ≥ 3 repetitions for protocol grade; a
claim may not supply its own comparator value; a claim listed in `prohibited_claims` may not
also be asserted; units must match between comparator and headline.

### R-06-4 Withdrawals are recorded in the same file

A claim that turns out to be unsupported moves to `prohibited_claims` with its reason, so the
next reader cannot re-derive it. Two mechanisms exist because both failure modes happened on
2026-09-06: a comparator that never existed (`glm53-raster.decode.vs-1111`), and a
cross-deployment, prefix-cached prefill comparison presented as an improvement.

### R-06-5 Provisional is a label, not a mood

A campaign on synthetic short prompts with prefix caching enabled, or on a raster deployment
that never went through chapter 5, is `provisional: true` with a reason. Publication requires
a chapter 5 campaign on the recorded workload identity (`R-02-10`). `provisional: true`
without `provisional_reason` fails validation.

### R-06-6 Publish the operating-point set, not one headline

If the throughput peak is bought with latency, publish the set: throughput, concurrency,
TTFT, ITL and the configuration for each point. Reporting only the peak hides the price
(measured on 2026-09-06: ITL moved 62 → 81 ms while TTFT went 0.9 s → 5.0 s across the same
curve).

## Publication

### R-06-7 Published filename grammar

```text
<hardware-model>--<ai-model>--<report-kind>.<extension>
```

Lowercase ASCII kebab-case within fields; `--` between semantic fields; hardware model or
platform family rather than an individual host (exact host stays in provenance); compact
public model name (repository/producer identity in provenance unless needed to distinguish
two reports of the same model); a stable kind such as `capacity-report`. Do **not** encode
mutable workflow labels (`complete`, `final`, `qualified`) in a published filename. Model
revision, campaign date, deployment ID, evidence classification and quantization live in the
report configuration. Quantization appears in the filename only when several quantizations of
one model are published side by side.

```text
xe7740--glm5.3--capacity-report.html
xe7740--glm5.3--fp8--capacity-report.html      # quantization-comparison case
```

### R-06-8 Accepted artifacts are superseded, never edited

An accepted run, campaign or publication is not modified to fix a claim. A superseding
artifact is created and the old one stays with its reason (`R-PIPE-4`). This is what makes
the 2026-09-06 corrections reconstructable: the phantom comparator, the withdrawn prefill
claim and the corrected +19.8% peak are all traceable, and a corrected headline that silently
replaced a wrong one would have destroyed the only evidence about how the error happened.

### R-06-9 Comparators you publish become comparators others use

Whatever lands in `publication.json` is now an address in `results/<host>/comparators.json` and will be
subtracted from someone else's work. Headlines must carry concurrency, statistic, unit and
source series, or the next campaign inherits an ambiguous comparator.

## Exit gate — entering chapter 7

- [ ] `acceptance.json` complete; every exclusion has a stated reason
- [ ] `claims.yaml` validates, including the comparator resolutions recorded at preflight
- [ ] provisional/publication grade labelled with reason (`R-06-5`)
- [ ] operating-point set published with latency, not a single number (`R-06-6`)
- [ ] published filenames follow the grammar and carry no workflow label (`R-06-7`)
- [ ] superseded artifacts retained with reasons (`R-06-8`)
- [ ] new published headlines registered as comparators with full addressing (`R-06-9`)

### R-06-10 A validity condition may be recorded as unevaluated only after enumerating every artifact beside the result

On 2026-09-07 an acceptance generator reported KV occupancy, preemption counts and load-generator
CPU as `not-evaluable`, reasoning that the campaign had never scraped `/metrics`. They had been
measured in all 84 runs. `server_metrics_export.json` sat **next to** every AIPerf export the whole
time - the generator read the app export and its own derived CSVs and never listed the run
directory. Understating evidence is not conservative: it suppressed findings (queue depth at
saturation, zero preemptions across the campaign, 54.8% MTP acceptance) and would have justified a
rerun to obtain data that already existed. Enumerate the directory, then judge.

### R-06-11 A published number that is a floor or a ceiling must be labelled where it is read, not only in a sidecar

`publication.json` must structurally carry a `prefill` headline. A maximum on the top grid point is
not a peak (`R-06-1` Peaks forbids the claim), but the schema has no slot for the distinction, so
the number reaches a reader looking exactly like a peak - and `R-06-9` then makes other campaigns
subtract it. Label it on every surface a reader can reach: publication notes, report config, and the
comparator registry `id` plus note (here `glm5.3-formal-20260907.prefill.floor-not-peak`). The
machine-check is `build_acceptance.py`'s `peaks.<profile>.claim_allowed`.

## Sources

`R-06-1`/`R-06-2` moved from `PROCEDURE.md` §16. `R-06-7` from `harness/6-accept-and-publish/RULES.md`.
`R-06-3`..`R-06-6`, `R-06-8`, `R-06-9` are new and come from one incident: a +19.8% claim
was drafted against a comparator (1111 output tok/s at C48) that existed in no artifact; the
assistant's own session data reproduced the real published headline (927.373) within
0.001–0.6%, meaning three designed experiments and roughly an hour of eight-GPU time were
spent chasing a fabricated gap. See
`results/xe7740-8x-rtx6000/journal/2026-09-06-glm53-host-ram-floor-and-parameter-raster.md` §4.3, §5.4
and §7.5b.

R-06-10/R-06-11 come from the 2026-09-07 formal campaign closeout: an acceptance file under-claimed three measurements present in `server_metrics_export.json` beside each result, and a grid-ceiling maximum had to be stopped from becoming a published peak.
R-06-10/R-06-11 come from the 2026-09-07 formal campaign closeout: an acceptance file under-claimed three measurements present in `server_metrics_export.json` beside each result, and a grid-ceiling maximum had to be stopped from becoming a published peak.
## Sub-step budgets

One budget per sub-step: **wall-clock minutes**. B = blocking, charged in full;
O = off-path, must be scheduled inside a measurement window. Rules and breach protocol: `PIPELINE.md`.

| Sub-step | Owner | Path | Budget |
|---|---|---|---|
| completeness gate (`harness/5-formal-campaign/code/finalize_campaign.py`) | mech | B | 5m |
| aggregate and normalise | mech | B | 10m |
| publication generation + schema/semantic validation | mech | B | 10m |
| claim and delta recomputation validator | mech | B | 5m |
| site build | mech | B | 10m |
| `claims.yaml`: headline, comparators by ID, provisional flags | **agent** | O | 30m |
| exception approval and disclosure wording | **agent** | O | 15m |

### R-06-12: Acceptance re-runs the cache gate on the mirrored artifact
Do not trust the harness's own pass line. Acceptance runs `cold_gate.py` against the
mirrored run directory and records the verdict. A prefill number whose verdict is not
`cold` is archived evidence with the verdict recorded here, and may never be rendered as a
reader-facing prefill figure (R-07-11).

### R-06-13: R-PIPE-9 case -- the label that renamed a model

`GLM-5.3 NVFP4 (full model)` was not a careful caption; it became the page `<h1>`, `<title>`
and dataset name of the report, renaming the model on every surface, and it was an agent's
hand written into a config with no check behind it. The campaign `id` and paths may carry a
date to stay unique; labels may not carry precision (`NVFP4`, `FP8`, `W4A4`), topology, graph
or speculative-decoding values, or parentheticals. `Flash`, `Next` and release dates are part
of product names and must pass -- tested from both directions, because a naming rule that
rejects real names gets ignored and then unenforced.

### R-06-13: Under-collection withholds acceptance, and therefore publication

`build_acceptance.py` runs chapter 3's collection contract against the campaign directory. Any
defect means acceptance is withheld (exit 3), `publication_permitted` is false and the defects
are recorded in `acceptance.json`. A campaign whose instrument under-collected cannot reach a
reader, so a hollow panel is not merely undesirable, it is unreachable through the pipeline.
There is no flag to waive this: a campaign that genuinely cannot sample a metric must extend the
instrument, not the exception list.

