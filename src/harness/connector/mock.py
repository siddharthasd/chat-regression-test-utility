"""Bundled mock connector service (FR-018-022, R2).

A stdlib-only HTTP server implementing the connector wire protocol. Launchable
standalone (`python -m harness.connector.mock`, `harness mock-connector`) or as a
child process / in-process server in tests. Deterministic; parameterized error
modes drive the SC-008/009/010 paths.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MOCK_CONNECTOR_ID = "mock"
MODES = ("ok", "nonconformant", "status500", "slow")


def build_contract(test_id: str, utterance_text: str) -> dict:
    """A deterministic Standard Evaluation Contract instance reflecting the input."""
    return {
        "contractVersion": "1",
        "utteranceId": str(uuid.uuid4()),
        "utteranceText": utterance_text,
        "testId": test_id,
        "conversationContext": None,
        "connectorId": MOCK_CONNECTOR_ID,
        "timestamp": datetime.now(UTC).isoformat(),
        "chatbotResponse": {
            "rawPayload": {"echo": utterance_text},
            "normalizedText": f"Echo: {utterance_text}",
            "agentChain": [],
            "metadata": {},
        },
    }


class _MockHandler(BaseHTTPRequestHandler):
    mode = "ok"
    slow_seconds = 5

    def log_message(self, *args) -> None:  # noqa: ANN002 — silence default stderr logging
        pass

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(raw or b"{}")
        except ValueError:
            request = {}
        test_id = request.get("testId", "unknown")
        utterance = request.get("utteranceText", "")

        mode = os.environ.get("HARNESS_MOCK_MODE", self.mode)
        if mode == "status500":
            self._send(500, {"error": "mock failure"})
        elif mode == "nonconformant":
            self._send(200, {"not": "a valid contract"})
        elif mode == "slow":
            time.sleep(self.slow_seconds)
            self._send(200, build_contract(test_id, utterance))
        else:  # "ok"
            self._send(200, build_contract(test_id, utterance))

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_server(
    host: str = "127.0.0.1", port: int = 0, mode: str = "ok", slow_seconds: int = 5
) -> ThreadingHTTPServer:
    """Build (but do not start) a mock connector server. `port=0` picks a free port."""
    handler = type(
        "_BoundMockHandler", (_MockHandler,), {"mode": mode, "slow_seconds": slow_seconds}
    )
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="harness-mock-connector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--mode", choices=MODES, default="ok")
    parser.add_argument("--slow-seconds", type=int, default=5)
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port, args.mode, args.slow_seconds)
    host, port = server.server_address[0], server.server_address[1]
    print(f"mock connector listening on http://{host}:{port} (mode={args.mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
