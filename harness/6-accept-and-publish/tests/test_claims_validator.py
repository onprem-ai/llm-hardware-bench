"""Runs the failure-mode proofs that R-PIPE-2 exists to provide.

validate_claims.py carries its own --self-test, but a flag inside a script is not a test: it is not
collected by `make test`, so the six ways this validator must refuse a claim could rot unnoticed.
This wrapper makes them a test and asserts each named mode actually FAILs.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve()
while not (ROOT / "harness").is_dir() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
VALIDATOR = ROOT / "harness/6-accept-and-publish/code/validate_claims.py"

# Each entry is a phrase that must appear next to a FAIL verdict in the self-test output.
EXPECTED_REFUSALS = [
    "phantom comparator",
    "delta mis-stated",
    "headline not the median",
    "supplying its own comparator value",
    "claim that is also prohibited",
]


class ClaimsValidatorTest(unittest.TestCase):
    def run_validator(self, *args):
        return subprocess.run([sys.executable, str(VALIDATOR), *args],
                              text=True, capture_output=True, cwd=ROOT)

    def test_self_test_passes_and_refusals_are_demonstrated(self):
        r = self.run_validator("--self-test")
        self.assertEqual(r.returncode, 0, f"self-test reported: {r.stdout}{r.stderr}")
        for phrase in EXPECTED_REFUSALS:
            with self.subTest(mode=phrase):
                self.assertIn(phrase, r.stdout)
                self.assertIn("FAIL", r.stdout.split(phrase, 1)[1].splitlines()[0])

    def test_real_claims_file_validates(self):
        claims = sorted((ROOT / "results").glob("*/**/claims.yaml"))
        self.assertTrue(claims, "no claims.yaml exists to validate")
        for path in claims:
            with self.subTest(claims=str(path.relative_to(ROOT))):
                r = self.run_validator(str(path.relative_to(ROOT)))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
