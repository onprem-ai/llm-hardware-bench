#!/usr/bin/env python3
"""Export immutable VictoriaMetrics/Prometheus range-query receipts for one run."""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, tempfile, urllib.parse, urllib.request


def request_json(base: str, query: str, start: str, end: str, step: str) -> tuple[bytes, str]:
    url = base.rstrip("/") + "/api/v1/query_range?" + urllib.parse.urlencode(
        {"query": query, "start": start, "end": end, "step": step})
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "llm-hardware-bench/1"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read(), url


def atomic(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8428")
    p.add_argument("--start", required=True, help="RFC3339 or Unix timestamp")
    p.add_argument("--end", required=True, help="RFC3339 or Unix timestamp")
    p.add_argument("--step", default="1s")
    p.add_argument("--query-file", required=True, type=pathlib.Path)
    p.add_argument("--output", required=True, type=pathlib.Path)
    a=p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    records=[]
    for number, raw in enumerate(a.query_file.read_text().splitlines(), 1):
        query=raw.strip()
        if not query or query.startswith("#"): continue
        payload,url=request_json(a.url,query,a.start,a.end,a.step)
        parsed=json.loads(payload)
        if parsed.get("status") != "success": raise RuntimeError(f"query failed: {query}: {parsed}")
        name=f"query-{number:03d}.json"; path=a.output/name; atomic(path,payload+b"\n")
        records.append({"query":query,"file":name,"request_url":url,
                        "series":len(parsed.get("data",{}).get("result",[]))})
    manifest={"schema_version":1,"exported_at":dt.datetime.now(dt.timezone.utc).isoformat(),
              "source_url":a.url,"start":a.start,"end":a.end,"step":a.step,"queries":records}
    atomic(a.output/"manifest.json",(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode())
    return 0
if __name__ == "__main__": raise SystemExit(main())
