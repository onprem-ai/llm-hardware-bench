import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
            if (a / '.git').exists())
MODULE_PATH = ROOT / "harness/2-preflight-conformance/code/dcgm/metric-availability.py"
spec = importlib.util.spec_from_file_location("metric_availability", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class MetricAvailabilityTests(unittest.TestCase):
    def test_parse_and_compare_label_order_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            before = d / "before.prom"
            after = d / "after.prom"
            before.write_text('# TYPE M gauge\nM{gpu="0",UUID="u"} 10\n')
            after.write_text('# TYPE M gauge\nM{UUID="u",gpu="0"} 14\n')
            types, left = module.parse_prometheus(before)
            _, right = module.parse_prometheus(after)
            common, changed, delta = module.comparable(left["M"], right["M"])
            self.assertEqual(types["M"], "gauge")
            self.assertEqual((common, changed, delta), (1, 1, 4.0))

    def test_missing_is_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.prom"
            path.write_text("# no samples\n")
            _, samples = module.parse_prometheus(path)
            self.assertNotIn("DCGM_FI_PROF_PCIE_RX_BYTES", samples)

    def test_collector_csv(self):
        fields = module.parse_collector(ROOT / "harness/2-preflight-conformance/code/configs/dcgm-custom.csv")
        by_name = {x["name"]: x for x in fields}
        self.assertEqual(by_name["DCGM_FI_PROF_PCIE_RX_BYTES"]["prometheus_type"], "gauge")
        self.assertEqual(by_name["DCGM_FI_DEV_PCIE_REPLAY_COUNTER"]["prometheus_type"], "counter")


if __name__ == "__main__":
    unittest.main()
