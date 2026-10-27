# Runtime image for the GLM-5.3-NVFP4 measurements on xe7740-04.
#
# The campaign built this by committing a running container:
#
#   docker commit --pause --change 'ENV MAX_NUM_SEQS=64' --change 'ENV GRAPH=256' \
#     radixark-glm53-graph128 local/radixark-glm53-r18-seq64-graph256:canary
#
# That looked unreproducible, but it is not: the commit changed only the
# environment and the entrypoint. Everything else -- the vLLM build, the b12x
# backend, the instanttensor loader and the four-level entrypoint chain -- comes
# from the published base image below, which was verified to contain
# serve-infernal-invocation.sh, serve-gilded-gnosis.sh, serve-glm52-v19.sh,
# serve-glm52-v16.sh, and vLLM
# 0.26.1rc0+infernal.invocation.cu133.r18.vllmf0fa1ce.b12x75787c7.
#
# The two measured profiles differ in exactly two variables.
#
# Build the decode-wide profile (used above C24):
#   docker build --build-arg MAX_NUM_SEQS=64 --build-arg GRAPH=256 \
#     -t local/radixark-glm53-r18-seq64-graph256:canary .
#
# Build the narrow profile (decode up to C24, and all prefill):
#   docker build --build-arg MAX_NUM_SEQS=32 --build-arg GRAPH=128 \
#     -t local/radixark-glm53-r18-graph128:canary .

FROM voipmonitor/vllm@sha256:414ec7d0d28358cfd8af0697f330f5c8acbb80e4dc4e5ba69c9fd5b5855ea804

# The only two values that vary between the measured profiles.
ARG MAX_NUM_SEQS=64
ARG GRAPH=256

# The base image's default entrypoint serves DeepSeek-V4-Flash. Select the GLM
# path; the dispatcher is already present in the base.
ENTRYPOINT ["/usr/local/bin/serve-infernal-invocation.sh"]

# The entrypoint chain reads these and builds the vLLM invocation from them.
# There is no command line to override.
ENV MODEL=/model \
    SERVED_MODEL_NAME=glm-5.3-nvfp4-radixark \
    MODEL_FAMILY=glm52 \
    GPUS=0,1,2,3,4,5,6,7 \
    TP=8 \
    DCP=1 \
    MTP=3 \
    PORT=8080 \
    MAX_MODEL_LEN=262144 \
    MAX_BATCHED_TOKENS=8192 \
    GPU_MEMORY_UTILIZATION=0.95 \
    QUANTIZATION=modelopt_fp4 \
    QUANTIZATION_CONFIG_JSON='{"linear":{"weight":"mxfp8"}}' \
    ONLINE_QUANT=mxfp8 \
    KV_CACHE_DTYPE=fp8 \
    LOAD_FORMAT=instanttensor \
    INSTANTTENSOR_BACKEND=BUFFERED \
    MOE_BACKEND=b12x \
    MOE_MODE=a16 \
    F8_DMA=ring

ENV MAX_NUM_SEQS=${MAX_NUM_SEQS} \
    GRAPH=${GRAPH}
