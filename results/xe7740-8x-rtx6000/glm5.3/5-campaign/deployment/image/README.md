# Runtime image for the GLM-5.3-NVFP4 measurements

```bash
# decode-wide profile (used above C24)
docker build --build-arg MAX_NUM_SEQS=64 --build-arg GRAPH=256 \
  -t local/radixark-glm53-r18-seq64-graph256:canary .

# narrow profile (decode up to C24, and all prefill)
docker build --build-arg MAX_NUM_SEQS=32 --build-arg GRAPH=128 \
  -t local/radixark-glm53-r18-graph128:canary .
```

## This was thought to be unreproducible. It is not.

The campaign produced these images with `docker commit` on a running container,
and no Dockerfile existed anywhere, so the deployment contract originally
recorded `build_recipe: unrecorded` and warned that pruning the images on
`xe7740-04` would lose the configuration.

That was wrong. The base is a **published, digest-pinned registry image** named
in `journal/2026-08-29-radixark-qualification.md`:

```text
voipmonitor/vllm@sha256:414ec7d0d28358cfd8af0697f330f5c8acbb80e4dc4e5ba69c9fd5b5855ea804
```

Verified on 2026-09-02: that image already contains the whole entrypoint chain
(`serve-infernal-invocation.sh` → `serve-gilded-gnosis.sh` → `serve-glm52-v19.sh`
→ `serve-glm52-v16.sh`) and the exact vLLM build

```text
0.26.1rc0+infernal.invocation.cu133.r18.vllmf0fa1ce.b12x75787c7
```

Comparing base and canary configs, the commit changed only:

- **23 environment variables** (reproduced verbatim in the Dockerfile), and
- **the entrypoint**, from the base default `serve-ds4-flash.sh` (which serves
  DeepSeek-V4-Flash) to `serve-infernal-invocation.sh`.

Nothing was compiled, patched or installed. The custom-looking parts — the b12x
MoE backend, the instanttensor loader, the `infernal.invocation` vLLM — are all
upstream in the base image.

The two measured profiles differ from each other in exactly two variables,
`MAX_NUM_SEQS` and `GRAPH`, which is why they are build args here.

## Caveat on exactness

A rebuild will not match the recorded local digests
(`sha256:c2df5e5bed93…` narrow, `sha256:ce20624ebb70…` wide) because `docker
commit` and `docker build` produce different layer metadata. The resulting
configuration is equivalent; the image is not bit-identical.

## Verify before measuring

`max_num_seqs` is not guaranteed by the environment. Check what vLLM actually
configured, as the campaign did:

```text
max_num_seqs: <profile value>
max_cudagraph_capture_size: <profile value>
num_spec_tokens=3
```

`../launch.sh` performs these checks and exits non-zero on mismatch.
