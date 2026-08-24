from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from chainfactbench.capture import capture_bundle
from chainfactbench.core import load_json_source
from chainfactbench.rpc import RPCClient

ROOT = Path(__file__).resolve().parents[1]
BLOCK_HASH = "0x" + "a" * 64


class MockRPCHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - HTTP server API
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        type(self).requests.append(request)
        method = request["method"]
        if method == "eth_chainId":
            result: Any = "0x1"
        elif method == "eth_getBlockByNumber":
            result = {"hash": BLOCK_HASH, "number": "0x10"}
        elif method == "eth_getBalance":
            result = "0x2a"
        else:
            self.send_error(500)
            return
        body = json.dumps({"id": request["id"], "jsonrpc": "2.0", "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


class CaptureIntegrationTests(unittest.TestCase):
    def test_capture_is_read_only_and_rechecks_header(self) -> None:
        MockRPCHandler.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockRPCHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            spec = load_json_source(ROOT / "examples" / "capture_spec.json")
            endpoint = f"http://127.0.0.1:{server.server_port}"
            bundle = capture_bundle(spec, RPCClient(endpoint))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(bundle["block"]["hash"], BLOCK_HASH)
        self.assertEqual(bundle["cases"][0]["expected"], "0x2a")
        methods = [request["method"] for request in MockRPCHandler.requests]
        self.assertEqual(
            methods,
            ["eth_chainId", "eth_getBlockByNumber", "eth_getBalance", "eth_getBlockByNumber"],
        )
        self.assertEqual(MockRPCHandler.requests[2]["params"][1], "0x10")
        self.assertTrue(all(not method.startswith("eth_send") for method in methods))


if __name__ == "__main__":
    unittest.main()

