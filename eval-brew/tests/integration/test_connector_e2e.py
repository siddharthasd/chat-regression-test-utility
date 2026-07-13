"""End-to-end connector tests over a real mock server (US1/US2/US4).

Covers SC-001/002/006/008/009/010 against a running connector service.
"""

from __future__ import annotations

import contextlib
import threading

from harness.connector import (
    ConnectorRegistryReader,
    ConnectorSnapshot,
    UtteranceRow,
    dispatch_utterance,
    mock,
)
from harness.contract import validate_contract
from harness.persistence.repositories import ConnectorRegistrationRepository


@contextlib.contextmanager
def running(mode: str = "ok", slow_seconds: int = 5):
    server = mock.make_server(port=0, mode=mode, slow_seconds=slow_seconds)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def _snap(url: str, timeout: int = 10) -> ConnectorSnapshot:
    return ConnectorSnapshot("mock", url, {"mode": "none"}, timeout, False)


def test_three_rows_all_ok_and_valid() -> None:
    with running() as url:
        snap = _snap(url)
        results = [dispatch_utterance(snap, UtteranceRow(f"t{i}", f"u{i}")) for i in range(3)]
    assert all(r.ok and validate_contract(r.contract).valid for r in results)  # SC-001


def test_register_and_run_mock_no_core_change(db_session) -> None:
    # SC-002: register via 009 repo, discover via the read facade, run — no source change.
    with running() as url:
        reg = ConnectorRegistrationRepository(db_session).create(
            {"display_name": "Mock", "endpoint_url": url, "auth_descriptor": {"mode": "none"}}
        )
        reader = ConnectorRegistryReader(db_session)
        assert reg.connector_id in {e.connector_id for e in reader.list_active()}
        full = reader.get(reg.connector_id)
        snap = ConnectorSnapshot(
            full.connector_id,
            full.endpoint_url,
            full.auth_descriptor,
            full.timeout_seconds,
            full.expects_per_row_password,
        )
        result = dispatch_utterance(snap, UtteranceRow("t1", "hi"))
    assert result.ok


def test_non_2xx_is_connector_response() -> None:
    with running(mode="status500") as url:
        result = dispatch_utterance(_snap(url), UtteranceRow("t", "h"))
    assert result.error_stage == "connector_response"  # SC-008


def test_nonconformant_is_connector_normalization() -> None:
    with running(mode="nonconformant") as url:
        result = dispatch_utterance(_snap(url), UtteranceRow("t", "h"))
    assert result.error_stage == "connector_normalization"  # SC-009


def test_slow_is_connector_transport() -> None:
    with running(mode="slow", slow_seconds=3) as url:
        result = dispatch_utterance(_snap(url, timeout=1), UtteranceRow("t", "h"))  # 1s < 3s
    assert result.error_stage == "connector_transport"  # SC-010
