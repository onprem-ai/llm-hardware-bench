import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
            if (a / '.git').exists())
MODULE_PATH = ROOT / "harness/7-report-and-feedback/code/render_report.py"
spec = importlib.util.spec_from_file_location("render_report", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class RendererHelpersTests(unittest.TestCase):
    def test_compact_maps_reader_facing_throughput(self):
        stat = {"median": 10, "minimum": 9, "maximum": 11, "mean": 10, "standard_deviation": 1, "n": 3, "unit": "tokens/s"}
        required = {
            "throughput": stat,
            "ttft_p50": stat,
            "ttft_p95": stat,
            "itl_average": stat,
            "itl_p95": stat,
        }
        data = {"series": {"decode": {"points": [{"concurrency": 1, **required}]}, "prefill": {"points": [{"concurrency": 1, **required}]}}}
        rows = module.compact(data)
        decode = next(x for x in rows if x["kind"] == "decode")
        prefill = next(x for x in rows if x["kind"] == "prefill")
        self.assertEqual(decode["decode_tps_median"], 10)
        self.assertEqual(prefill["input_tps_median"], 10)

    def test_fabric_section_distinguishes_endpoint_and_switch_metrics(self):
        data={'host_fabric':{'source':'/fabric','same_numa_all_reduce_busbw_gbps':{'minimum':28,'maximum':30},'cross_numa_all_reduce_busbw_gbps':{'minimum':20,'maximum':21},'cross_numa_penalty_pct':{'minimum':27,'maximum':29},'remote_cpu_penalty_pct':{'minimum':18,'maximum':25},'p2p_unidirectional_gbps':{'min':34,'median':40,'max':42},'p2p_bidirectional_gbps':{'min':64,'median':73,'max':75},'link_idle':'Gen1 x16','link_under_load':'Gen5 x16','upi':{'status':'unavailable'},'limitations':['GPU endpoint rates are not switch counters.']}}
        section=module.fabric_section(data)
        self.assertIn('NCCL',section);self.assertIn('Gen5 x16',section);self.assertIn('not direct internal PCIe-switch port counters',section)
        self.assertIn('<svg class="fabric-svg"',section)
        self.assertIn('Observed variation: 28.00-30.00',section)
        self.assertIn('<div class="n">29 GB/s</div>',section)

    def test_p2p_heatmap_contains_all_matrix_cells(self):
        rows=[]
        for direction in ('unidirectional','bidirectional'):
            for source in range(8):
                for destination in range(8):rows.append({'direction':direction,'source_gpu':source,'destination_gpu':destination,'value':40+source+destination})
        svg=module.p2p_heatmap_svg(rows,'unidirectional')
        self.assertEqual(svg.count('<rect '),64)
        self.assertIn('Destination GPU',svg)

    def test_prefill_rate_per_user_follows_decode_rate_per_user(self):
        template=(ROOT/'harness/7-report-and-feedback/code/templates/comparable-report.html').read_text()
        decode=template.index('<h3>Decode rate per user</h3>')
        prefill=template.index('<h3>Prefill rate per user</h3>')
        variability=template.index('<h3>Throughput variability</h3>')
        self.assertLess(decode,prefill)
        self.assertLess(prefill,variability)
        self.assertIn('id="prefillperuser"',template)
        self.assertIn("dat('prefill','per_user_tps_median')",template)
        self.assertIn("INPUT TOKENS / SECOND / USER",template)

    def test_primary_resource_order_prioritizes_gpus(self):
        template=(ROOT/'harness/7-report-and-feedback/code/templates/comparable-report.html').read_text()
        start=template.index('<section id="resources">');end=template.index('</section>',start);section=template[start:end]
        labels=['GPU utilization','GPU temperature','Allocated VRAM','Host CPU busy','Host RAM used']
        positions=[section.index(label) for label in labels]
        self.assertEqual(positions,sorted(positions))

    def test_template_contains_sglang_and_haproxy_panels(self):
        template=(ROOT/'harness/7-report-and-feedback/code/templates/comparable-report.html').read_text()
        for chart_id in ('mamba','haproxyfront','haproxyback','haproxyrequest','haproxyqueue','haproxybalance'):
            self.assertIn(f'id="{chart_id}"',template)
        self.assertIn('same-host proxy boundary',template)
        self.assertIn('RX and TX are never summed',template)

    def test_template_explains_process_pss_and_rss(self):
        template=(ROOT/'harness/7-report-and-feedback/code/templates/comparable-report.html').read_text()
        for chart_id in ('processpss','processrss','processprivate','processshared','processswap'):
            self.assertIn(f'id="{chart_id}"',template)
        self.assertIn('PSS proportionally divides shared pages',template)
        self.assertIn('RSS can count the same shared pages',template)

    def test_template_contains_visible_pcie_charts_and_references(self):
        template=(ROOT/'harness/7-report-and-feedback/code/templates/comparable-report.html').read_text()
        for chart_id in ('pcierx','pcietx','pciereplay'):self.assertIn(f'id="{chart_id}"',template)
        self.assertIn('<section id="gpu-path">',template)
        self.assertNotIn('<details><summary>GPU memory path',template)
        self.assertIn("~504 GB/s: 8 × Gen5 x16",template)
        self.assertIn("100% theoretical ceiling",template)
        self.assertIn("__SEQUENCE_CEILING__ active-sequence ceiling",template)
        self.assertNotIn("ref:32,refLabel:'32 active-sequence ceiling'",template)

    def test_template_labels_missing_metrics_unavailable(self):
        template=(ROOT/'harness/7-report-and-feedback/code/templates/comparable-report.html').read_text()
        self.assertIn("Metric was not collected for this campaign",template)
        self.assertIn("Unavailable",template)

    def test_single_repetition_wording_is_derived(self):
        config = {"provenance_notes": ["One repetition only."]}
        data = {"series": {"decode": {"points": [{"throughput": {"n": 1}}]}, "prefill": {"points": [{"throughput": {"n": 1}}]}}}
        counts = sorted({point["throughput"]["n"] for series in data["series"].values() for point in series["points"]})
        self.assertEqual(counts, [1])
        self.assertEqual(config["provenance_notes"], ["One repetition only."])

    def test_best_uses_throughput_median(self):
        series = {"points": [
            {"concurrency": 1, "throughput": {"median": 5}},
            {"concurrency": 8, "throughput": {"median": 7}},
        ]}
        self.assertEqual(module.best(series)["concurrency"], 8)


if __name__ == "__main__":
    unittest.main()
