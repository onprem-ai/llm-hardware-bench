---
kind: rule
step: 1
title: Model qualification rules
absorbs:
  - CLAUDE.md "Hugging Face model downloads" (steps 1-9, moved 2026-09-06)
  - harness/1-model-qualification/RULES.md (whole file)
  - PROCEDURE.md §3 "Required Test Record" -> "Model" subsection
---

# Chapter 1 — Model qualification

Pipeline order, budgets and gates: `PIPELINE.md`. This file owns **how a model gets from
a repository to a qualified, identified local payload**. Consumers: chapter 2 reads the
identity record; chapter 5 copies it into every run manifest; chapter 6 cites it as
provenance. Being consumed does not make another file an owner (`R-PIPE-1`).

Nothing here is about performance. A model that cannot be identified cannot be benchmarked,
because a later "we improved it by X%" has no left-hand side.

## What this chapter produces

A model directory plus two machine-readable artifacts, both required before any
qualification run launches:

| Artifact | Location | Contents |
|---|---|---|
| `remote-inventory.json` | downloader state dir | expected bytes, file list, resolved revision, downloader version |
| `DOWNLOAD_COMPLETE.json` | downloader state dir | atomic receipt: revision, timestamps, local bytes, payload inventory |

## Acquisition

### R-01-1 Resolve the revision to an immutable commit before transferring payload

Never download `main` without resolving it to a commit first. Query metadata and record
before the payload moves: repository ID, requested revision, resolved commit SHA, file
count, expected total bytes, per-file path/size/blob ID/LFS metadata where available,
`huggingface_hub` version, destination path. Write these to `remote-inventory.json`.
Check free disk against expected bytes plus a safety margin.

```python
from huggingface_hub import HfApi
info = HfApi().model_info(repo, revision=revision, files_metadata=True, token=True)
assert info.sha == revision
```

Inspect an existing environment before installing a client; a Python environment
containing `huggingface_hub` is sufficient. Do not modify an active benchmark environment
or install packages during a campaign because a standalone CLI is absent.

### R-01-2 Deterministic dedicated destination, state kept outside the payload

Destination: `$HOME/models/<organization>--<model>--model/`. Downloader state and logs go
in a sibling directory (`$HOME/models/<model>-download/`), never inside the payload. Do
not reuse a destination that holds a different repository or revision.

### R-01-3 Resumable download, no deprecated flags

Use `snapshot_download(repo_id=..., revision=<resolved commit>, local_dir=..., token=True,
max_workers=8)`. Modern `huggingface_hub` resumes from its own local metadata; do not set
deprecated `resume_download` options. Use moderate concurrency unless storage and network
have been qualified for more.

### R-01-4 Credentials are never materialised in arguments or logs

Use `token=True` or the existing token store. Never print, persist, or pass the token as a
command-line argument. Never log signed URLs or authorization headers. Report only whether
authentication is configured, never its value.

### R-01-5 Verify a detached download actually started

Run long downloads under `tmux`, `systemd-run`, or `nohup`, then confirm process state,
log growth, destination byte growth and free disk. A progress bar can sit still for many
minutes while shards transfer: check bytes, not percentage.

### R-01-6 Completion is explicit and atomic

The absence of a process does not prove success. Write `DOWNLOAD_COMPLETE.json.tmp` and
rename it into place only after `snapshot_download` returns successfully. The receipt must
carry: repository and requested/resolved revision, start and completion timestamps,
destination, local file count and total bytes, local payload inventory, downloader version.
**No receipt means the download is incomplete or unverified.**

### R-01-7 Structural validation precedes qualification

Before any performance run:

1. resolved revision equals requested revision;
2. expected remote files and sizes match local payload files;
3. every shard referenced by a safetensors index exists;
4. every safetensors header parses and its final offset equals the file size;
5. index tensor keys equal shard-header keys.

Structural completeness is not cryptographic equivalence; say so when reporting.

### R-01-8 Restart safely

Rerun the same script with the same repository, revision and destination. Do not delete
partial files unless corruption has been demonstrated. Before restarting, confirm no prior
downloader is still active and that the destination belongs to the same revision.

## Identity

### R-01-9 These model identity fields are mandatory in every run manifest

Repository and model ID; exact revision or commit SHA; architecture; total and active
parameters; quantization format; weight size on disk; weight tensors left at higher
precision; tokenizer revision; chat template revision; MTP / speculative-decoding
configuration.

These are copied verbatim into the per-run manifest by chapter 5. A run whose manifest
cannot state which weights it served is not evidence about those weights.

### R-01-10 Provenance gaps are recorded, never repaired by invention

If the upstream receipt is unavailable, record the state as-is (for example
`local-unverified`) and carry that label into the report. Do not invent an upstream
revision, backfill a hash, or infer a commit from a file listing. A known gap in
provenance is a finding; a fabricated one destroys every other claim in the campaign.

## Checksums

### R-01-11 Checksums are generated only for downloaded model data

That includes model shard files, tokenizer/configuration files delivered with a snapshot,
and the download inventory or completion receipt needed to verify those bytes.

### R-01-12 Checksums are not generated, required, published, or highlighted for

benchmark campaign manifests or run outputs; telemetry exports or collector snapshots; idle
baselines; fabric qualification output; generated reports, templates or report inputs;
repository source files or locally built benchmark tools.

Campaign evidence stays auditable through immutable paths, explicit source references,
timestamps, run IDs, recorded commands, frozen configuration copies, completion markers
and version-control history — not through hashes of our own outputs.

Existing checksum files in already-finalized external campaigns may remain as historical
records. They are not required by this protocol and must not be copied forward as a
requirement.

### R-01-13 External identifiers are not output checksums

Recording identifiers supplied by external artifact systems is required, not prohibited:
an OCI image digest pinning the runtime image, a Git commit ID pinning source, a Hugging
Face revision pinning a model repository. These identify external inputs. The framework
must not compute or present SHA-256 values for benchmark or report outputs.

## Exit gate — entering chapter 2

- [ ] resolved revision recorded and equal to the requested immutable revision (`R-01-1`)
- [ ] `DOWNLOAD_COMPLETE.json` present, atomically written, receipt fields complete (`R-01-6`)
- [ ] structural validation passed or its limits explicitly recorded (`R-01-7`)
- [ ] all `R-01-9` identity fields available to the campaign spec
- [ ] any provenance gap recorded under its real label, and no invented identifier anywhere (`R-01-10`)

## Sources

Rule IDs assigned 2026-09-06 during the pipeline extraction. `R-01-1`..`R-01-8` and the
checksum policy existed as text in `CLAUDE.md` and `harness/1-model-qualification/RULES.md` with no
chapter owner, which is why the same procedure had to be re-derived from memory twice.
`R-01-10` is new and comes from the DeepSeek-V4-Flash case on this host: the upstream
immutable revision and receipt were unavailable, the payload is labelled
`local-unverified`, and the alternative — asserting a revision we never observed — would
have made every DeepSeek number unverifiable after the fact.

## Sub-step budgets

One budget per sub-step: **wall-clock minutes**. B = blocking, charged in full;
O = off-path, must be scheduled inside a measurement window. Rules and breach protocol: `PIPELINE.md`.

| Sub-step | Owner | Path | Budget |
|---|---|---|---|
| pin revision, inventory | mech | B | 10m |
| structural validation (headers, offsets, shard keys, hashes) | mech | B | 15m |
| load canary: one startup, no benchmark | mech | B | 20m |
| correctness battery (stub first, then live) | mech | B | 15m |
| provenance adjudication | **agent** | O | 15m |
