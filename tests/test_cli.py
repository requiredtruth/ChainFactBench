from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "chainfactbench", *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_demo_is_one_command_and_offline(self) -> None:
        result = self.run_cli("demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("score=2/2 (100.00%)", result.stdout)
        self.assertNotIn("\x1b[", result.stdout)

    def test_verify_emits_machine_readable_summary(self) -> None:
        result = self.run_cli("verify", "examples/demo_bundle.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, {
            "block_hash": "0x" + "1" * 64,
            "block_number": "0x10",
            "cases": 2,
            "chain_id": "0x1",
            "valid": True,
        })

    def test_prompts_exclude_expected_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "prompts.jsonl"
            result = self.run_cli("prompts", "examples/demo_bundle.json", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            text = output.read_text(encoding="utf-8")
            self.assertNotIn('"expected"', text)
            self.assertNotIn("0x6000", text)

    def test_score_failure_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            answers = Path(directory) / "answers.jsonl"
            answers.write_text(
                json.dumps({
                    "case_id": "synthetic-balance",
                    "block_number": "0x10",
                    "block_hash": "0x" + "1" * 64,
                    "value": "99",
                }) + "\n",
                encoding="utf-8",
            )
            result = self.run_cli("score", "examples/demo_bundle.json", str(answers), "--no-color")
            self.assertEqual(result.returncode, 1)
            self.assertIn("value_mismatch", result.stdout)

    def test_unexpected_answer_cannot_report_a_perfect_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            answers = Path(directory) / "answers.jsonl"
            answers.write_text(
                (ROOT / "examples" / "demo_answers.jsonl").read_text(encoding="utf-8")
                + json.dumps({
                    "case_id": "hallucinated-case",
                    "block_number": "0x10",
                    "block_hash": "0x" + "1" * 64,
                    "value": 0,
                })
                + "\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "score", "examples/demo_bundle.json", str(answers), "--format", "json"
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual(report["failed"], 1)
            self.assertEqual(report["score_percent"], 66.67)
            self.assertEqual(report["results"][-1]["reasons"], ["unexpected_answer"])


if __name__ == "__main__":
    unittest.main()
