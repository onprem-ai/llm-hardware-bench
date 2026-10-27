# Astro hardware benchmark website

This directory contains the static multi-report website generator. It renders
benchmark reports directly from measurement data; no standalone report HTML is
produced or consumed.

## Data contracts

The build consumes:

1. `site-config.json`, validated by `harness/7-report-and-feedback/schemas/report-site.schema.json`.
2. One benchmark publication JSON per model, validated by
   `harness/7-report-and-feedback/schemas/benchmark-publication.schema.json`.

A publication embeds its validated `normalized-report-data.json`. Every chart,
table and headline on a model page is rendered from that embedded data at build
time. Generate a publication with:

```bash
python3 harness/6-accept-and-publish/code/generate_publication.py \
  report/report-config.json report/normalized-report-data.json \
  --hardware-model "<server model, from the host's site-config.json>" \
  --aggregate-vram-gib 768 \
  --normalized-data-path ../normalized-report-data.json \
  --output data/model.json
```

`--normalized-data-path` tells the site where the campaign's source files live,
so it can publish them beside the page as downloadable receipts. `--report-path`
still exists but is optional and only meaningful for archived publications that
predate native rendering.

Publications carry the deployment parameters, concurrency axis and provenance
paths under the same names `report-config.json` uses, so the two documents can
be read against each other without a translation table.

Since 2026-09-18 publications also carry a `reproducibility` block (pinned
container identity, model revision, verbatim launch commands read from the
tracked deployment scripts, measurement client, corpus) and a `procedure`
digest (what was tried, what failed, what worked - distilled from the study
journals, with the journals linked via `procedure_source`). The site renders
both as the `Reproduce` and `Procedure` sections at the end of every model
page, and `harness/check_repo.py` rule 9 refuses a publication without them:
numbers nobody can re-derive, with no visible path to them, do not publish.
Gaps are declared in-band (null plus a note), never omitted silently.

## Build

```bash
cd harness/7-report-and-feedback/code/site/astro
npm ci
REPORT_SITE_INPUT=/absolute/path/to/site-input npm run build
```

The input directory contains `site-config.json`, its hero image, and the
publication JSON files referenced by the manifest. Build output is `dist/`.

For this repository's publications, use the convenience command:

```bash
harness/7-report-and-feedback/code/site/astro/scripts/build-site.sh
```

or, from the repository root:

```bash
make build-site                    # every host that has a site-config.json
STUDY=<host-dir> make build-site   # one host only
```

It auto-discovers every results/<host>/ that carries a site-config.json, merges
them into one build input, and writes ignored generated output to `website/site/`.
It also rewrites `website/README.md`, so the build and preview instructions carried
inside the ignored output can never disagree with the script that produced it.

## Preview

Two routes, verified against the current build:

```bash
# 1. Serve exactly what the build published (website/site/), plain static server.
python3 -m http.server 4321 --directory website/site --bind 127.0.0.1
open http://127.0.0.1:4321/benchmarks/
```

```bash
# 2. Astro's own server, serving the generator's dist/ rather than website/site/.
cd harness/7-report-and-feedback/code/site/astro
npm run preview -- --port 4321
open http://localhost:4321/benchmarks/
```

`astro preview` binds IPv6 `::1` only unless you pass `--host`, so
`http://127.0.0.1:4321` gets an empty reply while `http://localhost:4321` works,
even though the server printed "ready". Route 1 avoids that difference; use
`npm run preview -- --host` when you want the page from another machine.

### Live editing

`npm run dev` also runs `prepare.mjs`, so it needs the same input directory the build
needs:

```bash
REPORT_SITE_INPUT=$PWD/results/<host-dir> \
  npm run dev -- --host 127.0.0.1 --port 4321
```

Without that variable `prepare.mjs` dies with
`ENOENT: ... astro/example/site-config.json`, which reads like a missing fixture rather
than a missing input path. Passing `--host 127.0.0.1` explicitly also removes the
`localhost`/`::1` ambiguity above. `astro preview` needs no such variable - it serves
the already-built `dist/`. Either way `prepare.mjs` runs once, at startup: restart the
server to pick up a report published after it began.

### If the port is already taken

A server answering on that port is not necessarily serving this build. Observed on
this repository: an `astro dev` started days earlier from a directory that has since
been moved out of the tree kept answering `500` on `/benchmarks/`, because
`prepare.mjs` stages `src/generated/` only when the server starts. So a long-running
dev or preview server shows neither new publications nor deleted-path errors - it just
keeps serving whatever it staged that morning. Check who owns the port, restart it after
any rebuild, or use a different port - `localhost` may resolve to `::1` while another
process still owns `127.0.0.1` on the same number, so two servers can answer that URL
differently:

```bash
lsof -nP -iTCP:4321 -sTCP:LISTEN
```

Confirm the page you expect is actually being served instead of trusting that a
server started:

```bash
curl -s http://127.0.0.1:4321/benchmarks/ | grep -o 'href="[^"]*"' | sort -u
```

## Routes

```text
/                                       redirects to /benchmarks/
/benchmarks/                            hardware device list, specs, and model links
/benchmarks/<hardware-label>/<model>/
/data/<hardware-label>/<model>/         published source files for that report
```

The site manifest contains a `devices` array. Each device owns its image, specs,
and benchmark-publication JSON list, so additional hardware can be added without
changing page components.

## How a report page is built

- `scripts/prepare.mjs` validates the input, stages it into `src/generated/`,
  and copies each campaign's source files into `public/data/`.
- `src/lib/report.ts` provides typed access to `normalized_data`. Metrics are
  addressed by their normalized-report-data names.
- `src/lib/catalogue.ts` describes the report as data: which sections exist and
  which metric each chart plots. Adding a metric is one entry here; adding a
  model or a server needs no change at all.
- `src/lib/chart.ts` and `src/lib/fabric.ts` build every chart as SVG markup.
- `src/components/report/` composes the sections, and pairs each chart with a
  table of the values behind it.

## Guarantees

- No iframes, and no generated HTML is scraped or injected.
- Charts are SVG built at build time, each with `<title>` and `<desc>`, and each
  data point carrying its value, range and repetition count as hover text.
- Every plotted series is also emitted as an HTML table, so measurements are
  readable as text rather than only as chart geometry.
- The decode/prefill toggle uses radio inputs and sibling selectors, so both
  variants are present in the DOM.
- **Report pages require no JavaScript.** The only script on a page is an
  optional enhancement that carries your position in the report across a model
  switch.
- Each page links the source data it was rendered from, and lists it in the page
  `Dataset` structured data.
