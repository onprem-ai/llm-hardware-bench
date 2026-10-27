"""R-06-12: a published model label is the model name, with nothing appended.

This exists because a formal campaign published its model as
"GLM-5.3 NVFP4 (full model)" after the bare-name requirement had been stated
repeatedly. The label is not cosmetic: `model.name` becomes the page `<h1>`, the
`<title>`, the dataset name in JSON-LD and the entry in the device index, so a
decorated name is decoration on every surface of the report. Precision and
serving parameters already have their own fields - `model.repository`,
`model.revision`, `model.quantization` and the deployment record - which is where
that information belongs and where the page already renders it under `Model` and
`Quantization`.

The test is deliberately two-sided. A naming check that only proves it can reject
things is worthless if it also rejects "GLM-5.3 Flash" and "DeepSeek V4 Flash 0731",
which are real product names.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness"))

from check_repo import model_name_decorated  # noqa: E402


class TestDecoratedNamesAreRejected(unittest.TestCase):
    DECORATED = [
        "GLM-5.3 NVFP4 (full model)",      # the actual 2026-09-07 defect
        "Full GLM-5.3 NVFP4",              # precision promoted into the name
        "GLM-5.3 FP8",
        "GLM-5.3 INT4",
        "GLM-5.3 (quantized)",
        "DeepSeek V4 Flash (full model)",
        "GLM-5.3 seq128/graph512",         # serving parameters in the label
        "GLM-5.3 MTP-3",
        "GLM-5.3 at C128",
        "",
    ]

    def test_each_decorated_name_is_refused(self):
        for name in self.DECORATED:
            with self.subTest(name=name):
                self.assertIsNotNone(model_name_decorated(name))


class TestRealModelNamesAreAccepted(unittest.TestCase):
    ACCEPTED = [
        "GLM-5.3",
        "GLM-5.3 Flash",                   # "Flash" is part of the product name
        "DeepSeek V4 Flash 0731",          # a date token is part of the release name
        "Qwen3.8 Flash Next",
        "Llama 3.1 70B Instruct",
    ]

    def test_each_real_name_is_accepted(self):
        for name in self.ACCEPTED:
            with self.subTest(name=name):
                self.assertIsNone(model_name_decorated(name),
                                  f"{name!r} is a real model name and must not be flagged")


class TestPublishedModelNames(unittest.TestCase):
    def test_every_tracked_publication_is_cleanly_named(self):
        files = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard",
             "results"],
            capture_output=True, text=True).stdout.split()
        publications = [f for f in files if f.endswith("publication.json")]
        self.assertTrue(publications, "expected at least one tracked publication.json")
        for rel in publications:
            with self.subTest(publication=rel):
                model = json.loads((ROOT / rel).read_text()).get("model", {})
                reason = model_name_decorated(model.get("name", ""))
                self.assertIsNone(
                    reason,
                    f"{rel}: model.name {model.get('name')!r} {reason}. Name the model; put "
                    f"precision in model.quantization and topology in the deployment record.")


if __name__ == "__main__":
    unittest.main()
