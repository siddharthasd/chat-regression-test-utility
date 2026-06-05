"""End-to-end: a job whose connector AND evaluator use client-credentials auth.

Proves the OAuth2 client-credentials descriptor survives the whole pipeline —
registration (with `clientSecret` encrypted at rest) → job snapshot → orchestrator
dispatch — and that a real token is fetched from the token endpoint and attached.
A counting stub token server verifies the in-process cache fetches each service's
token exactly once per job (not once per row): with two rows and two distinct
clients, the token endpoint sees exactly two grants.
"""

from __future__ import annotations

import json
import os
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest

from harness.connector import mock as conn_mock
from harness.csv_upload import process_upload
from harness.evaluator import mock as ev_mock
from harness.orchestrator import run_job
from harness.persistence import get_session
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    JobRepository,
)
from harness.remote import oauth


class _TokenHandler(BaseHTTPRequestHandler):
    calls: list[dict]  # bound per-subclass in _make_token_server

    def log_message(self, *args) -> None:  # noqa: ANN002 — silence default logging
        pass

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        type(self).calls.append(parse_qs(body.decode("utf-8")))
        payload = json.dumps(
            {"access_token": "TKN", "token_type": "Bearer", "expires_in": 3600}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _make_token_server() -> tuple[ThreadingHTTPServer, list[dict]]:
    calls: list[dict] = []
    handler = type("_BoundTokenHandler", (_TokenHandler,), {"calls": calls})
    return ThreadingHTTPServer(("127.0.0.1", 0), handler), calls


def _serve(server) -> str:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    return f"http://{host}:{port}/"


def _cc(token_url: str, client_id: str, secret: str) -> dict:
    return {
        "mode": "client-credentials",
        "tokenUrl": token_url,
        "clientId": client_id,
        "clientSecret": secret,
        "scope": "api.read",
    }


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """Register a cc connector + cc evaluator and run one real two-row job."""
    tmp = tmp_path_factory.mktemp("cc_e2e")
    db_path = tmp / "cc.db"
    prev = {k: os.environ.get(k) for k in ("HARNESS_DB_PATH", "HARNESS_KEY_FILE")}
    os.environ["HARNESS_DB_PATH"] = str(db_path)
    os.environ["HARNESS_KEY_FILE"] = str(tmp / "cc.key")

    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(db_path)
    oauth.reset_token_cache()

    connector = conn_mock.make_server(mode="ok")
    evaluator = ev_mock.make_server(mode="ok")
    token_server, token_calls = _make_token_server()
    conn_url = _serve(connector)
    eval_url = _serve(evaluator)
    token_url = _serve(token_server)

    try:
        with get_session() as session:
            conn_reg = ConnectorRegistrationRepository(session).create(
                {
                    "display_name": "CC Connector",
                    "endpoint_url": conn_url,
                    "auth_descriptor": _cc(token_url, "conn-client", "conn-secret"),
                    "timeout_seconds": 30,
                    "expects_per_row_password": False,
                }
            )
            eval_reg = EvaluationAgentRegistrationRepository(session).create(
                {
                    "display_name": "CC Evaluator",
                    "description": "scores relevance",
                    "endpoint_url": eval_url,
                    "auth_descriptor": _cc(token_url, "eval-client", "eval-secret"),
                    "timeout_seconds": 60,
                    "declared_scoring_dimensions": ["relevance"],
                }
            )
            # clientSecret must be ciphertext at rest (encrypted on create).
            assert conn_reg.auth_descriptor["clientSecret"] != "conn-secret"

            jobs = JobRepository(session)
            job = jobs.create_draft("CC Job", None, "alice")
            jobs.set_connector_snapshot(job.job_id, conn_reg)
            jobs.set_evaluator_snapshot(job.job_id, eval_reg)
            job_id = job.job_id

        csv_path = tmp / "in.csv"
        csv_path.write_text(
            "utteranceText,testId\nhello,t-1\nhowdy,t-2\n", encoding="utf-8"
        )
        assert process_upload(job_id, str(csv_path)).success
        with get_session() as session:
            JobRepository(session).transition_to_queued(job_id)
        run_job(job_id)

        with get_session() as session:
            final = JobRepository(session).get(job_id)
            yield SimpleNamespace(
                status=str(final.status),
                processed=final.processed_count,
                failed=final.failed_count,
                total=final.total_utterance_count,
                token_calls=token_calls,
            )
    finally:
        connector.shutdown()
        evaluator.shutdown()
        token_server.shutdown()
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_job_completed_all_rows_passed(run) -> None:
    assert run.status == "completed"
    assert run.total == 2
    assert run.processed == 2
    assert run.failed == 0  # token fetched + attached; both hops succeeded


def test_token_fetched_once_per_service_not_per_row(run) -> None:
    """Two rows, two distinct clients → exactly two grants (cache reuse across rows)."""
    client_ids = Counter(c["client_id"][0] for c in run.token_calls)
    assert client_ids == {"conn-client": 1, "eval-client": 1}


def test_token_request_used_client_credentials_grant(run) -> None:
    for call in run.token_calls:
        assert call["grant_type"] == ["client_credentials"]
        assert call["scope"] == ["api.read"]
    # The decrypted secrets reached the token endpoint (proves at-rest round-trip).
    secrets = {c["client_id"][0]: c["client_secret"][0] for c in run.token_calls}
    assert secrets == {"conn-client": "conn-secret", "eval-client": "eval-secret"}
