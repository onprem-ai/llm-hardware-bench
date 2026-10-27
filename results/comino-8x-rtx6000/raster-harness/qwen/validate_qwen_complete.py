#!/usr/bin/env python3
"""Structural validation of the Qwen3.8-Flash-Next-NVFP4 download (chapter-1 gate).
Checks: (1) file inventory + sizes vs HF API at the pinned revision, (2) safetensors
header parse and tensor bounds, (3) sharded-index coverage. Trailing bytes beyond the
last tensor end are reported (writer padding) but tolerated, as with the GLM payload."""
import json, os, struct, sys, urllib.request

REPO = "RadixArk/Qwen3.8-Flash-Next-NVFP4"
REV = "7b719225242aacd3dbd3f9407468c2ee9a9d2594"
LOCAL = os.path.expanduser("~/bench/models/RadixArk--Qwen3.8-Flash-Next-NVFP4--model")
OUT = os.path.expanduser("~/bench/models/qwen38-flash-next-download/VALIDATION.json")

api = f"https://huggingface.co/api/models/{REPO}/tree/{REV}?recursive=true"
inv = json.load(urllib.request.urlopen(api, timeout=60))
inv_files = {e["path"]: e["size"] for e in inv if e["type"] == "file"}

problems, notes = [], []
local_files = {}
for root, _, files in os.walk(LOCAL):
    for f in files:
        if f.endswith(".incomplete"):
            problems.append(f"incomplete part file present: {f}")
            continue
        p = os.path.relpath(os.path.join(root, f), LOCAL)
        local_files[p] = os.path.getsize(os.path.join(root, f))

for path, size in sorted(inv_files.items()):
    if path not in local_files:
        problems.append(f"missing: {path}")
    elif local_files[path] != size:
        problems.append(f"size mismatch {path}: local {local_files[path]} vs api {size}")
extra = set(local_files) - set(inv_files)
if extra:
    problems.append(f"extra local files: {sorted(extra)[:5]}")

total_trailing = 0
shards_checked = 0
for path, size in sorted(inv_files.items()):
    if not path.endswith(".safetensors"):
        continue
    fp = os.path.join(LOCAL, path)
    if not os.path.exists(fp) or os.path.getsize(fp) != size:
        continue
    with open(fp, "rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        header = json.loads(fh.read(n))
    end = 8 + n
    for k in header:
        if k == "__metadata__":
            continue
        end = max(end, 8 + n + header[k]["data_offsets"][1])
    trailing = size - end
    if trailing < 0:
        problems.append(f"{path}: tensors exceed file size by {-trailing}")
    elif trailing > 0:
        total_trailing += trailing
        notes.append(f"{path}: {trailing} trailing bytes beyond last tensor")
    shards_checked += 1

idx_path = os.path.join(LOCAL, "model.safetensors.index.json")
index_covers = None
if os.path.exists(idx_path):
    idx = json.load(open(idx_path))
    shards = sorted(set(idx["weight_map"].values()))
    api_shards = sorted(p for p in inv_files if p.endswith(".safetensors"))
    missing = [s for s in shards if s not in api_shards]
    if missing:
        problems.append(f"index references missing shards: {missing[:3]}")
    uncovered = [s for s in api_shards if s not in shards]
    if uncovered:
        notes.append(f"api shards not referenced by index: {uncovered[:3]}")
    index_covers = {"index_shards": len(shards), "api_shards": len(api_shards)}
else:
    if any(p.endswith(".safetensors") for p in inv_files):
        problems.append("model.safetensors.index.json missing but safetensors present")

report = {
    "repo": REPO, "revision": REV, "local": LOCAL,
    "api_files": len(inv_files), "local_files": len(local_files),
    "safetensors_checked": shards_checked,
    "total_api_bytes": sum(inv_files.values()),
    "trailing_bytes_total": total_trailing,
    "index": index_covers,
    "problems": problems, "notes": notes[:60],
    "verdict": "PASS" if not problems else "FAIL",
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(report, open(OUT, "w"), indent=2)
print(json.dumps({k: report[k] for k in ("api_files", "local_files", "safetensors_checked",
                                         "trailing_bytes_total", "verdict")}))
for p in problems[:10]:
    print("PROBLEM:", p)
sys.exit(0 if not problems else 1)
