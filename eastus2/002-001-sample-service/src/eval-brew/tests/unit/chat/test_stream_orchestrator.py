"""StreamOrchestrator unit tests (017 US3/US7) — happy path + failure modes.

Uses httpx.MockTransport to control SSE bytes without a real server.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest

from harness.chat.event_bus import TurnEventBus
from harness.chat.stream_orchestrator import _aiter_with_timeout, _iter_sse_events


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- _iter_sse_events
def _make_response(body: str) -> httpx.Response:
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


def test_iter_sse_single_event() -> None:
    async def _test():
        resp = _make_response("event: token\ndata: {\"content\":\"hi\"}\n\n")
        events = []
        async for name, data in _iter_sse_events(resp, timeout_seconds=5):
            events.append((name, data))
        assert events == [("token", '{"content":"hi"}')]
    _run(_test())


def test_iter_sse_multiple_events() -> None:
    async def _test():
        body = "event: token\ndata: A\n\nevent: contract\ndata: {}\n\n"
        resp = _make_response(body)
        events = []
        async for name, data in _iter_sse_events(resp, timeout_seconds=5):
            events.append((name, data))
        assert [e[0] for e in events] == ["token", "contract"]
    _run(_test())


def test_iter_sse_ignores_comment_lines() -> None:
    async def _test():
        body = ": this is a comment\nevent: token\ndata: hi\n\n"
        resp = _make_response(body)
        events = []
        async for name, data in _iter_sse_events(resp, timeout_seconds=5):
            events.append((name, data))
        assert len(events) == 1
        assert events[0] == ("token", "hi")
    _run(_test())


def test_iter_sse_multiline_data() -> None:
    async def _test():
        body = "event: info\ndata: line1\ndata: line2\n\n"
        resp = _make_response(body)
        events = []
        async for name, data in _iter_sse_events(resp, timeout_seconds=5):
            events.append((name, data))
        assert events[0] == ("info", "line1\nline2")
    _run(_test())


# --------------------------------------------------------------------------- _aiter_with_timeout
def test_aiter_with_timeout_passes_through_items() -> None:
    async def _test():
        async def _source():
            for i in range(3):
                yield i

        items = []
        async for item in _aiter_with_timeout(_source(), timeout_seconds=5):
            items.append(item)
        assert items == [0, 1, 2]
    _run(_test())


def test_aiter_with_timeout_raises_on_stall() -> None:
    async def _test():
        async def _slow_source():
            yield "first"
            await asyncio.sleep(100)
            yield "never"

        with pytest.raises(asyncio.TimeoutError):
            async for _ in _aiter_with_timeout(_slow_source(), timeout_seconds=0.01):
                pass
    _run(_test())


# --------------------------------------------------------------------------- run_turn (mocked)
def _sse_body(*events: tuple[str, str]) -> str:
    parts = []
    for name, data in events:
        parts.append(f"event: {name}\ndata: {data}\n\n")
    return "".join(parts)


def _setup_db(tmp_path, monkeypatch, db_name="orch"):
    from harness.persistence import encryption, engine as eng
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / f"{db_name}.key"))
    encryption._reset_key_cache_for_tests()
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    eng.init_db()
    return eng


def _seed_turn(eng, db_name):
    from harness.persistence.repositories.connector_registration import ConnectorRegistrationRepository
    from harness.persistence.repositories.evaluator_registration import EvaluationAgentRegistrationRepository
    from harness.chat.session_service import ChatSessionService
    from harness.chat.turn_service import TurnService
    from sqlalchemy import select
    from harness.persistence.models.connector_registration import ConnectorRegistration
    from harness.persistence.models.evaluator_registration import EvaluationAgentRegistration

    with eng.get_session() as db:
        ConnectorRegistrationRepository(db).create({
            "display_name": "C", "endpoint_url": "https://conn.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 5,
            "expects_per_row_password": False, "supports_sse": True,
        })
        EvaluationAgentRegistrationRepository(db).create({
            "display_name": "E", "description": "e", "endpoint_url": "https://eval.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 5,
            "declared_scoring_dimensions": [], "supports_sse": True,
        })
        cid = db.scalar(select(ConnectorRegistration.connector_id))
        eid = db.scalar(select(EvaluationAgentRegistration.evaluation_agent_id))
        sess = ChatSessionService(db).create_session("S", cid, "uid", "pw", eid, "oid-1")
        turn = TurnService(db).create_turn(sess.chat_session_id, "hello")
        return sess.chat_session_id, turn.turn_id


def test_run_turn_happy_path(monkeypatch, tmp_path) -> None:
    eng = _setup_db(tmp_path, monkeypatch, "orch1")
    session_id, turn_id = _seed_turn(eng, "orch1")

    contract_payload = json.dumps({"utteranceId": "u-1", "utteranceText": "hello", "chatbotResponse": {"normalizedText": "hi"}})
    connector_body = _sse_body(
        ("token", json.dumps({"content": "hi"})),
        ("contract", contract_payload),
    )
    evaluator_body = _sse_body(
        ("score", json.dumps({"relevance": 0.9})),
        ("final", json.dumps({"verdict": "pass"})),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "conn" in str(request.url):
            return httpx.Response(200, content=connector_body.encode(),
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, content=evaluator_body.encode(),
                              headers={"content-type": "text/event-stream"})

    _real_client = httpx.AsyncClient  # capture before patch

    monkeypatch.setattr(
        "harness.chat.stream_orchestrator.httpx.AsyncClient",
        lambda **kw: _real_client(transport=httpx.MockTransport(handler)),
    )

    published = []

    class _Bus(TurnEventBus):
        async def publish(self, event):
            published.append(event)
            await super().publish(event)

    async def _test():
        bus = _Bus()
        from harness.chat.stream_orchestrator import run_turn
        await run_turn(turn_id, session_id, "hello", bus)

    _run(_test())

    event_names = [e["event"] for e in published]
    assert "connector_token" in event_names
    assert "evaluating" in event_names
    assert "evaluator_event" in event_names
    assert "turn_complete" in event_names
    assert "turn_failed" not in event_names

    with eng.get_session() as db:
        from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
        t = ChatSessionRepository(db).get_turn(turn_id, session_id)
        assert t.status == "completed"
        assert t.result is not None
        assert "hi" in t.result.assembled_response


def test_run_turn_connector_http_error(monkeypatch, tmp_path) -> None:
    eng = _setup_db(tmp_path, monkeypatch, "orch2")
    session_id, turn_id = _seed_turn(eng, "orch2")

    def handler(request):
        return httpx.Response(503)

    _real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "harness.chat.stream_orchestrator.httpx.AsyncClient",
        lambda **kw: _real_client(transport=httpx.MockTransport(handler)),
    )

    published = []

    class _Bus(TurnEventBus):
        async def publish(self, event):
            published.append(event)
            await super().publish(event)

    async def _test():
        bus = _Bus()
        from harness.chat.stream_orchestrator import run_turn
        await run_turn(turn_id, session_id, "hi", bus)

    _run(_test())

    event_names = [e["event"] for e in published]
    assert "turn_failed" in event_names

    with eng.get_session() as db:
        from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
        t = ChatSessionRepository(db).get_turn(turn_id, session_id)
        assert t.status == "failed"
        assert t.result.error_stage == "connector_stream"


def test_run_turn_contract_validation_failure(monkeypatch, tmp_path) -> None:
    eng = _setup_db(tmp_path, monkeypatch, "orch3")
    session_id, turn_id = _seed_turn(eng, "orch3")

    bad_contract = json.dumps({"wrong_key": "value"})
    connector_body = _sse_body(
        ("token", json.dumps({"content": "partial"})),
        ("contract", bad_contract),
    )

    def handler(request):
        if "conn" in str(request.url):
            return httpx.Response(200, content=connector_body.encode(),
                                  headers={"content-type": "text/event-stream"})
        raise AssertionError("Evaluator must NOT be called on contract validation failure")

    _real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "harness.chat.stream_orchestrator.httpx.AsyncClient",
        lambda **kw: _real_client(transport=httpx.MockTransport(handler)),
    )

    published = []

    class _Bus(TurnEventBus):
        async def publish(self, event):
            published.append(event)
            await super().publish(event)

    async def _test():
        bus = _Bus()
        from harness.chat.stream_orchestrator import run_turn
        await run_turn(turn_id, session_id, "hi", bus)

    _run(_test())

    event_names = [e["event"] for e in published]
    assert "turn_failed" in event_names

    with eng.get_session() as db:
        from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
        t = ChatSessionRepository(db).get_turn(turn_id, session_id)
        assert t.status == "failed"
        assert t.result.error_stage == "connector_normalization"
