---
kind: record
status: current
date: 2026-09-10
purpose: cold prompt pool source
produced_by: harness/3-deployment-raster/code/fetch_prompt_corpus.py then make_pool_source.py
---

# Prompt pool source for cold measurement (versioned, fetched once)

`make_book_corpus.py` cuts the prompt pool from `pool-source-20260910.txt.gz`, which
`make_pool_source.py` derives from the raw fetch. The fetch happened once, 2026-09-10, from Project
Gutenberg (`https://www.gutenberg.org/cache/epub/<id>/pg<id>.txt`), paced 0.4 s between works with
byte-capped range requests -- an earlier unpaced loop was rate-limited (HTTP 429), and a benchmark
that bullies a public service is not a benchmark worth running.

* works: 261 public-domain ebooks; IDs in fetch order in `gutenberg-work-ids-20260910.txt`
* raw gzipped corpus: 56,283,931 bytes, sha256 `0245c2f242a5d545c31baa9861ecd17b…`
* derived pool source: 105,143,694 bytes unique prose; gzipped 38,314,641 bytes
* capacity: ~13,900 passages of ~2,048 tokens -- about eight times what a C32 campaign consumes
* dataset total: 94.6 MB

## Why duplicates, not volume, were the problem

Two passages sharing a long leading token sequence register as prefix-cache reads even when they
are different prompts. A pool cut from every text file on the benchmark host -- 58% of whose bytes
were duplicated license boilerplate -- served 23.5% of prompt tokens from cache at 1,200 entries;
re-cutting that same source at the same offset served 5.2% after a size increase. Both runs were
refused by the cold gate. Storing the source makes the pool reproducible from a versioned input
instead of from whatever happened to be on a machine.

## Terms

Project Gutenberg works are published in the United States and are in the public domain there;
used here solely as measurement input. Downstream publication should re-check terms for its own
jurisdiction.

## v2 corpus (2026-09-11) — payload held outside this repository

The 24-slice cold grid needs ~250 MB of unique prose; the v1 source holds 105 MB and the grid
stopped at point 4 with a refusal rather than reusing prompts. v2 extends the same procedure over
ebook IDs 8000-32000. Only the work-ID list is versioned here; the text payload lives in the local
evidence cache, because 587 MB cannot live under this repo's 100 MB line.

| | value |
|---|---|
| produced by | `fetch_prompt_corpus.py` (3 paced streams: 8000-20000, 20000-26000, 26000-32000) then `make_pool_source.py` |
| raw corpus | 806502583 bytes, 1,678 works |
| pool source | 587,222,566 bytes, sha256 `e24e38bc1082a437b8a5b39de666cf865a3cd9246fbeb7ec0904c26f04142118` |
| node copy | `/home/demouser/glm53-raster/pool-source-20260911.txt`, same SHA-256, verified before measurement |
| ebook IDs | `gutenberg-work-ids-20260911.txt`, in fetch order |
| overlap with v1 | **0 works** by ID, so v2 prose is distinct from text the engine cache may already hold from v1 runs |
| HTTP errors | none; two early stream failures were my own malformed arguments, not Gutenberg |

Same terms as v1: Project Gutenberg, US public domain, paced at 0.4 s per request with byte-capped
range requests and a descriptive User-Agent.

## Payload storage (2026-09-18)

The gzipped payload files are no longer stored in this repository; a few MB of
aggregated or selected data per study is the ceiling, and raw corpus is not
that. The reproduction path is this record plus the work-ID lists: re-run
`fetch_prompt_corpus.py` with the IDs in `gutenberg-work-ids-20260910.txt`
(paced, as documented above), pipe the raw fetch through
`make_pool_source.py`, and verify byte counts and sha256 against the values
recorded here. Payload copies live outside the repository on the machines
that consumed them and under the untracked `_local-evidence/` mirrors.
