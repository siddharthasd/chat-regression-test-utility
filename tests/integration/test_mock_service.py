"""Bundled mock connector service tests (US4, FR-018-022, SC-011).

Runs the mock over a real localhost port with zero external setup.
"""

from __future__ import annotations

import contextlib
import threading

import httpx

from harness.connector import mock
from harness.contract import validate_contract


@contextlib.contextmanager
def running(mode: str = "ok", slow_seconds: int = 5):
    server = mock.make_server(port=0, mode=mode, slow_seconds=slow_seconds)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_mock_emits_conformant_contract() -> None:
    with running() as url:
        resp = httpx.post(url, json={"testId": "t1", "utteranceText": "hello"}, timeout=5)
    assert resp.status_code == 200
    body = resp.json()
    assert body["connectorId"] == "mock"
    assert body["testId"] == "t1"
    assert validate_contract(body).valid  # FR-019


def test_mode_status500() -> None:
    with running(mode="status500") as url:
        resp = httpx.post(url, json={"testId": "t", "utteranceText": "h"}, timeout=5)
    assert resp.status_code == 500


def test_mode_nonconformant() -> None:
    with running(mode="nonconformant") as url:
        resp = httpx.post(url, json={"testId": "t", "utteranceText": "h"}, timeout=5)
    assert resp.status_code == 200
    assert not validate_contract(resp.json()).valid


def test_mock_zero_external_setup() -> None:
    # SC-011: no real chatbot, no credentials, no internet — just a free local port.
    with running() as url:
        resp = httpx.post(url, json={"testId": "t", "utteranceText": "x"}, timeout=5)
    assert resp.status_code == 200
