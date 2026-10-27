# Published benchmark data

These compact, schema-validated JSON documents are the Git-controlled inputs to
the XE7740 Astro report website.

- `glm5.3/publication.json`
- `glm5.3-flash/publication.json`
- `qwen3.8-flash-next/publication.json`
- `deepseek-v4-flash/publication.json`
- `assets/dell-poweredge-xe7740.png`
- `../site-config.json`

Schemas:

- `../../harness/7-report-and-feedback/schemas/benchmark-publication.schema.json`
- `../../harness/7-report-and-feedback/schemas/report-site.schema.json`
- embedded normalized data: `../../harness/7-report-and-feedback/schemas/normalized-report-data.schema.json`

The publication JSON contains distilled aggregate results and provenance. Raw
benchmark receipts and telemetry remain outside Git.

The publication records reference generated standalone reports under
`published/xe7740/`, while all JSON and the hero image are tracked here.

Deployment contracts currently exist for:

- `glm5.3/`
- `glm5.3-flash/`
- `qwen3.8-flash-next/`
- `deepseek-v4-flash/`

Build the site from the repository root:

```bash
harness/7-report-and-feedback/code/site/astro/scripts/build-site.sh
```

Generated output is written to `published/xe7740/site/`. Raw and legacy local
evidence lives under ignored `local-artifacts/xe7740-04/`.
