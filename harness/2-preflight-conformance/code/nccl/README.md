# NCCL fabric qualification

`run-matrix.py` executes a declared matrix of GPU groups, CPU/NUMA policies, and
NCCL collectives inside an immutable runtime image. `parse-results.py` preserves
all message-size rows and calculates large-message medians.

Build pinned tools first:

```bash
export FABRIC_RUNTIME_IMAGE='<image>@sha256:<digest>'
export TOOLS_ROOT="$HOME/llm-bench-tools"
harness/2-preflight-conformance/code/bootstrap/build-fabric-tools.sh
```

Dry-run and execute:

```bash
python3 harness/2-preflight-conformance/code/nccl/run-matrix.py <matrix.json> \
  --output "$FABRIC_CAMPAIGN/nccl-matrix" --dry-run
python3 harness/2-preflight-conformance/code/nccl/run-matrix.py <matrix.json> \
  --output "$FABRIC_CAMPAIGN/nccl-matrix"
python3 harness/2-preflight-conformance/code/nccl/parse-results.py "$FABRIC_CAMPAIGN/nccl-matrix"
```

## NUMA policy

When `cpu_node` is present, the runner resolves the host's actual node CPU list
from sysfs and invokes `numactl --physcpubind ... --membind ...` inside a
privileged, ephemeral test container. This avoids a known class of NVIDIA OCI
hook failures caused by Docker `--cpuset-*` GPU-container constraints while
still applying and recording both process affinity and memory policy.

Privileged mode is used only for explicit memory-policy cases and requires an
approved idle qualification window. Unpinned cases are not privileged.

## Interpretation

- `algbw` is operation size divided by operation time.
- `busbw` applies the NCCL collective correction factor.
- Neither is a direct PCIe-link-utilization percentage.
- Keep an `NCCL_DEBUG=INFO` run for algorithm/topology attribution separate
  from clean numeric runs because asynchronous debug lines can interleave with
  table rows.
- Always preserve correctness columns and raw logs.
