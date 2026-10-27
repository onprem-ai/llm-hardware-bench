# 2026-09-24 — GLM-5.3 NVFP4 corrected-cold grid campaign (glm53-coldgrid-20260924)

Host: comino-8xrtx6000. Model: RadixArk/GLM-5.3-NVFP4 @ 363e8f086905afd83db356a620f9aa401c23800a
(ModelOpt NVFP4 W4A4 routed experts layers 3-77, BF16 MTP layer 78).

## Contract

Frozen before measurement by user decision: Dell xe7740-04 deployment parameters
verbatim (param raster skipped), corrected-cold AIPerf invocation, and the
published 7-point axis [1, 8, 16, 24, 32, 48, 64] x {decode, prefill} x 3 reps.
The contract is recorded in the tracked controller
`results/comino-8x-rtx6000/raster-harness/run-coldgrid.sh` and in the
report-config provenance notes. Corrected-cold means: `--num-dataset-entries
4000 --dataset-sampling-strategy sequential`, per-(C,rep) seeds 600000+C*1000+rep,
disjoint warmup pools (953601 decode / 953602 prefill, request-count max(C,32)),
60 s windows with grace inf, and a fail-closed engine-side prefix-cache gate
(served <= 1%) around every rep.

## Deployment

One TP8 vLLM replica across all 8 GPUs behind haproxy (single backend, frontend
127.0.0.1:8084 -> engine 127.0.0.1:8080, prometheus metrics on 127.0.0.1:8404).
A profile IS an image: the two measured images are docker-commit canaries
imported from the xe7740-04 study by image export —
`local/radixark-glm53-r18-graph128:canary` (sha256:d45401bef457..., commit layer
ENV MAX_NUM_SEQS=32 GRAPH=128) and `local/radixark-glm53-r18-seq64-graph256:canary`
(sha256:1e53276a801b..., commit layer ENV MAX_NUM_SEQS=64 GRAPH=256) on base
`voipmonitor/vllm@sha256:414ec7d0d28358cfd8af0697f330f5c8acbb80e4dc4e5ba69c9fd5b5855ea804`
(vLLM 0.26.1rc0+infernal.invocation.cu133.r18.vllmf0fa1ce.b12x75787c7, b12x MoE
backend, InstantTensor loader). Decode splices the two profiles at the C24/C32
boundary exactly like the published xe7740-04 series (two container launches).

Realized args were verified from each boot's startup log before any measurement
(max_num_seqs, cudagraph capture size, MTP-3 speculative tokens, TP8, batched
tokens 8192, KV fp8, modelopt_fp4, InstantTensor, prefix caching on) — recorded
per launch in `segments/*/params.txt`. First boot ~3 min cache-warm (433 GiB
InstantTensor load in 38 s at 11.4 GB/s from warm page cache; the Gen4 root NVMe
bounds a true cold boot). Correctness gate 7/7 through the measured path after
each boot; B1-pre and B1-post loaded-idle baselines captured (300 s each).

## Campaign

42/42 runs complete (14 points x 3 reps), 0 AIPerf errors, 0 excluded runs,
COMPLETE 2026-09-24T20:52:56Z. All 42 prefix-cache gates passed at 0.0% served
(fail-closed <= 1%). Evidence:
`results/comino-8x-rtx6000/glm5.3/5-campaign/glm53-coldgrid-20260924/`
(manifests, per-rep artifacts + telemetry slices, baselines, gates, SHA256SUMS).

## Results (medians of 3 reps)

Decode (output tokens/s, 8-in/768-out): C1 103.96, C8 368.62, C16 539.51,
C24 700.54, C32 793.83, C48 982.49 (peak), C64 937.99.

Prefill, cold-uncached (input tokens/s, 2048-in/8-out): C1 3194.92, C8 5313.52,
C16 6043.67, C24 6229.01, C32 6253.29, C48 6259.77, C64 6260.40.

## Cross-host deltas (validated in 6-acceptance)

- Decode C48 982.49 is +5.94% over the xe7740-04 published decode headline
  (comparator `glm5.3.decode.published-headline`, 927.37 @ C48) — same point,
  same profile family, both corrected-cold.
- Decode peak vs the xe7740-04 cold decode peak: -20.37% (comparator
  `glm5.3-cold-20260909.decode.published-headline`, 1233.88 @ C128) —
  cross-axis by contract: this campaign measured the published 7-point axis
  (max C64), the xe7740-04 cold campaign ran to C192.
- Prefill ceiling parity: 6260.40 at C64 is +0.36% over the xe7740-04
  corrected-cold prefill peak (comparator
  `glm5.3-cold-20260909.prefill.published-headline`, 6238.18 @ C160) —
  plateau parity of the prefill ceiling, not a point comparison.
- No prefill delta may be stated against the published prefill headline
  (`glm5.3.prefill.published-headline`): that series is cache-served
  (65-89% prefix-cache reads) and is forbidden as a cold comparator.

Claims: `results/comino-8x-rtx6000/glm5.3/6-acceptance/claims-coldgrid-20260924.yaml`
and `...-prefill.yaml` (all PASS, validate_claims.py).
