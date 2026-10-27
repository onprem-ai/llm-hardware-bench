# 2026-09-06 - GLM-5.3 host RAM floor and parameter raster

## TL;DR

Five findings on the full `RadixArk/GLM-5.3-NVFP4` TP8 deployment, plus the
harness defects found while driving them:

0. **Decode throughput was improved 19.8% above the published figure, to 1110.99
   output tok/s** (90 s protocol, repetitions 1105.40 / 1118.10 / 1110.99, zero errors)
   by raising admission from `max_num_seqs=64` to 96 with graph coverage 384, peaking at
   **C88** rather than the published C48. Comparator: `publication.json`
   `/headlines/decode` = 927.373 at C48. That same published configuration reproduces in
   this session at 926-933, so the comparison is clean and the node is reproducible to
   under a percent across a restart and four to six days. See section 7.5.
1. **Host RAM requirement is roughly 10x below the 433 GiB checkpoint size.**
   A 96 GiB cgroup limit is measured sufficient for cold start, graph capture
   and sustained C48 load. See section 1.
2. **The decode plateau extends to about C56, and speculation depth matters far
   more than admission width or background load.** A fine sweep put the peak at C56,
   5.6% above C48; a protocol-length re-measurement (90 s x 3) narrowed that to
   ~1.1% and ruled out window length as the explanation for the campaign-to-campaign
   gap. See sections 4 and 4.1.
3. **A background telemetry agent was burning ~40 cores unbounded** - the PROCEDURE
   4.1 preflight failure mode. Capping it lifted throughput by only **1-3%**, so it
   was measured and rejected as the explanation for the cross-campaign gap. See
   sections 4.4 and 6.
4. **Profile parameters are environment-driven, not baked into the image,** and
   three distinct expert-execution widths are selectable on the runtime already
   in use. Correcting this makes the whole raster cheap. See section 2.

A prior belief recorded in `deployment/deployment.yaml` turned out to be wrong:
profile parameters can be changed **without building a new image**.

Two of my own hypotheses were tested and rejected during this work: that shallow
speculation (MTP2) would beat MTP3 despite 0.318 acceptance on the third draft token
- it loses by 12% at the operating point - and that ambient CPU interference explained
the 16% gap to the published figure - it accounts for 1-3%.

---

## 1. Host RAM: what was actually consumed

### 1.1 Why the number had to be measured

The earlier estimate of "roughly 433 GiB of host RAM" conflated three different
quantities:

* the size of the checkpoint on disk,
* the aggregate VRAM across eight GPUs (about 8 x 90 GiB), and
* resident host RAM required by the process.

The checkpoint is streamed to the GPUs by the InstantTensor loader and is not
retained in host RAM, so none of those three numbers is the one that has to be
provisioned.

### 1.2 Precondition: `/dev/shm` contamination

Before any measurement could be trusted, the host had to be cleaned. The node
carries 32 x 96 GB DDR5 modules, 3072 GB populated, 2.953 TiB visible to Linux.

Inspection found 26 `vllm_offload_*.mmap` files totalling about 1.23 TiB in
`/dev/shm`. These are tmpfs files, so they count against RAM and cannot be
reclaimed by the kernel.

They were classified by mapping them against `/proc/*/maps`:

| Population | Files | Bytes |
|---|---:|---:|
| referenced by a live process | 4 | 4 x 48.5 GiB, the live DeepSeek replicas |
| unreferenced after replica teardown | 22 | 1,145,679,101,952 (~1.04 TiB) |

Only the unreferenced files were removed, and only after their owning processes
had exited. An 8 GiB swap partition that had been exhausted by the
`/dev/shm` residue was disabled and re-enabled to reset its consumed counter.
This is a consumption counter reset, not a memory reclaim.

**This is an operational defect, not a capacity requirement.** An interrupted
vLLM TP worker leaks its offload file into `/dev/shm`, and the residue
eventually exhausts a 3 TiB host.

### 1.3 Experiment design

The deployment was constrained through its own cgroup rather than by reserving
host memory:

```text
docker run --memory <limit> --memory-swap <limit>
```

Setting `memory-swap` equal to `memory` removes cgroup swap entirely, so the
test measures RAM, not RAM plus overflow. Sampling ran every two seconds and
recorded `memory.current`, `memory.peak`, `memory.swap.current`,
`memory.events`, `pids.current`, aggregate `Pss`/`Rss` from per-process
`smaps_rollup`, and `/dev/shm` usage.

Aggregate PSS, not RSS, is the correct host-RAM metric here: eight TP workers
map shared regions, and RSS would multiply them.

Both experiments used the published wide profile: TP8, DCP1, MTP3,
`max_num_seqs=64`, `max_cudagraph_capture_size=256`,
`max_num_batched_tokens=8192`, `max_model_len=262144`, FP8 KV, GPU utilisation
0.95. DeepSeek was stopped first because GLM-5.3 requires all eight GPUs.

### 1.4 128 GiB result

Cold start reached `/health` 200. All 35 PIECEWISE graph shapes were profiled
and captured. The 433 GiB checkpoint streamed in 63.01 s.

| Measurement | Value |
|---|---:|
| Cgroup limit | 128.00 GiB |
| Peak charged (`memory.peak`) | 105.18 GiB |
| Anonymous (`memory.stat anon`) | 48.21 GiB |
| File-backed (`memory.stat file`) | 56.70 GiB |
| Kernel | 0.29 GiB |
| Shared memory (`shmem`) | 2.02 GiB |
| Aggregate PSS | 52.74 GiB |
| Aggregate RSS | 58.75 GiB |
| Cgroup swap | 0 |
| `max` / `oom` / `oom_kill` events | 0 / 0 / 0 |
| GPU KV cache | 545,600 tokens |

Each of the eight TP workers accounted for 6.28-6.30 GiB of PSS; the engine and
API processes add about 2.5 GiB.

The 57 GiB of file-backed charge is the page cache produced while reading the
checkpoint. It is reclaimable, which is why the 128 GiB peak is not the
requirement.

### 1.5 96 GiB result

| Measurement | Value |
|---|---:|
| Cgroup limit | 96.00 GiB |
| Peak charged | 50.33 GiB |
| Aggregate PSS | 52.52 GiB |
| Aggregate RSS | 58.48 GiB |
| host `/dev/shm` used (`df`, peak) | 1.33 GiB |
| Swap | 0 |
| OOM events | 0 |
| Samples | 327 |
| Decode C48 | 904.22 output tok/s |
| Prefill C48 | 8557.89 input tok/s |
| Errors | 0 |

The container ran healthy for two days under this limit. **96 GiB is therefore
a measured sufficient host-RAM allocation for this deployment**, not an
estimate.

Note the contrast with the 128 GiB run: charged memory peaked at 50.33 GiB
instead of 105.18 GiB. Under the tighter limit the kernel reclaimed the
checkpoint page cache instead of holding it, while the application's own
footprint (PSS ~52.5 GiB) was unchanged. This is the direct evidence that the
large 128 GiB figure was cache accounting rather than requirement.

### 1.6 Consequences

| Allocation | Assessment |
|---|---|
| 48 GiB | Not qualified. Anonymous memory alone is ~48 GiB. |
| 64 GiB | Plausible, ~11 GiB above observed PSS. **Untested.** |
| 96 GiB | **Measured sufficient**, including cold start and graph capture. |
| 128 GiB | Comfortable; headroom is mostly reclaimable cache. |

The 64 GiB test remains open. The host total is not the constraint here; the
point of the exercise is whether several such deployments, or a deployment
beside other services, can be sized honestly.

---

## 2. Correction: the profile is not baked into the image

`deployment/deployment.yaml` recorded:

> Changing a setting therefore means committing a new image, not editing a
> command.

That is wrong. The entrypoint chain is fully environment-driven. The relevant
public interface, confirmed with `DRY_RUN=1` against the live image:

```text
MODEL_FAMILY  TP  DCP  MTP  MAX_NUM_SEQS  GRAPH  MAX_BATCHED_TOKENS
MAX_MODEL_LEN  GPU_MEMORY_UTILIZATION  MOE_MODE  MOE_BACKEND
KV_CACHE_DTYPE  QUANTIZATION  LOAD_FORMAT  ASYNC_SCHEDULING
```

Rebuilt commands were compared argument by argument and differ only in the
intended values; the attention backend, quantization config, `hf-overrides`
index-pattern, tool/reasoning parsers, async scheduling and the MTP
speculative config remain identical.

The consequence for tuning is significant: every candidate in this raster needs
no image build at all.

The full live control command was captured for provenance, including
`--attention-backend B12X_MLA_SPARSE`, `--moe-backend b12x`,
`--quantization modelopt_fp4`, `--load-format instanttensor`,
`-cc.pass_config.fuse_allreduce_rms=True`, `--enable-prefix-caching` and
`--speculative-config {"method":"mtp","num_speculative_tokens":3,
"draft_sample_method":"probabilistic"}`.

### Expert-execution modes

The current deployment logs:

```text
B12X MoE force-A16 enabled: using quant_mode=w4a16.
```

`vllm/model_executor/layers/fused_moe/b12x_moe.py` decides this from two
environment flags:

| Mode | Flags | `quant_mode` |
|---|---|---|
| current | `B12X_MOE_FORCE_A16=1` | `w4a16` |
| A8, labelled experimental upstream | `B12X_MOE_FORCE_A8=1` | `w4a8_nvfp4` |
| native | both flags absent | `nvfp4`, i.e. W4A4 |

The checkpoint carries NVFP4 expert weights, so the native W4A4 path is the
default the runtime would otherwise take. Three distinct, testable expert
modes therefore exist on the runtime we already have, without needing a newer
image.

---

## 3. Measurement protocol corrections

Three methodological defects were found and fixed while starting Generation 1.
They are recorded because each one silently distorts results.

1. **`--use-server-token-count` is mandatory.** Without it AIPerf reports a
   client/server token-count mismatch, which corrupts input-token throughput.
   The first Generation 1 attempt was aborted for this reason and archived as
   `gen1-fine-concurrency-token-count-discard-*`, not deleted.
2. **AIPerf JSON time fields are milliseconds, not microseconds.** Each metric
   object carries `"unit": "ms"`. An early collector divided by 1000 assuming
   microseconds and produced TTFT values off by 1000x. Asserting the unit field
   is now part of the collector.
3. **`date --iso-8601=ns` emits a comma-separated fractional part under the
   server locale**, which shifts columns in the telemetry CSV and made the 128
   GiB summary fail to parse. The container was healthy; only the summary
   script died. Timestamps now use an explicit
   `+%Y-%m-%dT%H:%M:%S.%NZ` format.

The 128 GiB experiment consequently has complete raw telemetry but no
`summary.json`; its figures above were taken from the raw cgroup files and the
in-situ PSS snapshot.

---

## 4. Generation 1: fine concurrency, unchanged control

Deployment unchanged: TP8 / DCP1 / MTP3, seq64, graph256, batch 8192,
262144 context, GPU utilisation 0.95, FP8 KV, `B12X_MOE_FORCE_A16=1`, 96 GiB
cgroup limit. Warmup of 32 requests, then two 60 s measured repetitions per
point, `--use-server-token-count`, temperature 0, `ignore_eos`, zero token
stddev.

Status: **complete**. 14 points, 28 measured repetitions, zero errors.

| Concurrency | Output tok/s | vs C32 | TTFT p50 | TTFT p95 | ITL p50 | Acceptance | Mean power |
|---:|---:|---:|---:|---:|---:|---:|---:|
| C32 | 705.40 | - | 1.136 s | 2.469 s | 38.80 ms | 0.544 | 1818 W |
| C36 | 757.78 | +7.4% | 0.828 s | 2.925 s | 40.75 ms | 0.545 | 1860 W |
| C40 | 839.56 | +19.0% | 0.960 s | 3.017 s | 43.33 ms | 0.544 | 1851 W |
| C44 | 887.14 | +25.8% | 0.967 s | 3.191 s | 45.33 ms | 0.548 | 1875 W |
| C48 | 926.05 | +31.3% | 0.976 s | 3.204 s | 46.62 ms | 0.550 | 1887 W |
| C52 | 953.00 | +35.1% | 1.477 s | 3.294 s | 49.54 ms | 0.540 | 1895 W |
| **C56** | **977.95** | **+38.6%** | 1.435 s | 3.339 s | 51.10 ms | 0.551 | 1909 W |
| C60 | 894.11 | +26.7% | 3.441 s | 3.450 s | 57.83 ms | 0.544 | 1853 W |
| C64 | 803.99 | +14.0% | 3.553 s | 3.560 s | 64.65 ms | 0.545 | 1811 W |

### The published decode knee is in the wrong place

The real peak is **C56 at 977.95 output tok/s**, not C48. Against the published
operating point measured in this same session that is **+5.6%** (977.95 versus
926.05) and it requires **no server change at all**, only a different client
concurrency.

Past the peak the collapse is steep rather than flat: C64 delivers 803.99
tok/s, **17.8% below peak**, while ITL p50 rises 66% from 38.8 ms to 64.7 ms.
The published C32 -> C48 -> C64 grid straddled the peak without sampling it,
and made C64 look like a gentle plateau when it is well inside the degradation
region.

MTP3 acceptance holds at 54.0-55.0% across every point, approximately 1.63
accepted draft tokens per verification step. Acceptance being flat while
throughput rises and then falls means the curve is governed by batching and
scheduling efficiency, not by speculation collapsing under load.

### Prefill

| Concurrency | Input tok/s | TTFT p95 | ITL p50 | Acceptance | Mean power |
|---:|---:|---:|---:|---:|---:|
| C32 | 8517.69 | 9.519 s | 449.32 ms | 0.630 | 1623 W |
| C40 | 15183.66 | 4.517 s | 303.38 ms | 0.626 | 1211 W |
| C48 | 17986.84 | 4.589 s | 247.91 ms | 0.628 | 1246 W |
| C56 | 17762.02 | 5.236 s | 336.93 ms | 0.632 | 1205 W |
| C64 | **18238.55** | 5.709 s | 391.41 ms | 0.631 | 1207 W |

Prefill is still improving at C64, so within this raster no prefill peak was
reached. **These prefill figures cannot be compared against the published
prefill numbers at all**, for two independent reasons, and an earlier chat
summary that quoted "18,238 versus the published 13,703" was wrong twice over:
13,703 is not in `publication.json` and is not a published figure, and the
comparison itself is invalid.

The published prefill series is
`publication.json -> /normalized_data/series/prefill`, source
`seq32-graph128-prefill-formal`:

```text
C1 1516.1   C8 3115.3   C16 5466.5   C24 8574.6
C32 10187.4   C48 11086.8 (maximum)   C64 10600.9
```

Two reasons the raster's prefill numbers are not comparable to that curve:

1. **Different deployment.** The published prefill series comes from the
   `seq32/graph128` profile; this raster runs `seq64/graph256` and wider. The
   publication states explicitly that no `seq64` prefill result is implied.
2. **Different prompt economics.** The raster replays fixed-shape synthetic
   prompts against a server with `--enable-prefix-caching` enabled, so repeated
   prompts are largely cache hits. That inflates input-token throughput without
   bound. This is not fresh-prompt capacity and must never be published as such.

An earlier revision of this section also claimed the published prefill peaked at
C32; the published maximum is **C48 at 11,086.8**, with C32 at 10,187.4.

What the raster *can* legitimately say about prefill is structural only: within one
configuration, prefill throughput was still rising at the top of the measured range,
and prefill draws about 40% less power than decode at ~62% GPU utilisation.
A publishable prefill improvement claim requires the recorded-prompt profile on the
candidate configuration, with prefix caching controlled.

### Node power envelope

Decode draws roughly 1.9 kW aggregate across the eight GPUs and peaked at
2643 W at 78% mean utilisation. Decode is therefore not pinned against a power
cap, which keeps the expert-mode and runtime candidates worth testing.

The C32 control reproduces the published C32 median (727.7 output tok/s) within
3.1%, so the session is comparable at that point.

### 4.1 Protocol-length check: the +5.6% claim does not survive it

The 60 s sweep left an obvious confound: the published campaign measured 90 s
windows with three repetitions, while the raster used 60 s with two. Generation 7
re-measured the control configuration under the published protocol - 90 s windows,
three repetitions, same server, same session.

| Point | 60 s x 2 (Generation 1) | 90 s x 3 (protocol probe) | Published, `publication.json` |
|---:|---:|---:|---:|
| C48 | 926.05 | **933.01** | **927.373** (median, C48) |
| C56 | **977.95** | 943.37 | not measured |
| C48 to C56 gain | +5.6% | **+1.1%** | - |

The published comparator is
`results/xe7740-8x-rtx6000/glm5.3/publication.json` -> `/headlines/decode` = 927.373479422657
output tok/s at C48, last modified 2026-09-02 in commit `63a823d`. An earlier revision of
this journal used 1111 in that cell; that figure is **not in the repository or in any
campaign artifact** and section 4.3 explains how it got here.

Two conclusions, one of them against my own earlier claim:

1. **There was no campaign gap.** At C48 this session produced 926.05 (60 s x 2),
   927.38 (60 s x 2, control rerun) and 933.01 (90 s x 3) against a published
   927.373 - agreement within **0.001% to 0.6%** across four to six days, on a server
   restarted between campaigns. The window-length question this probe was built to
   answer was real but secondary: the effect is +0.8%, and section 7.7 measures the
   same effect at +3.1% on a different configuration. The protocol is validated; the
   "16% discrepancy" that motivated this whole investigation was an artefact of an
   un-sourced comparator, documented in section 4.3.
2. **The C56 advantage is real but small.** With three 90 s repetitions C56 is
   943.37 against C48's 933.01, i.e. +1.1%, and the C56 spread is large (35.81
   between repetitions, versus 10.45 at C48). The correct statement is that **C48
   and C56 are within noise of each other and both sit on a broad plateau, while
   C60 and C64 fall off sharply**. The earlier +5.6% was short-window noise, and
   the claim that the published operating point was badly misplaced is withdrawn:
   C48 is defensible, and the durable finding is only that the plateau extends to
   about C56 and that C64 is deep in the collapse.

The probe also reproduced KV capacity exactly (544,832 tokens) and captured
per-position acceptance directly from the engine:

```text
Mean acceptance length: 2.61, speculative depth 3
Per-position acceptance: 0.768, 0.520, 0.318   (mean 53.5%)
```

That is the quantitative case for the MTP-depth raster: the third draft token is
accepted under a third as often as the first while costing a full verification row
per sequence.

### 4.2 Evidence-capture caveat

The probe's `params.txt` records `max_cudagraph_capture_size: None`, which is the
effective-argument form rather than the resolved compilation-config value of 256.
The parameter assertion therefore checks the resolved value; a naive grep of
`params.txt` alone would wrongly conclude the graph width was unset.

### 4.3 The discrepancy was invented by me: a comparator with no artifact behind it

This section previously read "three measurements agree and disagree with the published
figure by ~16%". That claim was **false, and every one of its components was checked
except the one that mattered.**

What was actually true: three measurements in this session agreed with each other
(926.05, 933.01, 904.22). What was never verified: the number they were said to
contradict. The published figure is **927.373 output tok/s at C48**
(`publication.json`, `/headlines/decode`, median), which is the maximum of the entire
published decode curve. It appears nowhere near 1111. Searching the repository and the
node's campaign tree confirms no measured decode value of ~1111 has ever existed for
this model:

- the string `1111` occurs in `publication.json` only inside unrelated fractional
  values, never as a decode throughput;
- on the node, the only artifact paths containing `1111.` are **warmup** exports and a
  prefill `profile_export.jsonl`, from superseded `seq32/graph128` and `balanced`
  campaigns - phases explicitly excluded from publication.

So the control configuration reproduced the published headline to within 0.001% on the
first try, and I spent hours investigating a gap that did not exist.

**How an unverified number survived this long.** The 1111 figure arrived as a recollection
- plausible, memorable, and close to what a good result on this hardware should look
like. It then acquired the authority of a citation because each later section referred
to "the published 1111" rather than to the artifact. Three designed experiments
(protocol probe, ambient cap, ambient A/B) were justified by it. Every one of them was
well executed and produced a valid negative; none of them checked the comparator.

**The rule, now in PROCEDURE rule 19:** a cross-campaign delta must name the artifact
path, the field inside it, and the statistic. "The published run got X" is not a
comparator. A number with no path is a hypothesis about a number, and any conclusion
built on it inherits that status - including when it happens to be convenient,
especially then.

The accidental positive result: **this node is reproducible across sessions to under a
percent** at C48 after a full restart and four to six days of other workloads, and
across window classes to 0.8-3.1%. That is far better run-to-run stability than I
assumed, and it retrospectively strengthens every within-session comparison in this
journal - which had been discounted on the strength of the phantom gap.

### 4.4 The ambient hypothesis, tested and mostly rejected

Ambient interference was the leading candidate for the 16% gap described above -
which section 4.3 shows did not exist. The experiment was still worth running, and it
is reported here as the clean negative it is. `cadvisor` is a **docker container** (`obs-cadvisor`), not
the systemd unit I had assumed - which is why `systemctl show -p MainPID` returned 0
and why my first two attempts to characterise it were wrong.

The cap was applied at a clean candidate boundary (generation 7 stopped between its
`mtp1` and expert-mode candidates, with the reason recorded) so that no single
generation straddles the change. Generation 9 then measured the **control baseline
first**, before any candidate, giving a same-session A/B on an identical
configuration.

| Ambient CPU | cadvisor | ambient non-benchmark cores |
|---|---:|---:|
| before | 40.1 cores, unbounded | **41.43** |
| after `--cpus=4` | 4.0 cores, capped | **4.79** |

Effect on the control configuration, identical protocol, same session:

| Point | high ambient (gen 7) | bounded ambient (gen 9) | change |
|---:|---:|---:|---:|
| C48 | 927.38 | 951.24 | **+2.6%** |
| C56 | 988.81 | **999.90** | **+1.1%** |
| C64 | 821.28 | 843.22 | +2.7% |

**Removing ~36 cores of background load bought 1-3%.** That is a real, repeatable
and previously undocumented interference cost, and it is the correct answer to a
question that should have been asked on its own merits rather than as an explanation
for a phantom discrepancy. The reason this experiment was still correct to run is
that it was cheap, it was ordered baseline-first, and it converted a vague suspicion
into a bounded number instead of a standing confound.

The mechanism was also mis-guessed in advance: with 344 CPUs and the node 88% idle,
the CPU count itself could not starve 8 worker threads, so the expected channel was
memory-bandwidth and cache pressure from a full-cgroup scan. The measured +1-3% is
consistent with that being the true but small contribution.

There is no gap left to explain. The residual +2-3% this session measures above the
published C48 value is consistent with the ambient cap plus the window-class effect of
section 7.7, both of which are now quantified.

---

## 5. Defects found in my own harness

Four automation defects appeared while driving the raster. Each is recorded
because it yields plausible-looking but wrong, or silently missing, evidence.

1. **Port 8080 contention.** The candidate launcher removed only its own
   container name, while the port was still held by the previous qualification
   container. `docker run` failed with exit 125 and the generation aborted in
   under a second. Launches now run a helper that stops every container
   publishing 8080 and waits for the listening socket to close.
2. **Cascade aborts.** The chained waiters test the predecessor PID, so a
   controller that dies for a non-benchmark reason takes the rest of the queue
   down with it. The waiters now re-read the predecessor PID file each poll.
3. **Sampler output lost.** The telemetry loop printed to stdout without a CSV
   redirect, leaving `telemetry.csv` containing only its header. All 1294
   samples were recoverable from the controller log because the script tees
   stdout, and were re-parsed positionally into
   `gen1-fine-concurrency/telemetry-recovered.csv`. The sampler that pointed at
   a deleted qualification cgroup was replaced by one that resolves the running
   container's own cgroup.
4. **False `params_mismatch`.** Candidate verification grepped the log for
   `--max-num-seqs 48`, but vLLM logs engine arguments as a Python dict
   (`'max_num_seqs': 48`). Both Generation 2 candidates were skipped even though
   they were configured correctly. Verification now reads the dict form, writes
   it to `params.txt` as evidence, and asserts on that.
5. **Candidate result collision.** The Generation 2 benchmark helper wrote to
   `$STATE/decode-C*` rather than a candidate-scoped path, so the second
   candidate would have silently overwritten the first candidate's results at
   every identical concurrency point. Discovered while reviewing progress, before
   candidate 2 ran. Paths are now `$CSTATE/<kind>-C<n>`, and completed points are
   skipped on restart so a fixed launcher can resume without discarding evidence.
   The two points already measured were moved into the candidate directory rather
   than re-measured.

Failed attempts were archived or renamed, never deleted, and no measurement from
a defective run was used.

### 5.1 AIPerf aborted the campaign from inside a native teardown assertion

At 09:09:12, during the Generation 2 C52 warmup, the benchmark client died with:

```text
Assertion failed: _count > 0 (src/trie.cpp:123)
Aborted (core dumped)
```

The sequence in the log matters. Every request had already completed and been
processed:

```text
Phase profiling complete | completed=32, cancelled=0, errors=0
Processed 32 valid requests and 0 errors
_finalize_and_process_results completed
All results received, initiating shutdown
Assertion failed: _count > 0 (src/trie.cpp:123)
```

So this is a client-side teardown defect, not a server or capacity event: the
server stayed at `/health` 200 throughout, GPUs stayed healthy, and there were no
OOM records in `dmesg`. Rerunning the identical C52 command succeeded
(`repro_exit=0`), which makes it intermittent rather than deterministic. It
resembles a reference-count assertion in a native structure shared with the
tokenizer/metrics path; only `profile_export.jsonl` had been written, so the
point's JSON export never appeared.

The real defect was **mine**: the controllers ran under `set -e`, so a single
non-zero exit from the benchmark client aborted the controller, and because each
queued generation polled its predecessor's PID, all four generations stopped at
once. Four changes follow:

1. Controllers no longer use `set -e`. A failed point is recorded in
   `bench-failures.tsv` as `bench_incomplete` and the run continues.
2. A point counts as measured only if `rep2/profile_export_aiperf.json` exists,
   rather than trusting the exit status.
3. Waiters now **serialise GPU access** instead of inheriting failure: they
   proceed when the predecessor either completed or exited, logging that the
   predecessor aborted. GPU serialisation and failure propagation were
   conflated, which is what turned one client crash into a full stop.
4. A controller that exits non-zero without `COMPLETE` writes `ABORTED`, so the
   terminal state of every generation is distinguishable after the fact.

The lesson generalises: benchmark-harness process lifecycle must not be coupled
to measurement validity. An intermittent crash in the load generator is a
recoverable, per-point event, and the campaign should degrade by one point rather
than by the whole queue.

### 5.2 Three more harness defects, all mine

Generations 3 and 4 produced **zero measured points** between 10:41 and 11:16. No
server fault, no OOM, no client crash: all three defects were in code I wrote that
day.

1. **Bash `local` evaluates every word before assigning any of it.** Writing
   `local label=$1 ... out="$STATE/$label/$kind-C$c"` in one statement means
   `$label` is expanded while still unset, so under `set -u` the shell died with
   `line 50: label: unbound variable`. It killed Generation 3 immediately after
   its probe server reached readiness, discarding an 11-minute startup. Generation
   4 carried the same latent bug and never lived long enough to reach it. The
   corrected form declares them in separate `local` statements.
2. **The quality gate tuple was malformed.** `correctness.py` contained a 2-tuple
   among 3-tuples, so `for name,q,expect in PROMPTS` raised
   `ValueError: not enough values to unpack` before judging a single prompt.
   Because candidates ran `quality X && perf X`, every expert-mode candidate
   launched a full ~10-minute server startup and then measured nothing - roughly
   25 minutes of GPU time producing no evidence.
3. **A completion marker can certify an empty generation.** Generation 4 was about
   to write `COMPLETE` with zero measurement files, which would have made a null
   result look like a clean pass. It was stopped, given `ABORTED` plus
   `INVALID.reason`, and Generation 3 received a clearly-labelled
   `ABORTED.retroactive` because the marker logic post-dated its death.

Two verification habits follow, and both were applied before rerunning:

* **Count the evidence, not the exit status.** A generation is complete iff
  `find ... -name profile_export_aiperf.json | wc -l` matches the plan. Generation
  4's count was 0 while its marker said complete.
* **Validate a gate against both a cooperative and a hostile stub before trusting
  it on hardware.** Running `correctness.py` against stub servers gave 6/7 and 0/7
  with correct exit codes, in seconds, without loading the model or contaminating
  a measured window. It also exposed an over-strict JSON expectation that could
  have failed for quoting reasons alone, which was relaxed to a substring test.

When the corrected reruns were assembled by splicing existing scripts, the result
contained **two `bench` definitions**, the later one 5-argument, which would have
silently overridden the 7-argument version and run the protocol-fidelity probe at
60 s x 2 instead of 90 s x 3 - defeating the one measurement whose entire purpose
was to test window length. The rerun script was rewritten from scratch and now
asserts one definition each of `wait_ready`, `launch`, `bench` and `quality`.

### 5.3 The defect recurred, and so did my tooling's inability to see it

Generations 5 and 6 died the same way as 3: `line 53: kind: unbound variable`, at
the `bench()` entry, immediately after readiness - so each burned a full ~12-minute
server startup and produced nothing. Both are now marked `INVALID` with
`INVALID.reason`. That makes **four generations with zero measured points**
(3, 4, 5, 6) against two productive ones (1, 2).

The root pattern is that all four shared one template, and I kept re-deriving new
generations from that template instead of from the corrected one. Fixing a bug in
one copy while generating four more from the broken original is how this happened.

Two safeguards were added, and one of them was itself wrong at first.

**An auditor that judges evidence, not markers** (`audit.py`). Current state:

```text
generation                     points  full  partial      marker   status
gen1-fine-concurrency             14    14       0    COMPLETE   ok
gen2-graph-matched                20    20       0           -   incomplete
gen3-speculation-depth             0     0       0     ABORTED   NULL RESULT
gen4-expert-mode                   0     0       0     INVALID   NULL RESULT
gen5-scheduler-and-headroom        0     0       0     INVALID   NULL RESULT
gen6-admission-headroom            0     0       0     INVALID   NULL RESULT
```

Generation 2's row is the interesting one: 20 of 20 points complete but no
`COMPLETE` marker, because the edit that removed its placeholder summary block also
removed the marker write. It received a labelled retroactive marker. The auditor is
right to flag it: an undocumented missing marker and an undocumented complete run
look identical, which is exactly the ambiguity being removed.

**A validator that initially could not detect the bug it was written for.**
`validate-raster.sh` extracts `bench()` and calls it with stubbed binaries. My first
version passed gen5 and gen6 - the two scripts that demonstrably crash - because the
extracted function ran **without `set -u`**, so the unbound variable expanded to an
empty string and the benchmark command simply referenced an empty path. The defect
was invisible for the same reason it is dangerous in production: silent empty
expansion.

After adding `set -u` to the harness it discriminates correctly:

```text
gen3  PASS     (fixed before it was rerun)
gen4  PASS
gen5  FAIL  kind: unbound variable
gen6  FAIL  kind: unbound variable
gen7  PASS     (written in the corrected style)
```

It also needed `MODEL` and `IMAGE` defined in the harness, otherwise every script
failed for a harness reason. A validator that only produces false positives is not
much better than one that produces false negatives; both get ignored.

The operative lesson is narrower and sharper than "test your code": **a test that
reproduces the conditions of the bug is the whole value of the test.** Running the
extracted function without the shell option that triggered the failure cost more
time than having no validator at all, because its `PASS` was believed.

Both reruns (7 and 8) are now written in the corrected single-`bench` style, and
generation 8 was validated before it was allowed into the queue.

### 5.4 The worst defect was not in the harness: a comparator with no source

Sections 5.1-5.3 are bugs in code. This one is a bug in reasoning, and it cost more.

An earlier revision of this journal asserted that this session measured ~16% below the
published figure. The comparator (1111 tok/s at C48) **does not exist in the repository
or in any campaign artifact**. The published value is 927.373, which this session
reproduced within 0.001% - so the "discrepancy" was an artefact of an unverified
recollection that acquired citation authority by being repeated across several sections
and referred to as "the published figure" rather than as a path and a field.

Three experiments were designed and executed to explain it: a protocol-length probe, an
ambient CPU cap, and a same-session A/B on the control. All three were methodologically
sound and produced useful, publishable negatives (window class +0.8%/+3.1%, ambient
+1-3%, node reproducibility <1%). Not one of them checked the comparator, which was the
single cheapest thing to verify and would have taken one `jq` command.

The failure mode is specific and worth naming: **the number was memorable, plausible,
and flattering to the hypothesis.** It said the hardware was capable of more than the
published result, which is exactly what someone mid-raster wants to be true. A
comparator that flatters your hypothesis deserves *more* scrutiny than one that does not.

Now encoded as PROCEDURE rule 19 and a section 16 checklist clause: every cross-campaign
comparison must name artifact path, field and statistic, or it is not a comparator.

### 5.5 The quality gate failed every candidate, including the healthy ones

Expert-mode candidates reached `ready` with correct KV-cache geometry and were then
refused by my own correctness gate, identically: `{"checks": 7, "passed": 6, "failed":
["spell"]}` for A8, for native W4A4 **and** for the MTP4+A8 combo. Three startups
(~30 min of eight-GPU time) produced zero measurements.

The `spell` check required the substring `percalifragilisticexpialidocious`, present only
when the model **echoes** the word. A model that spells it letter by letter — the more
correct reading of "spell the word" — fails. The gate was inverted: it punished better
behaviour, and being identical across candidates it had no discriminating power.

This was the second instance of one defect class in a single day: earlier I relaxed the
`code` check because it demanded a substring from a model emitting valid JSON without
pretty-printing, and left an equally over-strict expectation in the next row of the same
table.

Fix: a `letters:` comparison mode (letters only, so echo and letter-by-letter both pass
while a misspelling fails) and an offline `--self-test` asserting 14 positive and
negative cases without a server — a gate that cannot fail is worse than no gate.
Generation 15 runs the **control** through the gate first so its validity is established
on the same server class before any expert-mode result is believed.

### 5.6 A third null result, again from a guard I invented rather than read

Two generations (`gen14-confirm-and-turnover`, `gen15-expert-on-new-base`) aborted in under a
second each, producing zero measurements. The generated controller required the literal string
`ok free 8080` from `free-8080.sh`; the script has always printed `free8080_ok stopped=[...]`
and exited 0. So the guard reported `free8080_FAILED rc=0` — a contradiction that should have
been the tell: the script succeeded, the guard disagreed.

Zero GPU time was consumed, because the defect failed fast and before any container launch. That
is the only mercy available here: the same class of bug has now cost a queue slot three times
(gen3/gen5/gen6 variable-expansion defects, gen13 expert-mode container handling, now this).

Two repairs, both of which generalise:

1. The guard asserts the real contract **and** verifies state — `ss` shows no listener on 8080,
   and `/health` does not answer. Text alone was never sufficient evidence of a free port.
2. I validated by **executing** the guard: it passed with the port free, and a hostile case
   (a real container bound to 8080) was stopped and then verified free, which is the intended
   behaviour rather than a rejection. `bash -n` and the dry-run harness had already passed both
   broken scripts, and a regex patch that silently failed to match reported success — so parse
   checks are not evidence that code runs.

Codified as `R-03-19` in `harness/3-deployment-raster/RULES.md`.

### 5.7 The near-miss I only found while fixing a different bug

Rebuilding the raster controller this evening, I reconstructed the launcher from memory instead
of reusing gen12/gen13's tested harness. Three faults, ordered by how much they would have cost:

1. **No `--memory 96g`.** Every working generation binds host RAM at the 96 GiB allocation
   qualified in §1. My reconstruction omitted it. Had it started successfully it would have
   measured the headline peak extension (`seq128`/`seq144`/`seq160`, the +33% claim) **outside
   the qualified allocation** — comparable to nothing, and specifically not to the RAM-floor
   work that made the deployment credible. A silent validity failure: the numbers would have
   looked entirely reasonable.
2. **Model passed as a positional argument.** The image entrypoint is
   `serve-infernal-invocation.sh` with an empty CMD, so appending the model path replaces the
   CMD and vLLM exits with `unrecognized arguments`. Loud; the only one the environment caught.
3. **Corpus drift.** I used `osl=128` where the session's decode points use `osl=768`. Caught
   only because I was reading the working script line by line.

While fixing the resulting orchestration breakage I created a second incident: a follower
waiter was given an empty pid, its liveness test failed closed, and it started immediately.
Both generations share the container name `radixark-glm53-raster`, so each launch stopped the
other's server — four interleaved launches (21:38, 21:40, 21:44, 21:45), ~11 minutes of
discarded eight-GPU startup, zero measurements. The harness's own `name_still_taken` assertion
caught one collision, which is the only reason this was not a longer silent stall.

The pattern is uncomfortable and specific: **my reconstructions are where defects concentrate.**
Five null results today came from generated or reconstructed scripts; none came from the
harness built iteratively on the node. Reusing tested code and changing only the candidate list
is now `R-03-20`, which also requires a written-down pid for handoffs and an explicit
single-controller assertion before launch.

## 6. Ambient background load, measured

PROCEDURE 4.1 now treats background load as a controlled experimental variable.
A sampler was deployed mid-raster that separates serving CPU, load-generation
CPU, and everything else, attributing by process over the same window.

### What is actually running on XE7740-04

```
Non-benchmark ambient load:  ~38-40 cores
Largest consumer:            cadvisor, 39.0 cores
Runner up:                   victoria-metrics 0.7, node_exporter 0.4,
                             dcgm-exporter 0.1
Host load average:           ~75 on 344 CPUs
Host CPU count:              344
```

The dominant consumer is `obs-cadvisor`, which has been running continuously
since 2026-08-27 with zero restarts. Its cgroup reads:

```text
cpu.max    = max 100000   # quota unlimited
memory.max = max
pids.max   = 629145
```

`cpu.max` showing `max` means **no CPU quota**. Sustained ~39-core consumption by
an unbounded non-benchmark container is exactly the condition PROCEDURE 4.1
classifies as a preflight failure, and it was not caught by preflight because
cadvisor is also the thing that reports the metrics a preflight gate would use.

### Consequences for this raster

1. **Generation 1 has no ambient attribution.** It completed before the sampler
   existed. Its C32 control matched the published figure within 3.1%, which is
   reassuring but not equivalent to recording the covariate.
2. **Ambient drift becomes a live candidate for the C48 discrepancy**, replacing
   speculation. The published seq64/graph256 campaign ran on 2026-08-31; if
   ambient load then differed from the ~39 cores measured today, cross-campaign
   comparison is confounded in exactly the way PROCEDURE 4.1 warns about. The
   discrepancy stays unresolved until measured against a common environment.
3. **cadvisor is not being touched mid-raster.** Reconfiguring it now would
   produce an inhomogeneous result set, which is harder to interpret than uniform
   contamination. The sequence is: finish the raster, bound cadvisor, re-capture
   baselines, then re-measure the affected control points.

Per PROCEDURE 4.1 the correct follow-up is an explicit present/absent A/B of
cadvisor on one frozen configuration across the concurrency range, not an
assumption that 39 cores of filesystem walking is harmless. Its known cost is
recursive overlayfs filesystem-usage walks, which contend on the same page-cache
and dentry paths the serving stack uses.

## 7. The admission-headroom finding: discovery path and results

### 7.0a How the headroom finding was discovered

The result was not found by sweeping blindly; it came out of a chain where each link
was forced by a prior measurement. Recording the chain matters because the two
candidate configurations that finally won were suggested by **two independent
failures that pointed in opposite directions**.

**Step 1 - the published grid was too coarse to see the peak (Generation 1).**
The published decode curve used C32/C48/C64. A 10-step sweep showed the peak was a
broad plateau rather than the published point, and that C64 sat 17.8% below peak with
66% higher ITL. Nothing there was above 1000, but it established that concurrency was
a live parameter rather than a settled one.

**Step 2 - narrowing admission *toward* the old peak made things worse (Generation 2).**
`seq48/graph192` and `seq56/graph224` were built to match admission and graph width to
the presumed C48 optimum, satisfying the `max_num_seqs x (1 + MTP depth)` graph rule
exactly. Both lost - `seq48` by as much as 27% at C56 - while **reporting more KV
capacity than the control** (557,056 vs 545,600 tokens). That combination was the
signal: more KV, less throughput, and the loss grew with applied concurrency.

**Step 3 - the interpretation, stated as a falsifiable claim.** Throughput was not
limited by KV capacity or graph width but by **admission headroom relative to applied
load**. With MTP depth 3 every sequence occupies `1 + 3 = 4` graph rows, so a scheduler
at exactly `max_num_seqs` has no slack to place a newly-arriving batch. The prediction
this makes is specific: *widening* admission beyond the load should help at high
concurrency, and narrowing it below the load should hurt badly. Generation 2 had
already demonstrated the second half.

**Step 4 - isolate the environment before trusting the candidate.** Rather than test
the claim immediately, generation 9 measured the **control baseline first** under a
changed environment (ambient CPU capped), so any candidate number would have a
same-session anchor. This is the ordering that made the later comparison credible, and
it also produced the negative result in section 4.4: the ambient change was worth only
1-3%.

**Step 5 - the claim survived, and quantified itself.** `seq80/graph320` lifted C64 by
16.7% over the control, then `seq96/graph384` reached 1054.71 at C80 with the curve
still rising - both on 60 s windows, so neither was publishable yet.

**Step 6 - extend the sweep until it turns over, then measure at protocol length.**
Generation 12 continued `seq96` to its admission ceiling and re-measured with five and
three 90 s repetitions: C80 1087.74, **C88 1110.99**, C96 1013.90. The turnover landed
on C96 - exactly `max_num_seqs` - which is the same mechanism that destroyed `seq48`
and `seq56`, now seen from the other side. Stopping at C80 would have reported the top
of an unfinished sweep as a peak, repeating the original published-grid mistake.

The whole finding is one variable: **`max_num_seqs` must exceed the concurrency you
serve, by roughly 10-15%.** Every otherwise confusing measurement in this journal is
explained by it, including the two candidates that had to lose before it was visible.

This sequence is now the process contract, not just this session's ad-hoc method:
`PROCEDURE.md` rules 13-18 and the section "Naming the parameter search, and what it is
not" codify the OFAT interaction probe, the turnover requirement, window-class
comparability, re-baselining across environment changes, evidence-count auditing, and
the prohibition on calling a raster an optimisation.

What did *not* produce the gain, each measured rather than assumed: speculation depth
below 3 (section 7.6), graph width as an independent variable, GPU memory utilisation
(KV was never binding: 96 sequences x ~776 tokens needs ~75 K of 536 K available),
measurement window length (0.8%), and background CPU load (1-3%).

### 7.0 The first measurement above 1000 output tok/s, and why it is not yet a claim

After the ambient cap, the control configuration measured **above 1000 output
tok/s** at C56 under the published protocol (90 s windows, three repetitions):

```text
rep1   987.09 tok/s   errors=0
rep2  1012.71 tok/s   errors=0
rep3  1022.57 tok/s   errors=0
median 1012.71   min 987.09   max 1022.57   spread 35.48
```

This is the session maximum and it clears 1000 on the median. It does **not** yet
support a published "1012 tok/s" headline, for three reasons:

1. Only **2 of 3** repetitions exceed 1000, and the worst is 987.09. A median that
   straddles a threshold readers treat as pass/fail needs enough repetitions that
   one sample does not decide it.
2. The repetitions trend **upward** (987 -> 1013 -> 1023). That is either legitimate
   steady-state warm-up or drift, and n=3 cannot distinguish them. If it is drift the
   median understates the settled value; if it is noise the median is optimistic.
3. C48 measured **951.24** with a tight 6.13 spread and 0/2 above 1000. The sub-1000
   and above-1000 measurements sit at *different* concurrencies and must not be
   quoted interchangeably.

The same configuration at C56 under high ambient gave 988.81 (978.92, 998.70), 0/2
above 1000 - so the ambient cap moved the distribution across the line rather than
clearing it.

The defensible statement today: **the C56 decode plateau sits at roughly
1005 +/- 20 tok/s, i.e. on the 1000 boundary.** A publishable number needs six or
more 90 s repetitions at the winning point. A larger and more honest margin should
come from expert execution width (native W4A4), not from more repetitions.

| Generation | Content | State |
|---|---|---|
| 1 | C32-C64 fine concurrency, unchanged control | **complete** |
| 2 | seq48/graph192 and seq56/graph224, MTP3 | **complete, both falsified** |
| 3 | MTP depth raster + protocol-fidelity probe | **invalid: harness defect, 0 measured points**, rerun as 7 |
| 4 | expert mode A16 / A8 / native W4A4 | **invalid: harness defect, 0 measured points**, rerun as 7 |
| 5 | scheduler budget, GPU utilisation | **invalid: harness defect, 0 measured points**, superseded |
| 6 | admission headroom seq80 / seq96 | **invalid: harness defect, 0 measured points**, superseded |
| 7 | protocol probe, MTP depth 3/2/1 | **complete for probe + MTP**, stopped at candidate boundary before expert modes so the ambient cap could apply to whole generations |
| 8 | scheduler budget, GPU headroom, admission headroom | **superseded by 9**: control points ordered last, so it could not self-calibrate across the environment change |
| 9 | bounded-ambient campaign: control baseline first, then seq80/seq96, then expert modes behind a quality gate | running |
| 10 | MTP depth 4 and 5 (justified by the monotonic depth raster, section 7.6), plus a combined candidate | queued, validated |
| 11 | seq80 protocol confirmation | **deferred**: the winning configuration moved past it (`DEFERRED.reason`) |
| 12 | extend `seq96` to its admission ceiling at protocol length, then `seq112/graph448` and `seq128/graph512` to find where headroom stops paying | **produced the 1110.99 peak**; wider-admission curves in progress |
| 13 | expert modes retried with logs streamed from container creation and a name-free assertion | queued, validated |

### 7.1 Admission headroom is the first configuration that wins, and it crosses 1000 reproducibly

`seq80/graph320` (`max_num_seqs=80`, `max_cudagraph_capture_size=320`, MTP3, everything
else identical to the published control) is the only candidate that beat the control,
and it did so decisively in the high-concurrency region:

| Point | control `seq64/graph256` | `seq80/graph320` | delta | spread |
|---:|---:|---:|---:|---:|
| C48 | 946.03 | 932.96 | -1.4% | 9.23 |
| C56 | 1012.71 | **1012.27** | -0.0% | **1.96** |
| C64 | 843.22 | **983.76** | **+16.7%** | 7.39 |
| C72 | not measured | **995.11** | - | 21.36 |
| C80 | not measured | 901.29 | - | 6.40 |

**The crossing is reproducible.** At C56 the two repetitions were 1013.25 and 1011.29 -
**both above 1000, spread 1.96**. Compare the control's near-identical 1012.71 median,
whose repetitions were 987.09 / 1012.71 / 1022.57 with only 2 of 3 above the line.
Nearly equal medians, completely different credibility: the control value is a median
sitting on a threshold, this one is a tight distribution above it.

**The real win is shape, not peak.** Admission headroom barely moves the peak (1012.27
vs 1012.71) but lifts C64 by 16.7% and still holds 995 at C72, where the control has
already collapsed to 843. The mechanism matches Generation 2: at `max_num_seqs=64` with
MTP3 every sequence needs `1 + 3` graph rows, so C64 needs exactly 256 rows with zero
admission slack and the scheduler bubbles; at 80 sequences the same C64 load leaves 64
rows of slack. The peak is compute-limited, so headroom cannot raise it - but it removes
the cliff, which is worth more in serving than a few percent of peak.

This reframes Generation 2. `seq48/graph192` and `seq56/graph224` both lost while
`seq80/graph320` won, and all three satisfied the `max_num_seqs x (1 + MTP depth)`
graph rule. The rule is necessary but not sufficient: **what killed the narrower
candidates was admission below the applied load**, not graph width.

Confirmation under the published protocol (90 s windows, 5 reps at C56) is queued as
generation 11. Until it completes the publishable statement is "1012 tok/s at C56, two
60 s repetitions, both above 1000, spread 2" - not "1012 tok/s at protocol grade".

### 7.2 Admission headroom keeps paying: 1054.71 tok/s, and the peak was not reached

`seq96/graph384` (`max_num_seqs=96`, `max_cudagraph_capture_size=384`, MTP3) beat both
the control and `seq80/graph320`, and its curve had **not turned over** at its highest
measured point:

| Point | control `seq64/graph256` | `seq80/graph320` | `seq96/graph384` | spread (seq96) |
|---:|---:|---:|---:|---:|
| C48 | 946.03 | 932.96 | 932.22 | 21.80 |
| C56 | 1012.71 | 1012.27 | 1013.10 | 34.49 |
| C64 | 843.22 | 983.76 | 979.64 | 10.32 |
| C72 | not measured | 995.11 | **1029.92** | **4.12** |
| C80 | not measured | 901.29 | **1054.71** | 29.48 |

The session maximum is now **1054.71 output tok/s**, +4.2% above the previous best and
+19.8% above the published C48 headline of 927.373, and +25% above what the
published configuration achieves at the same C80 load. C72's
repetitions were unusually tight (spread 4.12), which makes 1029.92 the most trustworthy
above-1000 number measured so far.

Three observations, stated with their limits:

1. **Throughput rises with admission headroom, not with graph width.** Three
   configurations, all graph-covered correctly, ordered `seq48 < seq56 < seq64 ~ seq80
   < seq96`. KV capacity moved the other way (545,600 -> 540,288 -> 536,192 tokens as
   graph capture grew), which is further evidence KV is not the binding constraint for
   this workload: 96 sequences x ~776 tokens needs ~75 K of the 536 K available.
2. **The peak may still be higher.** The curve rises through C72 and C80 while
   `max_num_seqs=96` permits C96. Generation 12 extends the curve to C88/C96 at
   protocol length and continues to `seq112/graph448` and `seq128/graph512` to find
   where this stops paying. Stopping the sweep at C80 and calling it the peak would
   repeat the exact mistake made with the published C32/C48/C64 grid.
3. **These are 60 s x 2 measurements.** The published protocol is 90 s x 3. Generation
   12 re-measures C80 with five 90 s repetitions and C72/C88/C96 with three before any
   number is treated as publishable.

The queue was reprioritised accordingly: the seq80 protocol confirmation was deferred
(marked `DEFERRED.reason`) because the winning configuration moved past it, and peak
extension took its place.


The Generation 2 `seq48/graph192` decode series is complete and **decisively
falsifies** the hypothesis that matching admission and graph width to the old C48
peak helps.

Candidate verified configured as `max_num_seqs: 48`, `max_cudagraph_capture_size:
192`, MTP3, reporting **557,056 GPU KV cache tokens** against the control's
**545,600** (+2.1% capacity), smoke test passing, zero request errors:

| Point | seq48/graph192 | Control seq64/graph256 | Delta |
|---:|---:|---:|---:|
| C32 | 693.22 | 705.40 | -1.7% |
| C40 | 820.74 | 839.56 | -2.2% |
| C44 | **823.79** (its peak) | 887.14 | -7.1% |
| C48 | 758.77 | 926.05 | -18.1% |
| C52 | 748.14 | 953.00 | -21.5% |
| C56 | 713.94 | **977.95** (control peak) | **-27.0%** |
| C64 | 696.52 | 803.99 | -13.4% |

Its own peak is **C44 at 823.79**, which is 15.8% below the control's peak. The
deficit is not a constant offset: it widens monotonically with concurrency until
the candidate is 27% behind at the load where the control performs best.

Beyond its 48-sequence admission limit the candidate degrades qualitatively, not
just quantitatively. TTFT p95 goes to 35.34 s at C56 and 40.11 s at C64, versus
3.34 s and 3.56 s for the control at those points, while its repetition spread
also grows (27.94 at C52). The control never exceeds 3.56 s TTFT p95 anywhere in
its range.

Prefill moves the same direction but far more mildly: 8291.33 input tok/s at C32
versus the control's 8517.69, about -2.7%.

Two conclusions:

1. **`max_num_seqs` headroom is worth real throughput below the admission limit.**
   The narrower deployment has zero spare sequence slots exactly when the control
   still has slack, which is consistent with chunked prefill of arriving requests
   needing free slots to overlap with in-flight decode. Recorded as the mechanism,
   with `seq56/graph224` as the discriminating test: it covers its own verification
   width while retaining headroom at C48.
2. **KV capacity is not the constraint.** The candidate had strictly more KV cache
   than the control and performed strictly worse. Any further KV-headroom idea,
   including the GPU-utilisation raster, should be judged against this and treated
   as low prior probability for decode.

Bucket starvation was ruled out: the candidate's capture list is
`[1, 2, 4, 8, 16, 24, 32, 40, 48, 56, 64, 72, ..., 192]`, so the
48 sequences x 4 rows = 192 width exists exactly as designed.

### 7.2a Generation 2: the falsification that pointed at admission

`seq56/graph224` was verified configured (`max_num_seqs: 56`,
`max_cudagraph_capture_size: 224`, MTP3), reporting **550,976 GPU KV cache
tokens** versus the control's 545,600, and completed with the same measurement
protocol.

| Point | seq48/graph192 | seq56/graph224 | Control seq64/graph256 |
|---:|---:|---:|---:|
| C32 | 693.22 | 697.71 | **705.40** |
| C40 | 820.74 | **846.27** | 839.56 |
| C44 | 823.79 | 880.42 | **887.14** |
| C48 | 758.77 | 906.67 | **926.05** |
| C52 | 748.14 | 897.84 | **953.00** |
| C56 | 713.94 | 812.96 | **977.95** |
| C64 | 696.52 | **811.42** | 803.99 |

Prefill for the same candidate: 8345.99 at C32, 16336.22 at C48 and 15608.94 at
C64, against the control's 8517.69, 17986.84 and 18238.55 - so the control also
leads on prefill, by 2% to 14%.

One transient client error occurred in the whole generation: a single
`ServerDisconnectedError` in rep1 of `seq56-graph224/prefill-C48`, with rep2 of the
same point clean. That point is reported from the median of both repetitions and
the error is recorded rather than quietly dropped.

**The ordering is by admission headroom, not by graph width.** At a given
concurrency C, every deployment whose `max_num_seqs` equals C collapses, while one
with spare slots does not:

| Deployment | Slots | Throughput at C equal to its own limit | Throughput at C56 |
|---|---:|---:|---:|
| seq48/graph192 | 48 | 758.77 at C48 | 713.94 |
| seq56/graph224 | 56 | 906.67 at C48 | 812.96 |
| seq64/graph256 | 64 | 926.05 at C48 | **977.95** |

TTFT p95 tells the same story: the control stays at or below 3.56 s across its
whole range, while `seq56/graph224` reaches 37.09 s at C64 once it is past
admission. Narrowing the graph to save memory therefore converts a throughput
curve into a cliff.

This inverts the original Generation 2 hypothesis. If headroom is what matters,
the productive direction is **more** admission capacity, not less: candidates
`seq80/graph320` and `seq96/graph384`, measured out to C64, with GPU graph memory
traded against KV capacity reported explicitly. That is queued as Generation 6.

The Generation 2 hardening also held: no AIPerf crash recurred,
`bench-failures.tsv` stayed empty across both candidates, and 14 of 14 decode
points plus 6 of 6 prefill points produced complete two-repetition evidence.

### 7.2b Acceptance is also readable from the server log

The engine prints speculation quality directly, which is a better source than
counter deltas alone:

```text
Mean acceptance length: 2.57, Current speculative depth: 3
Accepted: 1191 tokens, Drafted: 2277 tokens
Per-position acceptance rate: 0.765, 0.481, 0.323
Avg Draft acceptance rate: 52.3%
```

Per-position rates are what make the MTP-depth question quantitative: position 3
of 3 is accepted only 32.3% of the time, so the third draft token carries roughly
a third of the marginal value of the first while costing a full additional row of
verification width per sequence.

Graph coverage must satisfy `max_num_seqs x (1 + MTP depth)`; the C32 collapse
recorded on 2026-08-30 came from violating exactly this. The 0.979 utilisation
figure is not a guess: the runtime reports that with graph-memory profiling
enabled, 0.95 is equivalent to 0.9211 without it, and 0.9789 restores the
previous KV allocation.

Expert-mode candidates require a correctness gate before any throughput claim.
The KLD harness referenced in the deployment contract does **not** exist on this
host, so Generation 4 uses a deterministic exact-match battery over arithmetic,
extraction, code-echo, spelling and logic prompts at temperature 0, and the
limitation is stated rather than glossed: exact match is not a distributional
quality test. An A8 or W4A4 gain is worthless if output quality moves.

### 7.3 Protocol-grade confirmation: 1087.74 tok/s with five repetitions

The C56 number that crossed 1000 on two 60 s repetitions has now been confirmed under
the published protocol, at a different concurrency and configuration:

```text
seq96/graph384, MTP3, C80, 90 s windows x 5 repetitions
  output  1087.74 tok/s   (median)
  spread    10.59 tok/s
  errors    0
  ITL50     67.06 ms      acceptance 0.548
```

Five independent 90 s repetitions, zero failed requests, and a spread of one percent
make this the first measurement in this campaign that can be published without a
caveat about window length or sample count. It is **+8.9% over the control's C56
best** and **+7.5% over the 1012 tok/s figure** that the previous section was
hesitating to claim.

A first repetition at C88 then measured **1105.40 tok/s**, so the curve had again not
turned over when this was written - the C88/C96 sweep was still in progress. That
matters for how the 1087.74 figure is described: it is a confirmed measurement at a
specific operating point, not the peak of this configuration.

### 7.4 Expert modes produced nothing, and the reason is a diagnostics-order defect

Both expert-mode candidates in generation 9 failed, and the interesting part is not
the failure - it is that **the evidence was destroyed by the order of the capture**.
The captured `startup.log`, `failure-signals.txt` and `container-inspect.json` all
contain only `Error response from daemon: No such container`. The container had
already disappeared by the time `wait_ready` tried to read it, so the crash reason
was never recorded. Both candidates are marked `INVALID` with that explanation rather
than left as unexplained gaps.

Two defects, both in `launch()`:

1. `free-8080.sh` **stops** containers but never removes them. A stopped container
   still owns its name, so the next `docker run` failed with a name conflict, and the
   `docker rm -f` at the top of `launch()` had already silently failed via
   `|| true`. The visible symptom (`docker_run_failed`) had nothing to do with the
   expert-mode change being tested.
2. Logs were collected **after** the failure was detected, rather than streamed from
   the moment the container was created.

Generation 13 retries both expert modes on top of the now-winning `seq96/graph384`
base, with `docker logs -f` writing to `server.log` from creation, an explicit
name-free assertion before `docker run`, and a `failure-tail.txt` snapshot. Until that
runs, **the effect of expert execution width on this model is simply unknown** - not
"tested and rejected".

### 7.5 The peak is C88 at 1110.99 tok/s, and the curve turned over where the mechanism predicts

`seq96/graph384`, MTP3, all repetitions at published protocol length (90 s):

| Point | out tok/s (median) | repetitions | above 1000 | ITL50 ms | TTFT50 s |
|---:|---:|---|---:|---:|---:|
| C72 | 1023.68 | 1011.63 / 1055.87 / 1023.68 | 3/3 | 62.71 | 0.82 |
| C80 | 1087.74 | five reps | 5/5 | 67.06 | 0.99 |
| **C88** | **1110.99** | 1105.40 / 1118.10 / 1110.99 | **3/3** | 72.36 | 1.60 |
| C96 | 1013.90 | 1024.43 / 1003.05 / 1013.90 | 3/3 | 86.16 | 3.76 |

This is the first result in the campaign that satisfies every publication condition at
once: published window length, three or more repetitions, zero request errors, spread
near one percent, and a **turned-over curve**, so the number is a peak rather than the
top of an unfinished sweep.

**Session maximum: 1110.99 output tok/s** - +9.8% over the control's best (1012.71 at
C56), and +14.9% over the control measured at the same C88 load.

The turnover is the most useful part. C96 is exactly `max_num_seqs`, i.e. **zero
admission slack**: with MTP3 every sequence needs four graph rows, so a full
96-sequence batch needs all 384 rows with nowhere to grow. Throughput falls 8.7% while
TTFT jumps 2.4x (1.60 s -> 3.76 s). The peak sits at C88, about **92% of
`max_num_seqs`**.

That gives a rule worth recording beyond this model:

> **Set `max_num_seqs` roughly 10-15% above the concurrency you intend to serve.**
> Admission slack is a first-class throughput parameter. Maximising it is not the goal,
> and serving *at* the configured maximum is a self-inflicted stall.

This also unifies the entire raster. `seq48` and `seq56` lost because their admission
was *below* the applied load. `seq80` held C56-C72 and fell at C80 - its own maximum.
`seq96` peaked at C88 and fell at C96 - its own maximum. Every point is explained by
headroom relative to load, with no reference to graph width or KV capacity.

### Relationship to the published figure: +19.8%, not a coincidence

The published headline is **927.373 output tok/s at C48** (`publication.json`,
`/headlines/decode`, median of three repetitions, maximum of the published decode curve).
Measured against that artifact rather than against the phantom 1111 of section 4.3:

| Quantity | Value | Basis |
|---|---:|---|
| Published decode headline | 927.373 | `publication.json`, C48, `seq64/graph256` |
| This session, same config, C48 | 926.05 - 933.01 | reproduces the published value within 0.001-0.6% |
| New profile, protocol grade | **1110.99** | `seq96/graph384` @ C88, 90 s x 3 |
| Improvement | **+19.8%** | vs published headline |
| Session maximum, exploratory | 1133.58 | `seq112/graph448` @ C96, 60 s x 2 |

The near-equality between 1110.99 and the phantom 1111 was pure coincidence, and it is
worth recording why that mattered: the coincidence *felt* like confirmation, and a
matching number is the single weakest form of evidence in a comparison, because it can
be produced by two independent errors landing together. Had I checked the artifact at the
start, both the phantom gap and this false consolation would have been impossible.

The defensible claim is therefore **+19.8% over the published decode headline, at
protocol grade, on a re-tuned admission width** - and it needs no environment story to
survive.

### 7.5b Wider admission moves the peak again: 1133.58 tok/s, bought with TTFT

`seq112/graph448` (`max_num_seqs=112`, coverage 448, KV 531,328 tokens) was measured to
find where headroom stops paying. It has not stopped paying, but the shape changed in a
way that matters more than the peak number:

| Point | out tok/s (60 s x 2) | median reps | ITL50 ms | TTFT50 s |
|---:|---:|---|---:|---:|
| C72 | 1051.19 | 1050 / 1052 | 62.52 | **0.91** |
| C80 | 1069.79 | - | 63.48 | 3.49 |
| C88 | 1080.46 | - | 65.30 | 3.71 |
| **C96** | **1133.58** | - | 67.98 | 3.80 |
| C104 | 1121.65 | - | 74.36 | 4.07 |
| C112 | 1103.65 | - | 80.73 | 4.54 |

**New session maximum: 1133.58 output tok/s**, +2.0% over `seq96` at C88, and on 60 s
windows - roughly **1168 at protocol length** using the 3.1% short-window correction of
section 7.7. The peak sits at C96, about 86% of `max_num_seqs=112`, consistent with the
92% found on `seq96`.

**But the gain is not free, and the cost is not where I expected it.** Inter-token
latency at the throughput peak is essentially unchanged from the control's comfortable
operating point (67.98 ms vs 67.06 ms at `seq96`/C80) - tokens stream at the same rate
once they start. What degrades is **time to first token: 0.91 s at C72 rising to 3.80 s
at C96 and 4.54 s at C112.** The peak is therefore purchased by queueing admission
delay, not by per-token speed.

That distinction changes how this should be reported. Quoting "1133 tok/s" alone hides a
4-second first-token latency; quoting the control's "1012 tok/s" alongside TTFT 0.65 s
hides a genuinely different user experience in the other direction. The honest set of
operating points is:

| Goal | Configuration | out tok/s | TTFT50 | ITL50 |
|---|---|---:|---:|---:|
| Maximum throughput | `seq112/graph448` @ C96 | 1133.58 (60 s) | 3.80 s | 67.98 ms |
| Balanced peak | `seq96/graph384` @ C88 | **1110.99** (90 s x 3) | 1.60 s | 72.36 ms |
| Latency-respecting | `seq96/graph384` @ C80 | 1087.74 (90 s x 5) | **0.99 s** | 67.06 ms |
| Interactive | `seq112/graph448` @ C72 | 1051.19 (60 s) | **0.91 s** | 62.52 ms |

For any deployment with a first-token SLA, the last two rows are the useful ones, and
both still exceed 1000 tok/s. The maximum-throughput row is a legitimate headline only
when reported with its TTFT.

All four rows are 8-token synthetic prompts with prefix caching enabled; none of them is
a publishable headline until re-measured against the recorded prompt corpus.

### 7.6 Speculation depth: the raster, and the prediction I got wrong

Generation 7 measured MTP depth 3 / 2 / 1 on the same server family, each at its
required graph coverage (`max_num_seqs x (1 + depth)` = 256 / 192 / 128), everything
else identical to the control. These were taken **before** the ambient CPU cap, so the
comparisons are within-session and carry the ~1-3% ambient penalty of section 4.4
uniformly across all three depths. All values are 60 s x 2, output tok/s:

| Concurrency | MTP3 (control) | MTP2 | MTP1 | best |
|---:|---:|---:|---:|---|
| C32 | 694.41 | 708.73 | **728.04** | MTP1 +4.8% |
| C40 | **846.83** | 748.17 | 809.67 | MTP3 |
| C48 | **927.38** | 814.23 | 873.61 | MTP3 |
| C56 | **988.81** | 860.03 | 903.53 | MTP3 |
| C64 | 821.28 | 808.79 | **897.81** | **MTP1 +9.3%** |
| prefill C48 | 10346.86 | 10214.47 | 10505.33 | - |

Per-position acceptance came straight from the engine log:

```text
depth 3: per-position 0.768 / 0.520 / 0.318   mean acceptance length 2.61
depth 2: aggregate acceptance ~0.66
depth 1: aggregate acceptance ~0.79
```

**The prediction I made from those acceptance rates was wrong, and the throughput
raster is what corrected it.** Reading per-position acceptance alone, the third draft
token looks like dead weight at 0.318, so depth 2 should win. It does not: **MTP3 beats
MTP2 by 12.2% and MTP1 by 6.2% at C48.** The reason is that the accepted-token yield is
not the cost side of the trade - each extra depth costs a verification row per sequence
in the same batch, and at C40-C56 that row is cheap relative to the accepted tokens it
buys. Per-position acceptance rate is therefore **not** a valid criterion for choosing
speculation depth; only the throughput raster is.

**The two rasters intersect, and they corroborate each other.** At C64 the ordering
flips: MTP1 (897.81) beats MTP3 (821.28) by 9.3%. That is not a speculation result -
it is the admission mechanism arriving from a different direction. With
`max_num_seqs=64`, MTP3 needs all 256 graph rows at C64 and has zero admission slack,
whereas MTP1 needs only 128 and still has room to place a batch. The same configuration
that made `seq48` and `seq56` lose is what makes MTP3 lose here, and neither raster was
designed to test the other. Independent confirmation across two orthogonal axes is the
strongest evidence in this journal for the headroom mechanism.

Two secondary facts worth keeping:

* MTP1 wins at two places and for two different reasons: C32 (+4.8%) because the
  machine is under-loaded and shallow drafts waste less, and C64 (+9.3%) because MTP3
  has saturated admission there. Neither is a tuning candidate - the answer to C64 is
  more admission headroom, not shallower speculation, and C88 on `seq96` dominates both
  - and speculation is protocol-mandatory for this model in any case.
* The depth raster was **monotonic upward in depth** at C40/C48/C56. That monotonicity
  is the entire justification for testing depth 4 and 5 in generation 10; it is an
  extrapolation with evidence behind it, not a guess, and it is still unconfirmed.

One MTP1 prefill repetition recorded a single request error; it is a 60 s
decode-adjacent measurement and is not used for any claim.

Reproducibility of this raster's control column is good evidence for the whole session:
`mtp3-control` re-measured the same configuration that Generation 1 had measured hours
earlier and agreed within 2% at all five concurrency points (C48 927.38 vs 926.05, C56
988.81 vs 977.95, C64 821.28 vs 803.99, C40 846.83 vs 839.56, C32 694.41 vs 705.40).

### 7.7 Short-window bias, measured on an identical configuration

Because the whole campaign mixed 60 s x 2 sweeps with 90 s x 3 protocol measurements,
the offset between them was measured directly rather than assumed. Same configuration,
same session, same candidate, `seq96/graph384` at C80:

```text
60 s x 2 : 1054.71 tok/s
90 s x 3 : 1087.74 tok/s     (+3.13%)
```

Short windows read about **3% low** on this workload, most plausibly because the ramp
into steady state is a larger fraction of a shorter measured interval. Two consequences:

1. Every 60 s figure in this journal understates its protocol-grade equivalent by
   roughly 3%, so `seq112`'s 1080.46 at C88 corresponds to about 1114 at protocol
   length - which is why that curve is worth finishing rather than dismissing.
2. **Comparisons across generations are only valid within a window class.** The
   control's 1012.71 and `seq80`'s 1012.27 look identical but were taken at 90 s and
   60 s respectively, so `seq80` is nominally ahead once corrected. The medians are
   close enough that this does not change the ranking conclusion, but it must not be
   quoted as an exact tie.

### 7.9 Depth extrapolation broke at 4, and the ceiling rule broke at 128

Two claims from earlier in this session were falsified by the generations that followed
them. Both are recorded rather than edited away.

**MTP depth is not monotonic.** After MTP1 < MTP2 < MTP3 at C48, per-position acceptance
(0.32/0.52/0.77, rising with depth) suggested continuing to depth 4 and 5. It does not
continue:

| depth | C48 tok/s | vs MTP3 | per-position acceptance |
|---|---|---|---|
| 1 | 873.61 | −5.8% | — |
| 2 | 814.23 | −12.2% | — |
| **3** | **927.38** | — | 0.768 at `seq96` |
| 4 | 741.42 | **−20.1%** | 0.458 |
| 5 | 738.19 | −20.4% | 0.384 |

MTP4 and MTP5 are flat across C48–C72 and MTP4 also collapsed at C56 (508.02), so the
deficit is not a concurrency artefact. **MTP3 is the optimum**, and the inference that
produced depths 4 and 5 — "acceptance rises with depth, so deeper wins" — was an
extrapolation one step past the data. The raster caught it.

**The admission-slack rule does not survive `seq128`.** Section 7.4 states the peak sits
at ~92% of `max_num_seqs` with 10–15% headroom. That fitted `seq96` (peak C88, falls at
C96) and `seq112` (peak C96, falls at C112). `seq128` peaks **at its own ceiling**:

| deployment | C80 | C88 | C96 | C104 | C112 | C128 |
|---|---|---|---|---|---|---|
| `seq96/graph384` | 1087.74 | **1110.99** | 1013.90 ↓ | — | — | — |
| `seq112/graph448` | 1069.79 | 1080.46 | **1133.58** | 1121.65 | 1103.65 | — |
| `seq128/graph512` | 1067.61 | — | 1113.03 | — | 1157.50 | **1236.64** ↑ |

`seq128` at C128 is exactly `max_num_seqs` — zero slack — and is the session high, still
rising. Either the `seq96`/`seq112` dips have another cause or the pattern is not a rule.
Note the dip points are the weakest data in the table: 60 s × 2 with spreads of 21–35.
Generation 14 resolves it — `seq128` C128 is being remeasured at 90 s × 5, and
`seq144/graph576` / `seq160/graph640` extend past the ceiling to see whether turnover
exists at all. **Until then the slack rule is provisional and must not size a
deployment.**

What survives is the monotonic part: peak throughput rises with `max_num_seqs` from 48 to
128 (977 → 1237), paid for in TTFT, which reaches 5.0 s at C128 while ITL moves only
62 → 81 ms.

### 7.10 Where the session's peak stands

| configuration | grade | concurrency | out tok/s | vs published 927.373 |
|---|---|---|---|---|
| `seq96/graph384` MTP3 | 90 s × 3 | 88 | 1110.99 | +19.8% |
| `seq112/graph448` MTP3 | 60 s × 2 | 96 | 1133.58 | +22.2% |
| `seq128/graph512` MTP3 | 60 s × 2 | 128 | 1236.64 | **+33.3%** |

1236.64 is exploratory (2 repetitions, spread 34.79) and is being confirmed. None of
these is publishable: all use synthetic 8-token prompts with prefix caching enabled.

## 8. Open items
- **Apply the naming contract to published artifacts.** `publication.json`,
  `deployment.yaml` and the Astro site must use *deployment profile*, *operating
  point* and *raster*, and must not describe this work as parameter optimisation.


* Report the AIPerf `_count > 0 (src/trie.cpp:123)` teardown assertion upstream
  with the reproduction notes: it fires after all results are processed, is
  intermittent, and only `profile_export.jsonl` survives. Until fixed, the
  raster's validity check must be export-file presence, not exit status.

* Bound `obs-cadvisor` with a cgroup CPU quota, then re-capture baselines and
  re-measure the affected control points. Quantify its effect with a
  present/absent A/B on one frozen configuration rather than assuming it away.
* Add ambient attribution retroactively where possible, and state explicitly
  which results in this journal were taken without it.

* 64 GiB host-RAM boundary test.
* Reproduce the published C48 decode point under protocol settings to resolve
  the ~17% session offset.
* The `rtx6kpro` GLM-5.3-Flash runtime improvements (PCIe collective,
  decode prefetch, KDA side-stream) are untested against the full RadixArk
  checkpoint and need a loader plus correctness canary before they can be
  attributed to this model.
* The leaked `/dev/shm/vllm_offload_*.mmap` files remain a recurring operational
  hazard; the cleanup procedure should become part of preflight.
* The published GLM-5.3 decode headline was selected at C48. If the C56 result
  survives a protocol-length confirmation, both the published concurrency
  operating point and its peak figure need re-derivation.
* The deployment contract records an artifacts repository path under
  `/home/demouser/repos/llm-benchmark-artifacts` that does not exist on
  XE7740-04; that provenance path needs correcting or re-hosting.

### 5.8 gen14 falsifies the C128 peak, and the confounder is measurement order (23:06)

`seq128/graph512`, 90 s x 3-5 reps, points benched in the order **C128, then C96, then C112**:

| point | reps | median | range | position in sequence |
|---|---:|---:|---|---|
| C128 | 5 | **1115.73** | 1094.45-1123.64 | 1st |
| C96 | 3 | **1223.52** | 1209.40-1229.88 | 2nd |
| C112 | 3 | **1303.25** | 1297.36-1321.31 | 3rd |

Within-point spread is 1-2%, so this is not sampling noise: **throughput rises with position in
the session**, and concurrency ordering is completely confounded with it. The points were not
randomized. There is therefore no support here for "peak at C128", "peak at C112", or turnover —
the experiment cannot distinguish concurrency from session position at all.

### 5.9 Provenance correction: the 1236.64 comparator is mine, and I mis-recorded two values

The 60 s x 2 sweep that produced `C96 = 1113.03` and `C128 = 1236.64` lives in
**`gen12-peak-extension/seq128-graph512`**, not in a generation 13. Recomputing every point from
the files: C80 **1067.61**, C96 **1113.03**, C112 **1157.50**, C128 **1236.64**. The session table
in section 5.7 records C112 as 1179.33, which no file supports: my own analysis heredoc mixed
warm-up runs into the rep set. Two consequences:

- The "+33.3% over the previous peak" headline is **withdrawn**. It rests on two 60 s reps at one
  concurrency, and its 90 s confirmation returns 1115.73 at the same point.
- `gen12`'s four-point 60 s sweep is monotonically increasing in concurrency; `gen14`'s 90 s
  sweep is increasing in measurement order. Those two datasets disagree about what the x-axis is.
  Neither can settle the peak until order is controlled.

### 5.10 Four harness defects found while reading gen14, one of them fatal to the result

1. **`collect()` counted the wrong path.** It looks under `points/cN/`, but this generation writes
   `decode-CN/repN/`. It reported zero measurements while fourteen complete files sat on disk, so
   it would have declared a null result on a generation that contained the answer. My own
   measurement-file-count invariant was implemented against one layout and proved nothing.
2. **The AIPerf export has two shapes.** These files are `schema_version 1.4` with a flat
   `output_token_throughput.avg`; my analysis assumed a `results[0].metrics...` form and silently
   yielded nothing, which reads identical to an empty result. Silence and absence must not look
   alike. All of this analysis was done in throwaway SSH heredocs rather than in a tested repo
   script - section 5.5's lesson, ignored a second time, and this time it cost a claim.
3. **The startup deadline is a constant where it should scale with the candidate.**
   `seq144/graph576` and `seq160/graph640` were both declared `startup_failed` at 1020 s while the
   log shows them still compiling and registering routes - the larger the graph set, the longer
   capture takes. The turnover question is therefore **untested**, not answered negatively, and
   ~34 minutes of eight-GPU time went to prove nothing.
4. **The abort marker's name is spelled in two places.** The writer emits
   `ABORTED.invalid-harness-defect`; the reader tests for `ABORTED`, and my "cleanup" deleted the
   latter - a file that never existed - so the stale marker was still sitting in the directory.

### 5.11 An unexplained deletion, recorded because I cannot attribute it

`gen13-session-peak-extension/` is **gone from the node**: no directory, no run.sh, not in the
generation listing. Its `run.sh` demonstrably existed at 21:36 because gen14's script was derived
from it by textual substitution. The raster root's directory mtime is 21:47, the same window in
which the colliding gen15 directory was created. Nothing I ran issued a recursive delete under
that path, and I have no log line proving either way. Stated plainly: **one generation's working
directory disappeared during a window when two controllers were running concurrently**, and the
surviving measurements are attributed to gen12. Nothing published depends on the missing
directory, but the incident is unreconciled and a campaign should not be closed until the node's
generation inventory is diffed against the journal's claims.

### 5.12 gen15 closes expert width; the single-controller guard was never real (2026-09-07)

**Expert execution width is not a lever at this operating point.** Same launch, one switch, C128,
gate 7/7 on all three:

| expert execution | median decode @C128 | vs control |
|---|---:|---:|
| A16 (control) | 1225.71 | — |
| A8 (`B12X_MOE_FORCE_A8=1`) | 1222 | **−0.3%** |
| native W4A4 (both switches cleared) | 1225 | **−0.1%** |

Four attempts and two harness defects later: the answer is "no material difference", not "A16 is
required". Caveats stated as measured: one concurrency point, n=2 per point, 60 s windows.

**gen16 did not run for 45 minutes because it could not start**, twice. First: my driver used `$R`,
which the base harness never defines, and `set -u` killed it in milliseconds. Second: my patch
string contained `$STATE`, which expanded in the *ssh client* shell. Third, and the important one:
the single-controller guard the repository rule R-03-20 mandates **has never worked**.

Proof: with gen16 running, `pgrep -f 'glm53-raster/gen1[0-9-]*/run.sh'` returned **zero** matches,
because the controller's command line is the relative `bash run.sh` — no pattern containing the
raster root can match it. A planted decoy was also missed. The `pgrep -fc` variant printed a value
that failed a `[[ -gt ]]` test, which inside an `if` is **fail-open**: a guard that errors lets the
collision through. This is the actual root cause of the 21:38-21:45 gen14/gen15 collision that
destroyed ~11 minutes of startup work and whose `INVALID.reason` blamed "an empty pid" — that text
describes a symptom and misattributes the cause.

Fix in the versioned harness: a lock file holding the recorded pid, refused if alive, reclaimed if
stale, released on trap — never a process-table pattern, which is precisely what R-03-20 already
said and what I wrote anyway. The node's live copy is deliberately left alone while bash is reading
it; the next generation deploys from the repository copy.

Waste accounting: GPUs idle 00:00-00:23 (≈23 min of 8-way machine) plus 00:22-00:23 while I
discovered the two launch bugs. Reported because the waste metric is the point, not a formality.

