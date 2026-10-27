# Bootstrap

Bootstrap is intentionally two-stage:

1. `harness/2-preflight-conformance/code/check-host.sh` is read-only except for creating its output and the
   configured results directory.
2. Installation is performed only after review of `ubuntu-24.04-packages.txt`,
   `requirements.in`, `harness/2-preflight-conformance/RULES.md`, and pinned OCI image digests.

Suggested sequence:

```bash
sudo apt-get update
# Review comments, then install only uncommented applicable package names:
grep -Ev '^[[:space:]]*(#|$)' harness/2-preflight-conformance/code/bootstrap/ubuntu-24.04-packages.txt \
  | xargs sudo apt-get install -y
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r harness/2-preflight-conformance/code/bootstrap/requirements.in
.venv/bin/pip freeze --all > bootstrap/requirements.lock
```

`requirements.in` pins direct dependencies but is not a cross-platform lock.
Freeze and preserve the resolved environment used by each campaign. See
`PIPELINE.md` for the complete workflow.

Driver, Docker, NVIDIA Container Toolkit, DCGM Exporter, and observability
installation must follow vendor instructions and site policy. Their versions
and image digests belong in the host/campaign manifest. This repository does
not run curl-to-shell installers automatically.

Before campaigning, pin and build `NVIDIA/nccl-tests`, capture its commit and
compile command, and install a CUDA P2P bandwidth/latency test.
