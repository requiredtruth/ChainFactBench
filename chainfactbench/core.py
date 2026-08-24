from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_CASES = 10_000
MAX_PROMPT_CHARS = 4_096
MAX_ANSWER_LINE_BYTES = 64 * 1024

BLOCK_PARAMETER_INDEX = {
    "eth_getBalance": 1,
    "eth_getBlockByNumber": 0,
    "eth_getBlockTransactionCountByNumber": 0,
    "eth_getCode": 1,
    "eth_getProof": 2,
    "eth_getStorageAt": 2,
    "eth_getTransactionCount": 1,
    "eth_call": 1,
}
MUTABLE_BLOCK_TAGS = {"latest", "pending", "safe", "finalized"}
EVALUATORS = {"json_exact", "quantity"}
CASE_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
QUANTITY_RE = re.compile(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)\Z")
DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")


class BenchError(ValueError):
    """Raised when benchmark input violates a deterministic contract."""


def canonical_json(value: Any) -> str:
    """Return stable UTF-8 JSON text or raise BenchError for non-finite values."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise BenchError(f"value is not canonical JSON: {exc}") from exc


def sha256_json(value: Any) -> str:
    """Hash a value's canonical JSON representation with SHA-256."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_quantity(value: Any, *, field: str) -> int:
    """Parse a minimal EIP-1474 hex quantity."""
    if not isinstance(value, str) or not QUANTITY_RE.fullmatch(value):
        raise BenchError(f"{field} must be a minimal 0x-prefixed hex quantity")
    return int(value[2:], 16)


def parse_answer_quantity(value: Any, *, field: str) -> int:
    """Parse a non-negative model answer expressed as int, decimal, or quantity."""
    if isinstance(value, bool):
        raise BenchError(f"{field} must be a non-negative integer, not boolean")
    if isinstance(value, int):
        if value < 0:
            raise BenchError(f"{field} must be non-negative")
        return value
    if isinstance(value, str):
        if QUANTITY_RE.fullmatch(value):
            return int(value[2:], 16)
        if DECIMAL_RE.fullmatch(value):
            return int(value, 10)
    raise BenchError(f"{field} must be a non-negative integer, decimal string, or hex quantity")


def validate_block_hash(value: Any, *, field: str) -> str:
    """Validate and normalize a 32-byte 0x-prefixed hash."""
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise BenchError(f"{field} must be a 32-byte 0x-prefixed hash")
    return value.lower()


def _read_bounded(stream: BinaryIO, limit: int, *, label: str) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise BenchError(f"{label} exceeds the {limit}-byte input limit")
    return data


def load_json_source(source: str | Path, *, limit: int = MAX_INPUT_BYTES) -> Any:
    """Load one bounded JSON document from a path or '-' for stdin."""
    label = "stdin" if str(source) == "-" else str(source)
    try:
        if str(source) == "-":
            raw = _read_bounded(sys.stdin.buffer, limit, label=label)
        else:
            with Path(source).open("rb") as handle:
                raw = _read_bounded(handle, limit, label=label)
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise BenchError(f"{label} is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise BenchError(f"{label} is not valid JSON: line {exc.lineno} column {exc.colno}") from exc


def atomic_write_text(path: str | Path, text: str) -> None:
    """Atomically replace a UTF-8 text file with owner-readable mode 0640."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o640)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _reject_mutable_tags(value: Any, *, field: str) -> None:
    if isinstance(value, str) and value.lower() in MUTABLE_BLOCK_TAGS:
        raise BenchError(f"{field} contains mutable block tag {value!r}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_mutable_tags(item, field=f"{field}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_mutable_tags(item, field=f"{field}.{key}")


def validate_bundle(bundle: Any) -> dict[str, Any]:
    """Validate a complete frozen evidence bundle and return it unchanged."""
    if not isinstance(bundle, dict):
        raise BenchError("bundle root must be an object")
    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise BenchError(f"schema_version must equal {SCHEMA_VERSION}")
    parse_quantity(bundle.get("chain_id"), field="chain_id")

    block = bundle.get("block")
    if not isinstance(block, dict):
        raise BenchError("block must be an object")
    block_number = block.get("number")
    parse_quantity(block_number, field="block.number")
    block_hash = validate_block_hash(block.get("hash"), field="block.hash")

    cases = bundle.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchError("cases must be a non-empty array")
    if len(cases) > MAX_CASES:
        raise BenchError(f"cases exceeds the {MAX_CASES}-case limit")

    seen: set[str] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            raise BenchError(f"{label} must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
            raise BenchError(f"{label}.id must match {CASE_ID_RE.pattern}")
        if case_id in seen:
            raise BenchError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        prompt = case.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise BenchError(f"{label}.prompt must be non-empty text")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise BenchError(f"{label}.prompt exceeds {MAX_PROMPT_CHARS} characters")
        method = case.get("method")
        if method not in BLOCK_PARAMETER_INDEX:
            raise BenchError(f"{label}.method is not in the read-only allowlist")
        params = case.get("params")
        if not isinstance(params, list):
            raise BenchError(f"{label}.params must be an array")
        _reject_mutable_tags(params, field=f"{label}.params")
        position = BLOCK_PARAMETER_INDEX[method]
        if len(params) <= position:
            raise BenchError(f"{label}.params is missing the pinned block parameter")
        identifier = params[position]
        valid_number = identifier == block_number
        valid_hash = (
            isinstance(identifier, dict)
            and str(identifier.get("blockHash", "")).lower() == block_hash
            and identifier.get("requireCanonical") is True
        )
        if not (valid_number or valid_hash):
            raise BenchError(f"{label}.params does not reference the bundle's pinned block")
        evaluator = case.get("evaluator")
        if evaluator not in EVALUATORS:
            raise BenchError(f"{label}.evaluator must be one of {sorted(EVALUATORS)}")
        expected = case.get("expected")
        if evaluator == "quantity":
            parse_quantity(expected, field=f"{label}.expected")
        else:
            canonical_json(expected)
        digest = case.get("expected_sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise BenchError(f"{label}.expected_sha256 must be lowercase SHA-256")
        if digest != sha256_json(expected):
            raise BenchError(f"{label}.expected_sha256 does not match expected")
    return bundle


def validate_capture_spec(spec: Any) -> dict[str, Any]:
    """Validate a read-only capture specification before any network call."""
    if not isinstance(spec, dict):
        raise BenchError("capture specification root must be an object")
    if spec.get("schema_version") != SCHEMA_VERSION:
        raise BenchError(f"schema_version must equal {SCHEMA_VERSION}")
    parse_quantity(spec.get("block_number"), field="block_number")
    cases = spec.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchError("cases must be a non-empty array")
    if len(cases) > MAX_CASES:
        raise BenchError(f"cases exceeds the {MAX_CASES}-case limit")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            raise BenchError(f"{label} must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
            raise BenchError(f"{label}.id is invalid")
        if case_id in seen:
            raise BenchError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        prompt = case.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
            raise BenchError(f"{label}.prompt must contain 1..{MAX_PROMPT_CHARS} characters")
        method = case.get("method")
        if method not in BLOCK_PARAMETER_INDEX:
            raise BenchError(f"{label}.method is not in the read-only allowlist")
        params = case.get("params")
        if not isinstance(params, list):
            raise BenchError(f"{label}.params must be an array")
        _reject_mutable_tags(params, field=f"{label}.params")
        position = BLOCK_PARAMETER_INDEX[method]
        if len(params) <= position or params[position] != "$BLOCK":
            raise BenchError(f"{label}.params[{position}] must equal '$BLOCK'")
        if case.get("evaluator") not in EVALUATORS:
            raise BenchError(f"{label}.evaluator must be one of {sorted(EVALUATORS)}")
    return spec


def dump_json(value: Any) -> str:
    """Return stable human-readable JSON with one trailing newline."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
