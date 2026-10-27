#!/usr/bin/env python3
"""Build a prompt corpus from book text so no measured prompt can repeat.

Why not the synthetic generator: AIPerf's `synthetic` type samples random slices
of a fixed Shakespeare corpus with a bounded dataset size, and the formal
campaign ran with the default size of 100 prompts while each 60 s window issued
312-470 requests -- so prompts were re-sent 3-5 times per window and the engine
served 65-89% of prompt tokens from the prefix cache. Real book text with one
distinct passage per prompt removes the collision at the source and is also a
more honest input distribution than Shakespeare slices.

Determinism and proof:
  * passages are non-overlapping, taken in source order, so uniqueness follows
    from the offsets printed in the manifest;
  * the manifest records source path, byte length, SHA-256, token length used,
    and the passage index range, which is enough to re-derive the same corpus;
  * warm-up and measured prompts come from disjoint ranges, because a warm-up
    that draws from the measured range is a cache priming step, not a warm-up.

Output format is AIPerf's custom-dataset JSONL (one object per line with a
`prompt` field). The harness probes the installed binary with this file before
any measured run: if the flag set or the file shape is wrong, the probe fails
and no measurement is taken. Correctness here is established by execution, not
by this comment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

WORDS_PER_TOKEN = 0.75  # conservative; the probe reports the real token count


def sentences(text: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=pathlib.Path, required=True,
                    help="plain-text book (UTF-8), e.g. a Project Gutenberg etext")
    ap.add_argument("--out", type=pathlib.Path, required=True,
                    help="JSONL custom-dataset file to write")
    ap.add_argument("--manifest", type=pathlib.Path, required=True)
    ap.add_argument("--prompts", type=int, default=4000)
    ap.add_argument("--warmup-prompts", type=int, default=400,
                    help="drawn from a disjoint range before the measured range")
    ap.add_argument("--target-tokens", type=int, default=2048)
    ap.add_argument("--skip-head", type=int, default=20000,
                    help="skip Gutenberg header/front matter characters")
    args = ap.parse_args()

    raw = args.source.read_text(encoding="utf-8", errors="replace")
    body = raw[args.skip_head:]
    sents = sentences(body)
    need_words = int(args.target_tokens / WORDS_PER_TOKEN)

    passages, i, idx = [], 0, 0
    warmup_needed = args.warmup_prompts
    total_needed = args.warmup_prompts + args.prompts
    while len(passages) < total_needed and i < len(sents):
        chunk, words = [], 0
        while i < len(sents) and words < need_words:
            piece = sents[i]
            i += 1
            chunk.append(piece)
            words += len(piece.split())
        if words < need_words * 0.5:      # tail too short to be a real prompt
            break
        text = " ".join(chunk)
        passages.append({"prompt": text, "passage_index": idx})
        idx += 1

    if len(passages) < total_needed:
        print(f"REFUSED: source yields {len(passages)} passages of "
              f"~{args.target_tokens} tokens; need {total_needed} "
              f"({args.warmup_prompts} warm-up + {args.prompts} measured). "
              "Use a longer book or fewer prompts.", file=sys.stderr)
        return 2

    measured = passages[warmup_needed:]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(
        json.dumps({"prompt": p["prompt"]}, ensure_ascii=False) + "\n" for p in measured))

    manifest = {
        "source": str(args.source),
        "source_bytes": len(raw),
        "source_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "skipped_head_chars": args.skip_head,
        "target_tokens": args.target_tokens,
        "words_per_token_assumed": WORDS_PER_TOKEN,
        "warmup_passage_range": [0, warmup_needed],
        "measured_passage_range": [warmup_needed, len(passages)],
        "measured_prompts": len(measured),
        "prompts_are_disjoint_from_warmup": True,
        "uniqueness": ("passages are non-overlapping consecutive sentence runs; "
                       "each prompt appears exactly once in this file"),
        "output_sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  prompts written: {len(measured)} (warm-up range 0..{warmup_needed} excluded)")
    print(f"  output: {args.out} ({args.out.stat().st_size:,} bytes)")
    print(f"  manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
