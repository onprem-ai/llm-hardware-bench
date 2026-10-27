#!/usr/bin/env python3
"""Fetch public-domain prose once, for versioning. Single source, paced, byte-capped."""
import re, subprocess, sys, time
TARGET, OUT, IDS = int(sys.argv[1]), sys.argv[2], sys.argv[3]
BASE = "https://www.gutenberg.org/cache/epub"
UA = "llm-inference-hardware-bench/0.1 (research benchmark; cold prompt pool)"
START = re.compile(r"START OF THE PROJECT GUTENBERG", re.I)
END = re.compile(r"END OF THE PROJECT GUTENBERG", re.I)

def get(url, cap=3_000_000):
    r = subprocess.run(["curl", "-fsS", "--compressed", "--max-time", "30", "-A", UA, "-r", f"0-{cap}", url],
                       capture_output=True, text=True, errors="replace")
    return r.stdout if r.returncode == 0 else ""

def clean(t):
    body = False
    out = []
    for line in t.splitlines():
        if START.search(line):
            body = True
            continue
        if END.search(line):
            break
        if body:
            out.append(line)
    t = "\n".join(out)
    t = re.sub(r"\r", "", t)
    return t

written = kept = attempted = 0
seen = set()
try:
    seen = set(open(IDS).read().split())
except Exception:
    pass
with open(OUT, "a") as fh, open(IDS, "a") as ids_fh:
    lo, hi = (int(x) for x in sys.argv[4:6]) if len(sys.argv) > 5 else (1, 8000)
    for book in range(lo, hi):
        if written >= TARGET:
            break
        attempted += 1
        if str(book) in seen:
            continue
        raw = get(f"{BASE}/{book}/pg{book}.txt")
        if len(raw) < 150_000:
            time.sleep(0.35)
            continue
        body = clean(raw)
        if len(body) < 120_000:
            time.sleep(0.35)
            continue
        fh.write(body + "\n\n")
        fh.flush()
        ids_fh.write(f"{book}\n")
        ids_fh.flush()
        seen.add(str(book))
        written += len(body)
        kept += 1
        if kept % 15 == 0:
            print(f"  {written/1e6:.1f} MB from {kept} works (tried {attempted})", flush=True)
        time.sleep(0.4)
print(f"  done: {written/1e6:.1f} MB from {kept} works, {attempted} ids tried")
