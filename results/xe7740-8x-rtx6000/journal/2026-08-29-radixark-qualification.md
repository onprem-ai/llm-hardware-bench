# RadixArk full GLM-5.3 qualification — 2026-08-29

Candidate:

```text
RadixArk/GLM-5.3-NVFP4@363e8f086905afd83db356a620f9aa401c23800a
```

## Completed gates

- Download completed: 58 files, 464,874,334,135 bytes.
- All 49 files with upstream Hugging Face LFS SHA-256 metadata matched.
- Nine remaining metadata/configuration files were locally hashed.
- Safetensors audit passed: 47 shards, 232,385 indexed/header tensors, no
  missing/unindexed tensors, and no file-size/final-offset errors.
- ModelOpt structure verification passed: 57,600 routed expert projections use
  NVFP4 companions in layers 3–77; layer 78 has 791 high-precision tensors and
  no NVFP4 companions.
- TP8, MTP disabled, 262K loader canary passed and completed a chat request.
- TP8, MTP3, 262K loader canary passed. A real chat request returned the exact
  requested text and `/health` remained 200.
- Promoted qualification settings (`max_num_seqs=32`, graph cap 64) loaded and
  became healthy. Startup reported 584,320 FP8 KV-cache tokens and 2.23×
  theoretical concurrency for a full 262,144-token request.

Pinned runtime:

```text
voipmonitor/vllm@sha256:414ec7d0d28358cfd8af0697f330f5c8acbb80e4dc4e5ba69c9fd5b5855ea804
vLLM 0.26.1rc0+infernal.invocation.cu133.r18.vllmf0fa1ce.b12x75787c7
```

## Active qualification

A one-repetition, ten-point qualification sweep is running under:

```text
/home/demouser/llm-benchmark-results/xe7740-04/glm-5.3-nvfp4/363e8f086905/r1-tp8-dcp1-mtp3-seq32-b8192-r18/20260829-full-glm53-radixark-qualification
```

Profiles/points:

- Decode: C1, C32, C64, C128
- Prefill: C32, C64, C128
- Balanced: C32, C64, C128

This is qualification, not the formal repeated campaign. The first randomized
point is decode C128; its warm-up is intentionally large because the policy uses
`2 × concurrency` requests with 768 requested output tokens while the server
has 32 active sequence slots.

The campaign runner initially rejected the literal JSON `--extra-inputs`
argument because braces were interpreted as placeholders. No benchmark request
ran in that failed attempt. The generic expander was corrected to substitute
only `{identifier}` tokens and a regression test was added before restart.
