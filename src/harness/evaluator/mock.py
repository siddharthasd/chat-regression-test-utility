"""Bundled mock evaluator service (FR-022-027, R2).

stdlib-only HTTP server implementing the evaluator wire protocol. Emits a
well-formed, randomized (unseeded) EvaluationResult — exercising the
non-determinism guarantee by construction. Parameterized error modes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MOCK_AGENT_ID = "mock-evaluator"
MODES = ("ok", "nonconformant", "status500", "slow", "unexpected_dims")
_VERDICTS = ("pass", "fail", "warn")
DEFAULT_DIMENSIONS = ("mock_dimension_a", "mock_dimension_b")


def build_result(
    utterance_id: str, dimensions: list[str], *, inject_unexpected: bool = False
) -> dict:
    """A well-formed, randomized EvaluationResult reflecting the input contract."""
    dims = list(dimensions)
    if inject_unexpected:
        dims = dims + ["UNDECLARED_DIM"]
    scores = [
        {
            "parameter_name": d,
            "score": round(random.random(), 3),  # noqa: S311 — non-crypto mock randomness
            "reasoning": f"mock score for {d}: {random.choice(('weak', 'ok', 'strong'))}",  # noqa: S311
        }
        for d in dims
    ]
    return {
        "utteranceId": utterance_id,
        "evaluationAgentId": MOCK_AGENT_ID,
        "evaluationTimestamp": datetime.now(UTC).isoformat(),
        "evaluationScores": scores,
        "evaluationVerdict": random.choice(_VERDICTS),  # noqa: S311
        "metadata": {"mock": True},
    }


class _MockEvaluatorHandler(BaseHTTPRequestHandler):
    mode = "ok"
    dimensions: tuple[str, ...] = DEFAULT_DIMENSIONS
    slow_seconds = 5

    def log_message(self, *args) -> None:  # noqa: ANN002 — silence default logging
        pass

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            contract = json.loads(raw or b"{}")
        except ValueError:
            contract = {}
        utterance_id = contract.get("utteranceId", "unknown")
        dims = list(self.dimensions)

        mode = os.environ.get("HARNESS_MOCK_MODE", self.mode)
        if mode == "status500":
            self._send(500, {"error": "mock evaluator failure"})
        elif mode == "nonconformant":
            self._send(200, {"verdict": "??", "missing": "fields"})
        elif mode == "slow":
            time.sleep(self.slow_seconds)
            self._send(200, build_result(utterance_id, dims))
        elif mode == "unexpected_dims":
            self._send(200, build_result(utterance_id, dims, inject_unexpected=True))
        else:  # "ok"
            self._send(200, build_result(utterance_id, dims))

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_server(
    host: str = "127.0.0.1",
    port: int = 0,
    mode: str = "ok",
    dimensions: list[str] | None = None,
    slow_seconds: int = 5,
) -> ThreadingHTTPServer:
    """Build (not start) a mock evaluator server. `port=0` picks a free port."""
    env_dims = os.environ.get("HARNESS_MOCK_DIMENSIONS")
    if dimensions is None and env_dims:
        dimensions = [d.strip() for d in env_dims.split(",") if d.strip()]
    handler = type(
        "_BoundMockEvaluatorHandler",
        (_MockEvaluatorHandler,),
        {
            "mode": mode,
            "dimensions": tuple(dimensions) if dimensions is not None else DEFAULT_DIMENSIONS,
            "slow_seconds": slow_seconds,
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="harness-mock-evaluator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--mode", choices=MODES, default="ok")
    parser.add_argument("--dimensions", default="", help="Comma-separated declared dimensions.")
    parser.add_argument("--slow-seconds", type=int, default=5)
    args = parser.parse_args(argv)
    dims = [d.strip() for d in args.dimensions.split(",") if d.strip()] or None
    server = make_server(args.host, args.port, args.mode, dims, args.slow_seconds)
    host, port = server.server_address[0], server.server_address[1]
    print(f"mock evaluator listening on http://{host}:{port} (mode={args.mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
