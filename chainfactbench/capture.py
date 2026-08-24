from __future__ import annotations

from typing import Any, Callable

from .core import (
    BLOCK_PARAMETER_INDEX,
    BenchError,
    SCHEMA_VERSION,
    sha256_json,
    validate_block_hash,
    validate_bundle,
    validate_capture_spec,
    parse_quantity,
)
from .rpc import RPCClient

Status = Callable[[str], None]


def _validated_header(value: Any, block_number: str, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchError(f"{field} returned no block object")
    if value.get("number") != block_number:
        raise BenchError(f"{field} block number does not match the requested block")
    validate_block_hash(value.get("hash"), field=f"{field}.hash")
    return value


def capture_bundle(
    spec: dict[str, Any],
    client: RPCClient,
    *,
    status: Status | None = None,
) -> dict[str, Any]:
    """Capture allowlisted read-only facts and bind them to a stable block hash."""
    validate_capture_spec(spec)
    block_number = spec["block_number"]
    parse_quantity(block_number, field="block_number")
    if status:
        status("Resolving chain id and pinned block header")
    chain_id = client.call("eth_chainId", [], 1)
    parse_quantity(chain_id, field="RPC chain id")
    before = _validated_header(
        client.call("eth_getBlockByNumber", [block_number, False], 2),
        block_number,
        field="initial header",
    )
    block_hash = before["hash"].lower()

    captured_cases: list[dict[str, Any]] = []
    for offset, requested in enumerate(spec["cases"], start=3):
        if status:
            status(f"Capturing case {len(captured_cases) + 1}/{len(spec['cases'])}: {requested['id']}")
        params = list(requested["params"])
        params[BLOCK_PARAMETER_INDEX[requested["method"]]] = block_number
        result = client.call(requested["method"], params, offset)
        if requested["evaluator"] == "quantity":
            parse_quantity(result, field=f"RPC result for {requested['id']}")
        captured_cases.append(
            {
                "evaluator": requested["evaluator"],
                "expected": result,
                "expected_sha256": sha256_json(result),
                "id": requested["id"],
                "method": requested["method"],
                "params": params,
                "prompt": requested["prompt"],
            }
        )

    if status:
        status("Rechecking pinned block hash for reorganization")
    after = _validated_header(
        client.call("eth_getBlockByNumber", [block_number, False], 3 + len(captured_cases)),
        block_number,
        field="final header",
    )
    if after["hash"].lower() != block_hash:
        raise BenchError("pinned block hash changed during capture; discard and retry")

    bundle = {
        "block": {"hash": block_hash, "number": block_number},
        "cases": captured_cases,
        "chain_id": chain_id,
        "schema_version": SCHEMA_VERSION,
    }
    return validate_bundle(bundle)

