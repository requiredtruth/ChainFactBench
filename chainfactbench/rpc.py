from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .core import BenchError, canonical_json


class RPCError(BenchError):
    """Raised for a bounded transport or JSON-RPC failure."""


@dataclass(frozen=True)
class RPCClient:
    """Minimal JSON-RPC client that never persists or reports its endpoint."""

    endpoint: str
    timeout: float = 20.0
    max_response_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise RPCError("RPC endpoint must use http:// or https://")
        if not 0.1 <= self.timeout <= 120.0:
            raise RPCError("RPC timeout must be between 0.1 and 120 seconds")
        if not 1_024 <= self.max_response_bytes <= 64 * 1024 * 1024:
            raise RPCError("RPC response limit must be between 1024 and 67108864 bytes")

    def call(self, method: str, params: list[Any], request_id: int) -> Any:
        """Call one JSON-RPC method and return its result with bounded I/O."""
        payload = canonical_json(
            {"id": request_id, "jsonrpc": "2.0", "method": method, "params": params}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ChainFactBench/0.1"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RPCError(f"RPC transport failed ({exc.__class__.__name__})") from exc
        if len(raw) > self.max_response_bytes:
            raise RPCError("RPC response exceeded the configured byte limit")
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RPCError("RPC returned invalid UTF-8 JSON") from exc
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise RPCError("RPC response is not a JSON-RPC 2.0 object")
        if message.get("id") != request_id:
            raise RPCError("RPC response id does not match request id")
        if "error" in message:
            error = message["error"]
            code = error.get("code") if isinstance(error, dict) else "unknown"
            raise RPCError(f"RPC method {method} failed with code {code}")
        if "result" not in message:
            raise RPCError("RPC response has neither result nor error")
        return message["result"]

