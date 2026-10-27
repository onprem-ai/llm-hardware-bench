---
kind: rule
step: 4
title: Confirmation rules
absorbs:
  - PROCEDURE.md §7 Warm-Up and Run Policy, items 1-9 and 12
    (item 10 is chapter 5 capture; 11/13/14 are chapter 5 telemetry and qualification)
---

# Chapter 4 — Confirmation

Pipeline order, budgets and gates: `PIPELINE.md`. Chapter 3 finds a candidate; this chapter
decides whether a number is real enough to act on. It is a **grading** chapter: nearly every
rule here is about the difference between "measured once" and "known".

## What this chapter produces

Confirmed points with a stated grade (`exploratory`, `protocol`, `confirmed`), repetition
statistics, and a same-session control that calibrates the session against the published
baseline.

## Warm-up and interval

### R-04-1 Warm up at the measured concurrency and request shape

Per topology and concurrency: start and await readiness; record initial GPU memory and KV
capacity; warm up at the **same concurrency and request shape** as the measured run; allow a
15–30 s settling interval; run enough requests to maintain steady state. Warm-up at a
different concurrency is not warm-up for the point being measured.

### R-04-2 Interval length is chosen for the concurrency

Each measured interval ≥ 60–120 s; 2–5 minutes at low concurrency or when stable tail
percentiles are required; at high concurrency, observe multiple complete scheduling cycles.
Measured-window class is part of every comparison (`R-02-18`) — the offset between 60 s × 2
and 90 s × 3 regimes measured **+0.8% on one deployment and +3.1% on another**, larger than
most parameter effects.

### R-04-3 Order effects are designed out, not assumed away

Randomise concurrency order, or alternate ascending and descending, to reduce thermal and
order bias.

## Repetitions and grades

### R-04-4 Repetition counts define the grade

| Grade | Repetitions | Use |
|---|---|---|
| `exploratory` | 1–2, ≥ 60 s | raster ranking only; must be labelled exploratory wherever quoted |
| `protocol` | 3 × ≥ 90 s | comparison, acceptance input |
| `confirmed` | ≥ 5 × ≥ 90 s | a peak claim, or any number that will be published as a headline |

Automatically escalate to the extra repetitions when any of these hold: throughput spread
above 5%, abnormal latency spread, telemetry contamination, the point sits near peak
throughput, or it determines the recommended production concurrency.

### R-04-5 Report dispersion, not a single value

Report median and range plus mean and standard deviation across repetitions. A median quoted
without its spread hides whether the claim is real: on 2026-09-06 a decode point of
1012.71 tok/s with spread across three reps was quoted in chat as "over 1000" when only 2 of
3 repetitions were above the threshold.

### R-04-6 A median that straddles a threshold is not a claim

When a result is presented against a threshold (a round number, a published headline, a
previous best), the threshold must be cleared by the **repetitions**, not only by the median.
The later point that replaced it cleared 1000 in 3/3 repetitions with spread 1.96, which is
why it was publishable and the earlier one was not.

### R-04-7 Re-measure the control as the first measurement of a session or generation

After any environment change, the first measured point is the control again, so the generation
self-calibrates instead of inheriting a comparison made under different conditions
(`R-RASTER-16`). A same-session control on 2026-09-06 reproduced the published decode curve
within 2% at five concurrency points (C48 927.38 vs published 927.373), which is what made a
later +19.8% claim defensible — and what proved, two hours later, that a "16% discrepancy"
being investigated had been invented rather than measured.

### R-04-8 A peak needs turnover on the far side

A peak claim requires at least one measured point beyond it that is lower (`R-RASTER-14`).
Throughput still rising at the last concurrency tested is a truncated curve, not a peak: the
2026-09-06 raster reported 977.95 at C56 when the real peak sat at C56–C88 depending on
deployment, and later found values still rising at the admission ceiling.

### R-04-9 Grades do not mix inside one comparison

An exploratory point may not be compared against a protocol-grade point to imply the difference
is a parameter effect (`R-02-18`). Where a comparison must cross grades — for example a raster
point against a published formal campaign — the grade difference is stated next to the delta.

## Exit gate — entering chapter 5

- [ ] every point carries an explicit grade with repetition count and window length
- [ ] dispersion (range, mean, std) recorded, not only median
- [ ] threshold-crossing claims cleared by their repetitions (`R-04-6`)
- [ ] same-session control measured first and compared to the registered comparator
- [ ] every peak has a lower measured point beyond it (`R-04-8`)
- [ ] warm-up concurrency and request shape match the measured point

## Sources

`R-04-1`..`R-04-4` and `R-04-5` moved from `PROCEDURE.md` §7 items 1–9 and 12. `R-04-6`,
`R-04-7`, `R-04-9` are new; each came from the GLM-5.3 decode raster on XE7740-04 on
2026-09-06, where a straddling median, an uncalibrated session and a cross-grade comparison
were each one edit away from being reported as results. See
`results/xe7740-8x-rtx6000/journal/2026-09-06-glm53-host-ram-floor-and-parameter-raster.md` §4.3, §7.0a,
§7.5 and §7.7.

## Sub-step budgets

One budget per sub-step: **wall-clock minutes**. B = blocking, charged in full;
O = off-path, must be scheduled inside a measurement window. Rules and breach protocol: `PIPELINE.md`.

| Sub-step | Owner | Path | Budget |
|---|---|---|---|
| peak + turnover at protocol length (>=3, peak 5 reps) | mech | B | 55m |
| divergence adjudication (spread >5%, contamination) | **agent** | B | 15m |
