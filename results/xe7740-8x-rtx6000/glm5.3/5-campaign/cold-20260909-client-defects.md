---
kind: record
status: open
date: 2026-09-10
device: xe7740-04
model: GLM-5.3
---

# Two defects in the cold client, found by the first mechanical benchmark step

Discovered while running `harness/3-deployment-raster/code/benchmark-step.py` for one
concurrency (C32) against the live container. Nothing was measured; the step recorded
`STEP_INCOMPLETE` and exited 1, which is the intended behaviour.

## 1. The corpus-capability check can never pass on a `current` build

`cold-prefill-client.py` `probe()`, the `needs_corpus` branch:

```python
if vocab == "current" and needs_corpus:
    missing += ["--input-file"]
```

`--input-file` is appended to the *missing* list without testing whether it is absent. The node's
AIPerf 0.13 build documents it (`aiperf profile --help`, line 165), so the client refuses a build
that is fully capable:

```
REFUSED: build looks like `current` but lacks: --input-file -- refusing to measure
         with an option that would be ignored
```

The check must be `if "--input-file" not in help_text`. Consequence of the bug as written: no
non-overlapping pool can ever be passed on a `current` build, and the fallback vocabulary emits
`--dataset-type synthetic --num-dataset-entries N` -- synthetic prompts, the exact condition
R-05-2 exists to prohibit. The probe refuses for the wrong reason and the dangerous path is the
one it leaves open.

## 2. Four refusal tests were passing for an unrelated reason

With the one-line fix applied, `test_missing_credential_in_environment_is_refused`,
`test_refusal_names_the_variable_to_set`, `test_build_without_a_pool_option_is_refused_when_a_book_is_requested`
and one sibling stop refusing (exit 0 instead of 2). Their premise -- a credential is always
required unless `--allow-anonymous` is declared -- has to be re-derived against a client whose
probe no longer fails first. The fix and the test rework must land together; the fix on its own
would leave the suite red, and silencing the tests would remove the only evidence that the
credential gate needs auditing.

## What the step runner did correctly

Preflight passed (`nvidia-smi` rows, `/proc/meminfo`, `/proc/stat`, sampler, client, gate, binary,
container identity, tokenizer, pool source), the sampler was started before the first request,
the plan was validated first, and on failure the runner wrote `STEP_INCOMPLETE` with the
collection defects and a non-zero exit. It never reached the point of producing a number.

---

## Correction, same day: defect 2 was wrong, and the cause was my own working tree

With the one-line probe fix applied to a clean checkout, all 11 client tests pass, including the
four named above. They were not passing for the wrong reason. The failures I attributed to them
came from an edited test file in my own working tree, whose tail I had mangled while inserting a
new test class -- the tests never ran as written. The conclusion "four refusal tests were passing
because the probe failed first" is withdrawn.

What survives: defect 1 was real and is fixed (absence is tested, not assumed); HEAD's probe
coverage was one-sided (refusal only), now extended with an accept-side case and a
neither-vocabulary case, with the fake help text derived from `CORE_FLAGS` rather than typed by
hand so it cannot drift from the client.

And the discipline point stands independent of the misdiagnosis: the runner never produced a
number. It recorded STEP_INCOMPLETE and exited non-zero both times, which is what the instrument
is for.

## Status of the accept-side probe test: not landed

An accept-side case (probe must ACCEPT a build that documents --input-file) was written and is
correct in isolation, but importing the client module inside the test process made four
subprocess-based refusal tests in the same file misbehave. Rather than ship a suite with
unexplained coupling, the test file was reverted and the probe fix landed alone, with the 11
existing client tests green.

The one-sidedness of the probe's test coverage is therefore still open, tracked here. The
probe's own behaviour is now right -- verified end-to-end against the real AIPerf 0.13 on
xe7740-04, which is the case that matters.
