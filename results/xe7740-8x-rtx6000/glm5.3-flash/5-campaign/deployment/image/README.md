# Runtime image for the GLM-5.3-Flash-NVFP4 measurements

Vendored so this repository alone is sufficient to rebuild the runtime the
published numbers were measured on.

```bash
docker build -t local/vllm-glm53-flash:sm120-v8 .
```

Base is public: `vllm/vllm-openai:glm53-flash-x86_64-cu130`.

The image measured on `xe7740-04` was `local/vllm-glm53-flash:sm120-v8`, local
digest `sha256:744e620fbed6c979937e64f69534dd64150334549c39b5f8e64da6f1c9ff9588`.
It was never pushed to a registry, so a rebuild will not reproduce that digest
bit-for-bit — the FlashInfer nightly pinned in step 2 is a dated build and the
patches apply to whatever the base image currently ships.

## Layer order is load-bearing

Flattened from a seven-stage chain, kept as ordered layers:

| Step | Purpose |
|---|---|
| 1 | Extend FlashInfer's SM90 NoPE sparse-MLA backend to capability 12; FA2 off-Hopper |
| 2 | FlashInfer 0.6.18 nightly — 0.6.17's FA2 MLA returns NaN for 64-256-row batches |
| 3 | Restore `nvidia-nccl-cu13==2.30.7`, which step 2 downgrades and breaks `ncclCommInitRank` |
| 4 | Restore `nvidia-cutlass-dsl==4.6.2`, which step 2 leaves in a mixed state that ICEs CuTeDSL warmup |
| 5 | Gate PDL off SM12x — it races on the Triton KDA state kernels there |
| 6 | Indexer hardening: uninitialized top-k pool ids produced a second NaN class |
| 7 | Cap `CTA_TILE_KV` on the fp8 KV path rather than forcing a Hopper-sized tile |

**Do not merge or reorder these.** Steps 3 and 4 exist only to repair what step 2
breaks.

Each patch asserts its exact source line is present before replacing it, so a
change in the base image fails the build loudly instead of yielding a quietly
unpatched runtime.

## Naming caution

The original chain tagged intermediate stages `sm121`, targeting GB10 / DGX
Spark; only the final stage was retargeted to `sm120`. The patches are
capability-12-generic, but an `sm121`-tagged image from that chain was never
qualified on RTX 6000 Blackwell.

## Also in the catalog

The same recipe is maintained as a catalog image build at
`p009_ai_node/app/backend/catalog/rtx6k/_docker/vllm-glm53-flash-sm120/`, whose
target is the published name `onpremai/vllm-glm53-flash:sm120-v8`. The two
copies are byte-identical; if you change one, change both.
