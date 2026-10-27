// Validate the site input and stage it for the Astro build.
//
// Publications are the only per-model input. Their embedded normalized_data
// drives every chart and table, so this script no longer reads, scrapes or
// rewrites generated report HTML — the site renders the measurements itself.
//
// Alongside each publication it publishes the source files the numbers came
// from (normalized data, campaign CSVs) so any rendered value can be audited,
// and so the page can advertise them as Dataset distributions.
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import Ajv2020 from 'ajv/dist/2020.js';

const project = path.resolve(import.meta.dirname, '..');
const input = path.resolve(process.env.REPORT_SITE_INPUT || path.join(project, 'example'));
const generated = path.join(project, 'src', 'generated');
const publicDir = path.join(project, 'public');
function findRepo(start) { let d = start;
  while (d !== path.dirname(d)) {
    if (fs.existsSync(path.join(d, 'harness')) && fs.existsSync(path.join(d, 'results'))) return d;
    d = path.dirname(d);
  }
  throw new Error('repo root not found from ' + start);
}
const repo = findRepo(project);
const read = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));

// Publish-time redaction (CLAUDE.md: no access details in anything we publish).
// Evidence records the operator's absolute paths and the internal host name;
// the public site gets neither. Home directories collapse to "~", the internal
// host name becomes the public device label, and non-loopback IPv4 addresses
// are blanked. build-site.sh re-scans the final output and fails on any leak.
function redactText(text, hostNames, label) {
  let out = text
    .replace(/\/(?:home|Users)\/[^/\s"'`<>,]+/g, '~')
    .replace(/\/root\//g, '~/')
    .replace(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, (ip) =>
      ['127.0.0.1', '0.0.0.0'].includes(ip) ? ip : '<redacted-ip>');
  for (const h of hostNames) if (h && h !== label) out = out.split(h).join(label);
  return out;
}
const redactJson = (obj, hostNames, label) =>
  JSON.parse(redactText(JSON.stringify(obj), hostNames, label));

const ajv = new Ajv2020({ allErrors: true, strict: false });
const normalizedSchema = read(path.join(repo, 'harness/7-report-and-feedback/schemas', 'normalized-report-data.schema.json'));
const publicationSchema = read(path.join(repo, 'harness/6-accept-and-publish/schemas', 'benchmark-publication.schema.json'));
const siteSchema = read(path.join(repo, 'harness/7-report-and-feedback/schemas', 'report-site.schema.json'));
ajv.addSchema(normalizedSchema, 'normalized-report-data.schema.json');
const validateSite = ajv.compile(siteSchema);
const validatePublication = ajv.compile(publicationSchema);

const site = read(path.join(input, 'site-config.json'));
if (!validateSite(site)) throw new Error(ajv.errorsText(validateSite.errors, { separator: '\n' }));

// Source files offered for download when present next to the publication's
// normalized data. Absent files are skipped rather than linked as 404s.
const RECEIPTS = [
  { file: 'normalized-report-data.json', label: 'Normalized report data (JSON)', note: 'every value rendered on this page' },
  { file: 'campaign-summary-runs.csv', label: 'Campaign summary, per run (CSV)', note: 'one row per measured run' },
  { file: 'campaign-summary-aggregate.csv', label: 'Campaign summary, aggregated (CSV)' },
];

fs.rmSync(generated, { recursive: true, force: true });
fs.rmSync(publicDir, { recursive: true, force: true });
fs.mkdirSync(generated, { recursive: true });
fs.mkdirSync(path.join(publicDir, 'assets'), { recursive: true });

const devices = [];
const ids = new Set();
const receiptsById = {};
let receiptCount = 0;

for (const device of site.devices) {
  const publications = device.benchmarks.map((relative) => {
    const source = path.resolve(input, relative);
    const raw = read(source);
    if (!validatePublication(raw)) {
      throw new Error(`${source}\n${ajv.errorsText(validatePublication.errors, { separator: '\n' })}`);
    }
    const hostNames = [raw.hardware?.host].filter(Boolean);
    const doc = redactJson(raw, hostNames, device.label);
    if (ids.has(doc.id)) throw new Error(`Duplicate benchmark ID: ${doc.id}`);
    ids.add(doc.id);
    if (doc.hardware.model !== device.model) throw new Error(`Hardware mismatch: ${doc.id}`);
    if (!doc.normalized_data?.series?.decode?.points?.length) {
      throw new Error(`Publication carries no decode series: ${source}`);
    }

    // Receipts live beside the campaign's normalized data, which the
    // publication points at via source.normalized_data_path when known;
    // otherwise look beside the publication itself.
    const receiptDir = doc.source?.normalized_data_path
      ? path.dirname(path.resolve(path.dirname(source), doc.source.normalized_data_path))
      : path.dirname(source);
    const destDir = path.join(publicDir, 'data', device.label, doc.id);
    const found = [];
    for (const receipt of RECEIPTS) {
      const from = path.join(receiptDir, receipt.file);
      if (!fs.existsSync(from)) continue;
      fs.mkdirSync(destDir, { recursive: true });
      fs.writeFileSync(path.join(destDir, receipt.file),
        redactText(fs.readFileSync(from, 'utf8'), hostNames, device.label));
      found.push({ label: receipt.label, href: `/data/${device.label}/${doc.id}/${receipt.file}`, note: receipt.note });
    }

    // The publication always embeds normalized_data, so publish that as the
    // baseline receipt even when no campaign files sit beside the input.
    if (!found.some((r) => r.href.endsWith('normalized-report-data.json'))) {
      fs.mkdirSync(destDir, { recursive: true });
      fs.writeFileSync(
        path.join(destDir, 'normalized-report-data.json'),
        `${JSON.stringify(doc.normalized_data, null, 2)}\n`,
      );
      found.unshift({
        label: 'Normalized report data (JSON)',
        href: `/data/${device.label}/${doc.id}/normalized-report-data.json`,
        note: 'every value rendered on this page',
      });
    }

    receiptsById[`${device.label}/${doc.id}`] = found;
    receiptCount += found.length;
    return doc;
  });

  const image = path.resolve(input, device.image);
  if (!fs.existsSync(image)) throw new Error(`Missing device image: ${image}`);
  devices.push({ ...device, publications, imageExtension: path.extname(image).toLowerCase() });
}

const benchmarks = devices.flatMap((device) =>
  device.publications.map((publication) => ({
    hardwareLabel: device.label,
    device,
    publication,
    receipts: receiptsById[`${device.label}/${publication.id}`] ?? [],
  })),
);

fs.writeFileSync(path.join(generated, 'site.json'), JSON.stringify(site, null, 2));
fs.writeFileSync(path.join(generated, 'devices.json'), JSON.stringify(devices, null, 2));
fs.writeFileSync(path.join(generated, 'benchmarks.json'), JSON.stringify(benchmarks, null, 2));

for (const device of devices) {
  fs.copyFileSync(
    path.resolve(input, device.image),
    path.join(publicDir, 'assets', `${device.label}${device.imageExtension}`),
  );
}

console.log(
  `Prepared ${devices.length} devices, ${ids.size} schema-validated publications, ` +
    `${receiptCount} published source files from ${input}`,
);
