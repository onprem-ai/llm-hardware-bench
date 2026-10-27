import importlib.util
import unittest
from pathlib import Path

import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
            if (a / '.git').exists())
MODULE_PATH = ROOT / "harness/7-report-and-feedback/code/validate_report_inputs.py"
spec = importlib.util.spec_from_file_location("validate_report_inputs", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def statistic(value):
    return {"median": value, "minimum": value - 1, "maximum": value + 1, "n": 3, "unit": "tokens/s"}


def sample():
    config = {
        "axis": {"measured_concurrency": [1, 8], "maximum": 192, "major_ticks": [1, 8, 192]}
    }
    points = [
        {
            "concurrency": concurrency,
            "throughput": statistic(100 + concurrency),
            "ttft_p50": statistic(10),
            "ttft_p95": statistic(20),
            "itl_average": statistic(3),
            "itl_p95": statistic(5),
        }
        for concurrency in (1, 8)
    ]
    data = {
        "selection": {
            "decode_source_id": "source-d",
            "prefill_source_id": "source-p",
        },
        "series": {
            "decode": {"source_id": "source-d", "points": points},
            "prefill": {"source_id": "source-p", "points": points},
        },
    }
    return config, data


class ReportInputSemanticTests(unittest.TestCase):
    def test_valid_input(self):
        config, data = sample()
        self.assertEqual(module.semantic_errors(config, data), [])

    def test_axis_must_include_measurements(self):
        config, data = sample()
        config["axis"]["maximum"] = 4
        self.assertTrue(any("highest measured" in x for x in module.semantic_errors(config, data)))

    def test_profile_specific_grid_may_be_subset(self):
        config, data = sample()
        data["series"]["decode"]["points"].pop()
        self.assertFalse(any("subset" in x for x in module.semantic_errors(config, data)))

    def test_series_grid_cannot_exceed_axis(self):
        config, data = sample()
        data["series"]["decode"]["points"][0]["concurrency"] = 999
        self.assertTrue(any("not a subset" in x for x in module.semantic_errors(config, data)))

    def test_statistic_order(self):
        config, data = sample()
        data["series"]["decode"]["points"][0]["throughput"]["minimum"] = 200
        self.assertTrue(any("violated" in x for x in module.semantic_errors(config, data)))


if __name__ == "__main__":
    unittest.main()
