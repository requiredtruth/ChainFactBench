from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .core import (
    BenchError,
    MAX_ANSWER_LINE_BYTES,
    MAX_CASES,
    canonical_json,
    parse_answer_quantity,
    parse_quantity,
    validate_bundle,
)


def load_answers(source: str | Path) -> dict[str, dict[str, Any]]:
    """Load bounded JSONL answers keyed by unique case_id."""
    close = False
    if str(source) == "-":
        stream = sys.stdin.buffer
        label = "stdin"
    else:
        stream = Path(source).open("rb")
        close = True
        label = str(source)
    answers: dict[str, dict[str, Any]] = {}
    try:
        for line_number, raw in enumerate(stream, start=1):
            if len(raw) > MAX_ANSWER_LINE_BYTES:
                raise BenchError(f"{label}:{line_number} exceeds the answer line limit")
            if not raw.strip():
                continue
            if len(answers) >= MAX_CASES:
                raise BenchError(f"answers exceeds the {MAX_CASES}-line limit")
            try:
                item = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BenchError(f"{label}:{line_number} is not valid UTF-8 JSON") from exc
            if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
                raise BenchError(f"{label}:{line_number} must be an object with case_id")
            case_id = item["case_id"]
            if case_id in answers:
                raise BenchError(f"duplicate answer for case_id: {case_id}")
            answers[case_id] = item
    finally:
        if close:
            stream.close()
    return answers


def _grade_value(case: dict[str, Any], answer: dict[str, Any]) -> str | None:
    if "value" not in answer:
        return "missing_value"
    if case["evaluator"] == "quantity":
        try:
            actual = parse_answer_quantity(answer["value"], field="answer.value")
        except BenchError:
            return "invalid_quantity"
        expected = parse_quantity(case["expected"], field="case.expected")
        return None if actual == expected else "value_mismatch"
    try:
        return None if canonical_json(answer["value"]) == canonical_json(case["expected"]) else "value_mismatch"
    except BenchError:
        return "invalid_json_value"


def score_answers(bundle: dict[str, Any], answers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Score structured answers against exact values and pinned evidence fields."""
    validate_bundle(bundle)
    expected_ids = {case["id"] for case in bundle["cases"]}
    unexpected = sorted(set(answers) - expected_ids)
    results: list[dict[str, Any]] = []
    for case in bundle["cases"]:
        reasons: list[str] = []
        answer = answers.get(case["id"])
        if answer is None:
            reasons.append("missing_answer")
        else:
            try:
                answer_block = parse_answer_quantity(
                    answer.get("block_number"), field="answer.block_number"
                )
                expected_block = parse_quantity(bundle["block"]["number"], field="block.number")
                if answer_block != expected_block:
                    reasons.append("block_number_mismatch")
            except BenchError:
                reasons.append("invalid_block_number")
            block_hash = answer.get("block_hash")
            if not isinstance(block_hash, str) or block_hash.lower() != bundle["block"]["hash"].lower():
                reasons.append("block_hash_mismatch")
            value_reason = _grade_value(case, answer)
            if value_reason:
                reasons.append(value_reason)
        results.append(
            {
                "case_id": case["id"],
                "reasons": reasons,
                "status": "pass" if not reasons else "fail",
            }
        )
    for case_id in unexpected:
        results.append(
            {
                "case_id": case_id,
                "reasons": ["unexpected_answer"],
                "status": "fail",
            }
        )
    passed = sum(item["status"] == "pass" for item in results)
    total = len(results)
    return {
        "block_hash": bundle["block"]["hash"],
        "block_number": bundle["block"]["number"],
        "chain_id": bundle["chain_id"],
        "failed": total - passed,
        "passed": passed,
        "results": results,
        "score_percent": round(100.0 * passed / total, 2),
        "total": total,
        "unexpected_answer_ids": unexpected,
    }


def render_table(report: dict[str, Any], *, color: bool = False) -> str:
    """Render a stable terminal board; ANSI is opt-in and never used for pipes."""
    green = "\x1b[32m" if color else ""
    red = "\x1b[31m" if color else ""
    reset = "\x1b[0m" if color else ""
    width = max(7, *(len(item["case_id"]) for item in report["results"]))
    lines = [
        "ChainFactBench result",
        f"chain={report['chain_id']} block={report['block_number']} hash={report['block_hash']}",
        f"{'CASE'.ljust(width)}  STATUS  REASON",
        f"{'-' * width}  ------  ------",
    ]
    for item in report["results"]:
        passed = item["status"] == "pass"
        tint = green if passed else red
        reason = ",".join(item["reasons"]) if item["reasons"] else "exact"
        lines.append(
            f"{item['case_id'].ljust(width)}  {tint}{item['status'].upper().ljust(6)}{reset}  {reason}"
        )
    lines.append(
        f"score={report['passed']}/{report['total']} ({report['score_percent']:.2f}%) "
        f"unexpected={len(report['unexpected_answer_ids'])}"
    )
    return "\n".join(lines) + "\n"
