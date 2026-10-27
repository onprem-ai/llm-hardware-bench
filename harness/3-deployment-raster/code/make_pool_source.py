#!/usr/bin/env python3
"""Derive the cold prompt pool source from the fetched public-domain corpus.

Raw corpus text contains repeated boilerplate (license blocks, table-of-contents dots, duplicated
front matter). Duplicates matter: two passages sharing a long prefix register as prefix-cache reads
even though they are distinct prompts, which is exactly what made one measured run report 23.5%
served on a pool with 1,200 entries. So the source is built from UNIQUE prose lines only.

Usage: make_pool_source.py <raw-corpus> <out-pool-source> [--min-words 8]
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys

BOILER = re.compile(r"^(Project Gutenberg|Start of Project Gutenberg|End of Project Gutenberg|"
                    r"\*\*\*+|Title:|Author:|Release notes|Produced by|Illustrated by)", re.I)
PROSE = re.compile(r"^[\"'“‘(]?[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’”““’,;:\-—\.!\?\(\) ]+$")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--min-words", type=int, default=8)
    a = ap.parse_args(argv)

    seen: set[str] = set()
    kept = dropped_dup = dropped_shape = 0
    words_total = 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8") as out:
        buf: list[str] = []
        words = 0
        for line in a.raw.read_text(encoding="utf-8", errors="replace").splitlines():
            s = re.sub(r"[ \t]+", " ", line).strip()
            if not s or BOILER.match(s) or not PROSE.match(s):
                continue
            n = len(s.split())
            if n < a.min_words:
                dropped_shape += 1
                continue
            if s in seen:
                dropped_dup += 1
                continue
            seen.add(s)
            kept += 1
            words_total += n
            buf.append(s)
            words += n
            if words >= 2600:                      # ~one 2,048-token passage plus headroom
                out.write(" ".join(buf) + "\n\n")
                buf, words = [], 0
        if buf:
            out.write(" ".join(buf) + "\n\n")

    digest = hashlib.sha256(a.out.read_bytes()).hexdigest()
    print(f"  lines kept {kept:,} (duplicate lines dropped {dropped_dup:,}, "
          f"non-prose/short {dropped_shape:,})")
    print(f"  words {words_total:,}  -> ~{words_total // 1350:,} passages of ~2,048 tokens "
          f"(1,350 words/passage estimate)")
    print(f"  bytes {a.out.stat().st_size:,}  sha256 {digest[:32]}")
    print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
