from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from chainfactbench.core import (
    BenchError,
    load_json_source,
    parse_answer_quantity,
    validate_bundle,
    validate_capture_spec,
)
from chainfactbench.score import load_answers, score_answers

ROOT = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = load_json_source(ROOT / "examples" / "demo_bundle.json")

    def test_demo_bundle_validates(self) -> None:
        self.assertIs(validate_bundle(self.bundle), self.bundle)

    def test_digest_tamper_is_rejected(self) -> None:
        changed = copy.deepcopy(self.bundle)
        changed["cases"][0]["expected"] = "0x2b"
        with self.assertRaisesRegex(BenchError, "does not match"):
            validate_bundle(changed)

    def test_mutable_block_tag_is_rejected(self) -> None:
        changed = copy.deepcopy(self.bundle)
        changed["cases"][0]["params"][1] = "latest"
        with self.assertRaisesRegex(BenchError, "mutable block tag"):
            validate_bundle(changed)

    def test_capture_requires_block_placeholder(self) -> None:
        spec = load_json_source(ROOT / "examples" / "capture_spec.json")
        spec["cases"][0]["params"][1] = "latest"
        with self.assertRaisesRegex(BenchError, "mutable block tag"):
            validate_capture_spec(spec)

    def test_quantity_answer_forms(self) -> None:
        self.assertEqual(parse_answer_quantity(42, field="value"), 42)
        self.assertEqual(parse_answer_quantity("42", field="value"), 42)
        self.assertEqual(parse_answer_quantity("0x2a", field="value"), 42)
        with self.assertRaises(BenchError):
            parse_answer_quantity(True, field="value")


class ScoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = load_json_source(ROOT / "examples" / "demo_bundle.json")

    def test_demo_answers_pass(self) -> None:
        answers = load_answers(ROOT / "examples" / "demo_answers.jsonl")
        report = score_answers(self.bundle, answers)
        self.assertEqual(report["passed"], 2)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["score_percent"], 100.0)

    def test_wrong_evidence_and_value_fail_independently(self) -> None:
        answers = {
            "synthetic-balance": {
                "case_id": "synthetic-balance",
                "block_number": "0x11",
                "block_hash": "0x" + "2" * 64,
                "value": "43",
            }
        }
        report = score_answers(self.bundle, answers)
        first = report["results"][0]
        self.assertEqual(
            first["reasons"],
            ["block_number_mismatch", "block_hash_mismatch", "value_mismatch"],
        )
        self.assertEqual(report["results"][1]["reasons"], ["missing_answer"])

    def test_duplicate_answer_is_rejected(self) -> None:
        row = {
            "block_hash": "0x" + "1" * 64,
            "block_number": "0x10",
            "case_id": "same",
            "value": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answers.jsonl"
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(BenchError, "duplicate answer"):
                load_answers(path)


if __name__ == "__main__":
    unittest.main()

