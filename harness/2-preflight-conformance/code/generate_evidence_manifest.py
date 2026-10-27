#!/usr/bin/env python3
"""Generate the local evidence cache manifest from the cache as it actually is.

The manifest used to be hand-written, and hand-written manifests rot: it described directories
that had been split apart, it was once written to the wrong path (inside the ignored cache, where
no one would ever look), and the checker accepted it because the directory name appeared inside an
unrelated path string. Everything above the sentinel below is generated from the filesystem, so a
row cannot survive the deletion of its directory and a directory cannot exist without a row.

Everything below MANIFEST_SENTINEL is hand-written prose and is preserved verbatim.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

MANIFEST_SENTINEL = "## Hand-written notes"
UTC = dt.timezone.utc

HEADER = """---
kind: record
produced_by: 2
title: Local evidence cache manifest
---

"""

INTRO = """Raw per-run evidence is too large and too noisy for git, so it lives in an ignored directory
next to the studies it supports. The tree **mirrors the record layout** - `<host>/<model>/<n-step>/` -
so a number in `results/<host>/<model>/<n-step>/` has a same-named cache directory beside it.

Location: `results/<host>/_local-evidence/`, ignored by the root `.gitignore`. Enforced by
`harness/check_repo.py`: an undeclared cache or a subtree missing from this manifest is a
violation, as is any tracked file over 5 MiB, a cache directory reusing a repository name at host
or model level, and a step level that is not `N-step`. Each moved directory carries
`PROVENANCE.txt`.

**This table is generated from the filesystem** by
`harness/2-preflight-conformance/code/generate_evidence_manifest.py`. A row that does not exist on
disk is a checker violation, so this file cannot outlive what it describes.
"""


def human(nbytes: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} PiB"


def describe(path: str) -> str:
    parts = path.split("/")
    if any(part.startswith("_unsorted") for part in parts):
        return "pulled before the cache had a shape; not mapped to a step"
    if any(part.startswith("_retired") for part in parts):
        return "archived copy of something removed from the deliverable tree"
    if len(parts) >= 3:
        return "step evidence, mirrors the record layout"
    if len(parts) == 2:
        return "model-level evidence root"
    return "host-level loose files (no model or step directory)"


def scan(cache: pathlib.Path):
    """Bucket every file by its path at depth <= 3, counting each file exactly once."""
    buckets: dict[str, dict] = {}
    total_files = 0
    for f in sorted(x for x in cache.rglob("*") if x.is_file()):
        total_files += 1
        rel = f.relative_to(cache)
        key = "/".join(rel.parts[:3]) if len(rel.parts) > 3 else "/".join(rel.parts[:-1]) or "(loose files)"
        b = buckets.setdefault(key, {"n": 0, "size": 0, "ts": []})
        st = f.stat()
        b["n"] += 1
        b["size"] += st.st_size
        b["ts"].append(st.st_mtime)
    counted = sum(b["n"] for b in buckets.values())
    if counted != total_files:  # generated totals must not silently double-count
        raise SystemExit(f"manifest totals disagree: {counted} bucketed vs {total_files} files")
    return buckets, total_files


def render(cache: pathlib.Path, manifest: pathlib.Path, previous: str) -> str:
    buckets, total_files = scan(cache)
    total_size = sum(b["size"] for b in buckets.values())
    host_dirs = sorted(p.name for p in cache.iterdir() if p.is_dir())

    out = [HEADER,
           f"# Local evidence cache - {human(total_size)}, {total_files:,} files, untracked by design\n",
           INTRO,
           "## Top level\n",
           "| Directory | Meaning |",
           "|---|---|"]
    out += [f"| `{d}` | host directory; mirrors the node's filesystem layout |" for d in host_dirs]
    out += ["", "## Contents, by host path (generated)\n",
            "| Path under cache root | Files | Size | Oldest | Newest | What it is |",
            "|---|---:|---|---|---|---|"]
    for name, b in sorted(buckets.items(), key=lambda kv: -kv[1]["size"]):
        out.append("| `{}` | {:,} | {} | {} | {} | {} |".format(
            name, b["n"], human(b["size"]),
            dt.datetime.fromtimestamp(min(b["ts"]), UTC).date(),
            dt.datetime.fromtimestamp(max(b["ts"]), UTC).date(),
            describe(name)))
    out.append("")

    if MANIFEST_SENTINEL in previous:
        out.append(previous.split(MANIFEST_SENTINEL, 1)[1].join([MANIFEST_SENTINEL, ""]))
    else:
        out.append(MANIFEST_SENTINEL + "\n")
        out.append("No prose recorded yet. State here: where the authoritative copy lives, what is\n"
                   "no longer reproducible, and any removal together with the evidence that permitted it.\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", nargs="?", default=None,
                    help="cache directory (…/_local-evidence); default found from the repo root")
    ap.add_argument("--check", action="store_true", help="fail if the manifest is not current")
    a = ap.parse_args()
    root = pathlib.Path(__file__).resolve()
    while not (root / "results").is_dir() and root != root.parent:
        root = root.parent
    caches = [pathlib.Path(a.cache)] if a.cache else sorted((root / "studies").glob("*/_local-evidence"))
    if not caches:
        print("no _local-evidence cache found", file=sys.stderr)
        return 1
    rc = 0
    for cache in caches:
        manifest = cache.parent / "EVIDENCE.md"
        previous = manifest.read_text() if manifest.is_file() else ""
        want = render(cache, manifest, previous)
        if a.check:
            if previous != want:
                print(f"EVIDENCE.md is not current for {cache}", file=sys.stderr)
                rc = 1
            continue
        manifest.write_text(want)
        print(f"manifest written: {manifest}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
