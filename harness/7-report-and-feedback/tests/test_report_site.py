import json
import unittest
from pathlib import Path

import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
            if (a / '.git').exists())
SITE=ROOT/'harness/7-report-and-feedback/code/site/astro'


def _publication_schema():
    """Resolve the publication schema by search: it is chapter 6's document, referenced by
    chapter 7's tests, and a hard-coded chapter path rots the moment ownership moves."""
    for ch in ('7-report-and-feedback', '6-accept-and-publish'):
        c = ROOT / 'harness' / ch / 'schemas' / 'benchmark-publication.schema.json'
        if c.is_file():
            return json.loads(c.read_text())
    raise AssertionError('benchmark-publication.schema.json exists in no chapter')

def astro_sources():
    return '\n'.join(path.read_text() for path in (SITE/'src').glob('**/*.astro'))

class ReportSiteTests(unittest.TestCase):
    def test_astro_site_is_native_seo_html_without_iframes(self):
        sources=astro_sources()
        for text in ('application/ld+json','meta name="description"','property="og:title"',
                     '/benchmarks/${device.label}/${b.id}/'):
            self.assertIn(text,sources)
        self.assertNotIn('<iframe',sources)
        self.assertIn('/benchmarks/${hardwareLabel}/${item.id}/',sources)
        self.assertIn('class="device-row"',sources)
        self.assertTrue((SITE/'package-lock.json').is_file())

    def test_reports_render_natively_rather_than_embedding_generated_html(self):
        """The site builds reports from normalized_data.

        Reports were previously generated as standalone HTML, scraped apart for
        their <body> and <style>, and injected into the page. That coupling is
        what these assertions exist to prevent returning.
        """
        sources=astro_sources()
        self.assertIn('<Report publication=',sources)
        for removed in ('set:html={reportDocument.body}','reportDocument.styles','embedded-comparable-report'):
            self.assertNotIn(removed,sources)
        prepare=(SITE/'scripts/prepare.mjs').read_text()
        for removed in ('<body','<style','report-documents.json'):
            self.assertNotIn(removed,prepare)

    def test_charts_and_tables_are_built_without_client_javascript(self):
        chart=(SITE/'src/lib/chart.ts').read_text()
        # Charts are markup, not runtime drawing calls.
        self.assertIn('<svg viewBox',chart)
        self.assertNotIn('document.createElementNS',chart)
        self.assertNotIn('onmouseenter',chart)
        # Every chart carries text for crawlers and assistive technology.
        self.assertIn('<title>',chart)
        self.assertIn('<desc>',chart)
        # Each chart's numbers are also emitted as a table.
        figure=(SITE/'src/components/report/ChartFigure.astro').read_text()
        self.assertIn('<table>',figure)
        self.assertIn('<details',figure)

    def test_publication_and_site_schemas_accept_minimal_documents(self):
        try:
            import jsonschema



        except ImportError:
            self.skipTest('jsonschema not installed')
        statistic={"median":100,"minimum":90,"maximum":110,"n":3}
        point={"concurrency":1,"throughput":statistic,"ttft_p50":statistic,"ttft_p95":statistic,"itl_average":statistic,"itl_p95":statistic}
        normalized={"schema_version":1,"source_campaign":"/results","source_counts":{"runs":3,"requests":10,"errors":0},"selection":{"policy":"maximum-median-useful-tps","decode_source_id":"decode","prefill_source_id":"prefill"},"series":{"decode":{"source_id":"decode","points":[point]},"prefill":{"source_id":"prefill","points":[point]}}}
        publication={"schema_version":1,"id":"model","title":"Model capacity","description":"A sufficiently detailed benchmark description for schema validation.","hardware":{"model":"Server","host":"host","gpu_count":8,"gpu_model":"GPU","aggregate_vram_gib":768},"model":{"name":"Model","repository":"org/model","revision":"1234567","quantization":"FP8"},"report":{"path":"../report.html","kind":"capacity-report","date":None},"deployment":{"summary":"TP8","request_path":"AIPerf to HAProxy"},"evidence":{"runs":3,"requests":10,"errors":0,"repetitions":3},"axis":[1,8],"headlines":{"decode":{"value":100,"unit":"output tokens/s","concurrency":8,"statistic":"median"},"prefill":{"value":200,"unit":"input tokens/s","concurrency":8,"statistic":"median"}},"normalized_data":normalized}
        site={"schema_version":1,"site":{"title":"Site","description":"A sufficiently detailed hardware benchmark website description.","canonical_url":None},"devices":[{"label":"server","model":"Server","manufacturer":"Vendor","summary":"A sufficiently detailed hardware platform summary for validation.","image":"hero.png","specs":[{"label":"GPU","value":"8"}],"benchmarks":["data/model.json"]}]}
        normalized_schema=json.loads((ROOT/'harness/7-report-and-feedback/schemas/normalized-report-data.schema.json').read_text())
        _pub=next((ROOT/f'harness/{ch}/schemas/benchmark-publication.schema.json'
                        for ch in ('7-report-and-feedback','6-accept-and-publish')
                        if (ROOT/f'harness/{ch}/schemas/benchmark-publication.schema.json').is_file()),None)
        self.assertIsNotNone(_pub,'benchmark-publication.schema.json exists in no chapter')
        publication_schema=json.loads(_pub.read_text())
        resolver=jsonschema.RefResolver.from_schema(publication_schema,store={normalized_schema['$id']:normalized_schema})
        jsonschema.Draft202012Validator(publication_schema,resolver=resolver).validate(publication)
        jsonschema.validate(site,json.loads((ROOT/'harness/7-report-and-feedback/schemas/report-site.schema.json').read_text()))

    def test_publication_schema_accepts_a_publication_with_no_standalone_report(self):
        """Publications no longer need to point at a generated HTML report, and
        may carry the deployment and axis detail the native report renders."""
        try:
            import jsonschema
        except ImportError:
            self.skipTest('jsonschema not installed')
        statistic={"median":100,"minimum":90,"maximum":110,"n":3}
        point={"concurrency":1,"throughput":statistic,"ttft_p50":statistic,"ttft_p95":statistic,"itl_average":statistic,"itl_p95":statistic}
        normalized={"schema_version":1,"source_campaign":"/results","source_counts":{"runs":3,"requests":10,"errors":0},"selection":{"policy":"maximum-median-useful-tps","decode_source_id":"decode","prefill_source_id":"prefill"},"series":{"decode":{"source_id":"decode","points":[point]},"prefill":{"source_id":"prefill","points":[point]}}}
        publication={"schema_version":1,"id":"model","title":"Model capacity","description":"A sufficiently detailed benchmark description for schema validation.","hardware":{"model":"Server","host":"host","gpu_count":8,"gpu_model":"GPU","aggregate_vram_gib":768},"model":{"name":"Model","repository":"org/model","revision":"1234567","quantization":"FP8"},
            "report":{"kind":"capacity-report","date":"2026-09-01","subtitle":"Complete C1-C64 curves"},
            "deployment":{"summary":"1×TP8","request_path":"AIPerf to HAProxy","replicas":1,"tensor_parallel_per_replica":8,"active_sequence_ceiling":32,"kv_cache_dtype":"fp8","max_model_len":32768,"cpu_numa_affinity":"node0"},
            "source":{"campaign_path":"/results/campaign","normalized_data_path":"../normalized-report-data.json"},
            "evidence":{"runs":3,"requests":10,"errors":0,"repetitions":3},
            "axis":{"measured_concurrency":[1,8],"major_ticks":[1,4,8],"maximum":8},
            "headlines":{"decode":{"value":100,"unit":"output tokens/s","concurrency":8,"statistic":"median"},"prefill":{"value":200,"unit":"input tokens/s","concurrency":8,"statistic":"median"}},
            "normalized_data":normalized}
        normalized_schema=json.loads((ROOT/'harness/7-report-and-feedback/schemas/normalized-report-data.schema.json').read_text())
        publication_schema=_publication_schema()
        resolver=jsonschema.RefResolver.from_schema(publication_schema,store={normalized_schema['$id']:normalized_schema})
        jsonschema.Draft202012Validator(publication_schema,resolver=resolver).validate(publication)

if __name__=='__main__':unittest.main()
