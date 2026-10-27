# vLLM for GLM-5.3-Flash-NVFP4 on SM12x (RTX PRO 6000 Blackwell / GB10).
#
# Flattened from the seven-stage build that produced the benchmarked image
# local/vllm-glm53-flash:sm120-v8 on xe7740-04. The stages are kept as separate
# RUN layers in their original order, with their original reasoning, because
# several of them undo damage caused by the stage before.
#
# Build:
#   docker build -t onpremai/vllm-glm53-flash:sm120-v8 .

FROM vllm/vllm-openai:glm53-flash-x86_64-cu130

# ---------------------------------------------------------------------------
# 1. NoPE sparse-MLA on capability 12.
#
# GLM-5.3-Flash is glm5_next with NoPE MLA (qk_rope_head_dim=0). The base
# image's only capability-12 sparse-MLA backend is FLASHINFER_MLA_SPARSE_SM120,
# whose packed fp8_ds_mla cache layout hard-requires DeepSeek's pe_dim=64 and
# dies in warmup ("pe_dim must be 64 for fp8_ds_mla"). The SM90 NoPE backend
# (FlashInfer BatchMLAPagedAttentionWrapper, plain bf16 cache) supports kpe=0
# and its FA2 path passes a direct probe with GLM's real shape (32 heads/rank,
# ckv 512, kpe 0, page_size 1). Extend it to capability 12, select FA2
# off-Hopper, and scope the FlashInfer>=0.6.18 feature gate to the fp8-cache
# path it actually protects.
# ---------------------------------------------------------------------------
RUN python3 - <<'PY'
from pathlib import Path

base = Path("/usr/local/lib/python3.12/dist-packages/vllm")

p = base / "platforms/cuda.py"
s = p.read_text()
old = """        elif device_capability.major == 12:
            return [
                AttentionBackendEnum.TRITON_MLA,
                AttentionBackendEnum.FLASHINFER_MLA_SPARSE_SM120,
            ]"""
new = """        elif device_capability.major == 12:
            return [
                AttentionBackendEnum.TRITON_MLA,
                AttentionBackendEnum.FLASHINFER_MLA_SPARSE_SM90,
                AttentionBackendEnum.FLASHINFER_MLA_SPARSE_SM120,
            ]"""
if s.count(old) != 1:
    raise SystemExit("unexpected cuda.py capability-12 MLA candidate list; refusing to patch")
p.write_text(s.replace(old, new))

p = base / "v1/attention/backends/mla/flashinfer_mla_sparse_sm90.py"
s = p.read_text()

old = "    def supports_compute_capability(cls, capability: DeviceCapability) -> bool:\n        return capability.major == 9\n"
new = "    def supports_compute_capability(cls, capability: DeviceCapability) -> bool:\n        return capability.major in (9, 12)\n"
if s.count(old) != 1:
    raise SystemExit("unexpected sm90 capability gate; refusing to patch")
s = s.replace(old, new)

old = '            backend="fa3",\n'
new = '            backend=("fa3" if torch.cuda.get_device_capability()[0] == 9 else "fa2"),\n'
if s.count(old) != 1:
    raise SystemExit("unexpected sm90 wrapper backend literal; refusing to patch")
s = s.replace(old, new)

old = """        if not has_flashinfer_sm90_nope_mla():
            return (
                "FLASHINFER_MLA_SPARSE_SM90 requires FlashInfer with SM90 "
                "MLA support (ckv_scale_arr in "
                "BatchMLAPagedAttentionWrapper.run, FlashInfer >= 0.6.18)"
            )"""
new = """        if kv_cache_dtype in ("fp8", "fp8_e4m3") and not has_flashinfer_sm90_nope_mla():
            return (
                "FLASHINFER_MLA_SPARSE_SM90 fp8 KV requires FlashInfer with "
                "SM90 MLA support (ckv_scale_arr in "
                "BatchMLAPagedAttentionWrapper.run, FlashInfer >= 0.6.18)"
            )"""
if s.count(old) != 1:
    raise SystemExit("unexpected sm90 flashinfer version gate; refusing to patch")
s = s.replace(old, new)

p.write_text(s)
print("capability-12 NoPE MLA patches applied")
PY

# ---------------------------------------------------------------------------
# 2. FlashInfer 0.6.18 nightly.
#
# 0.6.17's FA2 MLA kernel produces NaN for 64-256-row batches (probed and
# bisected; 1-6 and 512+ rows are clean). 0.6.18 fixes it and is also the
# version whose SM90 NoPE MLA support is official. The 0.6.17 AOT jit-cache is
# removed so no stale prebuilt kernels load against the new package; everything
# JIT-compiles instead.
# ---------------------------------------------------------------------------
RUN pip install -q --pre \
      flashinfer-python==0.6.18.dev20260819 \
      flashinfer-cubin==0.6.18.dev20260819 \
      --extra-index-url https://flashinfer.ai/whl/nightly/ \
    && pip uninstall -q -y flashinfer-jit-cache \
    && python3 -c "import flashinfer; print('flashinfer', flashinfer.__version__)"

# ---------------------------------------------------------------------------
# 3. Restore NCCL.
#
# The FlashInfer nightly silently downgrades nvidia-nccl-cu13 2.30.7 -> 2.29.7,
# which fails ncclCommInitRank with an internal error. Restore the qualified
# version. Must come after step 2.
# ---------------------------------------------------------------------------
RUN pip install -q nvidia-nccl-cu13==2.30.7 \
    && pip show nvidia-nccl-cu13 | grep -q "Version: 2.30.7" && echo NCCL-RESTORED

# ---------------------------------------------------------------------------
# 4. Restore cutlass-dsl.
#
# The same nightly bumps nvidia-cutlass-dsl into a mixed 4.7.0/4.6.2 state,
# ICEing the CuTeDSL warmup (cute-to-nvvm). Restore the 4.6.2 family the image
# was qualified with; the FA2 MLA path does not use cutlass-dsl.
# ---------------------------------------------------------------------------
RUN pip install -q nvidia-cutlass-dsl==4.6.2 \
    && pip show nvidia-cutlass-dsl | grep -q "Version: 4.6.2" && echo DSL-RESTORED

# ---------------------------------------------------------------------------
# 5. Gate PDL off SM12x.
#
# Programmatic Dependent Launch is enabled for any capability >= 9 in the Triton
# kernels carrying KDA recurrent state (causal_conv1d, gather_initial_states,
# scatter_states). On SM12x this produces a timing-dependent read-before-store
# race: boots NaN or not depending on launch timing, and full-device-sync debug
# hooks reliably mask it. Restrict PDL to the arches it was validated on.
# ---------------------------------------------------------------------------
RUN python3 - <<'PY'
from pathlib import Path

p = Path("/usr/local/lib/python3.12/dist-packages/vllm/platforms/cuda.py")
s = p.read_text()
old = """    @classmethod
    def is_arch_support_pdl(cls) -> bool:
        try:
            device = torch.cuda.current_device()
            major, _ = torch.cuda.get_device_capability(device)
        except Exception:
            return False
        return major >= 9
"""
new = """    @classmethod
    def is_arch_support_pdl(cls) -> bool:
        try:
            device = torch.cuda.current_device()
            major, _ = torch.cuda.get_device_capability(device)
        except Exception:
            return False
        # PDL lowering is unvalidated on SM12x and races on KDA state kernels
        # there; keep it to Hopper/Blackwell-datacenter.
        return major in (9, 10)
"""
if s.count(old) != 1:
    raise SystemExit("unexpected is_arch_support_pdl source; refusing to patch")
p.write_text(s.replace(old, new))
print("PDL gated off on SM12x")
PY

# ---------------------------------------------------------------------------
# 6. Indexer hardening (second NaN class).
#
# The top-k destination was torch.empty and the top-k kernels only guarantee the
# first min(k, valid) entries, so rows with fewer valid pools carried
# uninitialized pool ids -> bogus token indices -> MLA gathers uninitialized KV
# -> NaN lottery. Initialize to -1 and clamp the expansion.
# ---------------------------------------------------------------------------
COPY patch_v7.py /tmp/patch_v7.py
RUN python3 /tmp/patch_v7.py && rm /tmp/patch_v7.py

# ---------------------------------------------------------------------------
# 7. fp8 KV cache on the FA2 NoPE sparse-MLA path.
#
# The fp8 branch forces CTA_TILE_KV=32, a Hopper 228KB-smem assumption. On
# smaller-smem devices that doubles the tile chosen by DISPATCH_SMEM_CONFIG and
# over-requests shared memory, failing cudaFuncSetAttribute with "invalid
# argument". Cap rather than force.
# ---------------------------------------------------------------------------
COPY patch_v8_fp8.py /tmp/patch_v8_fp8.py
RUN python3 /tmp/patch_v8_fp8.py && rm /tmp/patch_v8_fp8.py
