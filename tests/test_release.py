from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDRESSES = {
    "bc1qh474jpyw4malh0fmg2uy7n05ggtjvnjtcwhdne",
    "0x8fcC9C0d1FFCE17b1dEC91B299E56d66BC126Ba8",
    "D6qp2awRAHVo2VgincTAW5frhnJ9MBZcz4",
}


class ReleaseBoundaryTests(unittest.TestCase):
    def test_installed_demo_data_matches_documented_examples(self) -> None:
        pairs = (
            ("demo_bundle.json", json.loads),
            (
                "demo_answers.jsonl",
                lambda text: [json.loads(line) for line in text.splitlines() if line.strip()],
            ),
        )
        for filename, decode in pairs:
            documented = (ROOT / "examples" / filename).read_text(encoding="utf-8")
            installed = (ROOT / "chainfactbench" / "data" / filename).read_text(encoding="utf-8")
            self.assertEqual(decode(installed), decode(documented), filename)

    def test_support_contains_exact_authorized_addresses(self) -> None:
        support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
        found = set(re.findall(r"`([^`]+)`", support)) & ADDRESSES
        self.assertEqual(found, ADDRESSES)
        for address in ADDRESSES:
            self.assertEqual(support.count(address), 1)

    def test_relative_markdown_links_resolve(self) -> None:
        pattern = re.compile(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)")
        for path in ROOT.rglob("*.md"):
            for target in pattern.findall(path.read_text(encoding="utf-8")):
                if "://" in target:
                    continue
                self.assertTrue((path.parent / target).resolve().is_file(), f"{path}: {target}")

    def test_public_tree_has_no_private_project_or_key_marker(self) -> None:
        forbidden = (("world" + "forge"), "BEGIN " + "PRIVATE KEY")
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or ".git" in path.parts
                or ".venv" in path.parts
                or "__pycache__" in path.parts
                or path.name == "LICENSE"
                or path.suffix in {".pyc", ".pyo"}
            ):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for marker in forbidden:
                self.assertNotIn(marker.lower(), text, str(path))


if __name__ == "__main__":
    unittest.main()
