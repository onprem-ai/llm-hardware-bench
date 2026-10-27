#!/usr/bin/env bash
# Fetch pinned sources and build NCCL/CUDA fabric tools inside a pinned image.
set -euo pipefail
TOOLS_ROOT=${TOOLS_ROOT:-/opt/llm-bench-tools}
IMAGE=${FABRIC_RUNTIME_IMAGE:?set FABRIC_RUNTIME_IMAGE to an immutable digest}
NCCL_TESTS_REV=${NCCL_TESTS_REV:-b4d5beebca8a76cf01335f724d154b9b9d394d96}
CUDA_SAMPLES_REV=${CUDA_SAMPLES_REV:-3f1c50965017932fc81e6d94a3fc9e04c105b312}
mkdir -p "$TOOLS_ROOT" "$TOOLS_ROOT/bin" "$TOOLS_ROOT/receipts"
clone_at(){ local url=$1 dir=$2 rev=$3; if [[ ! -d $dir/.git ]]; then git clone "$url" "$dir"; fi; git -C "$dir" fetch --tags origin; git -C "$dir" checkout --detach "$rev"; test "$(git -C "$dir" rev-parse HEAD)" = "$rev"; }
clone_at https://github.com/NVIDIA/nccl-tests.git "$TOOLS_ROOT/nccl-tests" "$NCCL_TESTS_REV"
clone_at https://github.com/NVIDIA/cuda-samples.git "$TOOLS_ROOT/cuda-samples" "$CUDA_SAMPLES_REV"
uid=$(id -u); gid=$(id -g)
# Python NCCL wheels may ship libnccl.so.2 without the development libnccl.so
# linker name. Build a private prefix that points to the exact wheel payload;
# do not mutate the image or host linker configuration.
mkdir -p "$TOOLS_ROOT/nccl-prefix/include" "$TOOLS_ROOT/nccl-prefix/lib"
docker run --rm --user "$uid:$gid" -v "$TOOLS_ROOT:$TOOLS_ROOT" --entrypoint sh "$IMAGE" -lc \
 'cp /usr/local/lib/python3.12/dist-packages/nvidia/nccl/include/nccl.h '"$TOOLS_ROOT"'/nccl-prefix/include/ && cp /usr/local/lib/python3.12/dist-packages/nvidia/nccl/lib/libnccl.so.2 '"$TOOLS_ROOT"'/nccl-prefix/lib/ && ln -sfn libnccl.so.2 '"$TOOLS_ROOT"'/nccl-prefix/lib/libnccl.so'
docker run --rm --user "$uid:$gid" -v "$TOOLS_ROOT:$TOOLS_ROOT" -w "$TOOLS_ROOT/nccl-tests" --entrypoint sh "$IMAGE" -lc \
 'make -j"$(nproc)" CUDA_HOME=/usr/local/cuda NCCL_HOME='"$TOOLS_ROOT"'/nccl-prefix'
docker run --rm --user "$uid:$gid" -v "$TOOLS_ROOT:$TOOLS_ROOT" -w "$TOOLS_ROOT/cuda-samples" --entrypoint sh "$IMAGE" -lc \
 'nvcc -O3 -std=c++17 -I Common Samples/5_Domain_Specific/p2pBandwidthLatencyTest/p2pBandwidthLatencyTest.cu -o '"$TOOLS_ROOT"'/bin/p2pBandwidthLatencyTest'
for f in "$TOOLS_ROOT"/nccl-tests/build/{all_reduce_perf,all_gather_perf,reduce_scatter_perf} "$TOOLS_ROOT/bin/p2pBandwidthLatencyTest"; do test -x "$f"; printf 'binary=%s\n' "$f"; done > "$TOOLS_ROOT/receipts/binaries.txt"
{
 printf 'built_at=%s\nimage=%s\nnccl_tests_revision=%s\ncuda_samples_revision=%s\n' "$(date -u --iso-8601=ns)" "$IMAGE" "$NCCL_TESTS_REV" "$CUDA_SAMPLES_REV"
 docker image inspect "$IMAGE" --format 'image_id={{.Id}} repo_digests={{json .RepoDigests}}'
} > "$TOOLS_ROOT/receipts/build.txt"
echo "$TOOLS_ROOT"
