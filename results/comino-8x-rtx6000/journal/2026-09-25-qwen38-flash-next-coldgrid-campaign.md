# 2026-09-25 — Qwen3.8-Flash-Next NVFP4 corrected-cold grid campaign (qwen38-coldgrid-20260924)

Host: comino-8xrtx6000. Model: RadixArk/Qwen3.8-Flash-Next-NVFP4 @
7b719225242aacd3dbd3f9407468c2ee9a9d2594 (Qwen4ExpForConditionalGeneration,
compressed QSA, page_size pinned 64).

## Payload acquisition

419/419 files transferred, validation PASS: 206/206 safetensors shards, zero
trailing bytes after the final shard, receipt
`~/bench/models/qwen38-flash-next-download/DOWNLOAD_COMPLETE.json` (box-side).
Revision resolved to the commit before transfer.

## SM120 engine patch (re-derivation of the xe7740-04 edit)

The pinned base `lmsysorg/sglang:qwen38flashnext` (OCI index digest
sha256:12d3392bdc8be8d35e9a95f191df6aef99c5114bdbefd41bfdc7e760e6d25ec1,
SGLang base commit d91c3682b0b429e4c70df63cd57f819588ce29b0) lacks SM120 support
in the TRT-LLM QSA decode path — the xe7740-04 study documented the same gap and
patched it without recording a build recipe.

First patch attempt hit dead legacy code (`server_args.py` guard is not on the
live path): the fleet booted and then crashed with the xe7740-04-documented
MLIRError FA4/CuTe symptom. The live guard is
`qwen_sparse_attn_backend.py::_resolve_trtllm_sparse_decode()`. The correct edit
is one file: widen the import to `is_sm100_supported, is_sm120_supported` and
the guard from SM100-only to SM100-or-SM120; the server_args.py edit was
reverted. Final image `local/qwen38-flash-next-sm120:comino-patched`
(sha256:140c48fe3265...) carries exactly one edited file, verified against the
base image. Unlike the xe7740-04 image, this build recipe is recorded and
reproducible.

## Container launch chain (four fixes, each observed as a failure first)

1. Image ENTRYPOINT intercepted the launcher -> `--entrypoint bash` (bare
   launch scripts exec sglang directly).
2. Replicas bind 127.0.0.1 inside the container network namespace, which
   published-port mapping cannot reach -> `--network host` (drop `-p`).
3. Host networking alone dropped shared memory: NCCL unhandled system error ->
   `--ipc host` (host network is not host IPC).
4. Controller logging died with its process substitution -> `exec >> controller.log`.

## Deployment (Dell xe7740-04 recipe verbatim)

4 independent TP2 replicas on GPU pairs (0,1) (2,3) (4,5) (6,7), ports
8101-8104, behind haproxy 3.2-alpine leastconn (frontend 127.0.0.1:8000,
prometheus metrics on 127.0.0.1:8404). Two profile-specific fleet launches:
decode-optimized (max_running_requests 48, max_prefill_tokens 32768, chunked
4096, mamba cache 240, cuda-graph-bs 48, NEXTN 3/1/4, radix on, ISL 8 / OSL 512)
and prefill-optimized-uncached (24 / 65536 / 16384, mamba 120, graph 24, no
spec, --disable-radix-cache, ISL 4096 / OSL 8). In-container launch scripts
tracked verbatim at `results/comino-8x-rtx6000/raster-harness/qwen/{decode,prefill}-launch.sh`.

Correctness gate 7/7 through the measured path after each fleet boot; B1-pre
and B1-post baselines captured.

## Campaign

48/48 runs complete (16 points x 3 reps) on the xe7740-04 published 8-point
axis [1, 32, 64, 96, 128, 160, 192, 224], corrected-cold invocation as in the
GLM campaign, COMPLETE 2026-09-25T07:07:20Z. 0 AIPerf errors, 0 gate failures:
every prefill rep measured client-side `usage_prompt_cache_read_tokens == 0`
(radix disabled by launch flag as well); decode runs radix-on by design (ISL 8,
recorded, not gated). Evidence:
`results/comino-8x-rtx6000/qwen3.8-flash-next/5-campaign/qwen38-coldgrid-20260924/`.

## Results (medians of 3 reps)

Decode (output tokens/s, 8-in/512-out): C1 191.01, C32 3117.97, C64 4597.50,
C96 5559.76, C128 6426.72, C160 6929.40, C192 7556.55, C224 7679.49 (peak).

Prefill, uncached (input tokens/s, 4096-in/8-out): C1 11872.06, C32 62549.07,
C64 64738.63 (peak), C96 61883.39, C128 61991.18, C160 61873.40, C192 61723.61,
C224 61638.46.

## Cross-host deltas (validated in 6-acceptance)

- Decode C224 7679.49 is +25.60% over the xe7740-04 published decode headline
  (comparator `qwen3.8-flash-next.decode.published-headline`, 6114.29 @ C224) —
  identical deployment recipe on the same GPU model.
- Decode C32 3117.97 is +20.15% (comparator `qwen3.8-flash-next.decode.xe7740-c32`).
- Prefill peak 64738.63 (C64) is +4.29% over the xe7740-04 prefill headline
  (comparator `qwen3.8-flash-next.prefill.published-headline`, 62073.80 @ C224) —
  cross-configuration; the finding is plateau parity, comino holding 61.6-62.0k
  flat from C96 to C224, i.e. the ~62k prefill ceiling is scheduler/software
  bound rather than host bound.
- Prefill C32 62549.07 is +8.44% (comparator `qwen3.8-flash-next.prefill.xe7740-c32`).

Claims: `results/comino-8x-rtx6000/qwen3.8-flash-next/6-acceptance/claims-coldgrid-20260924.yaml`
and `...-prefill.yaml` (all PASS, validate_claims.py).
