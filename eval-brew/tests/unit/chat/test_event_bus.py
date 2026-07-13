"""TurnEventBus unit tests (017 US3)."""

from __future__ import annotations

import asyncio

from harness.chat.event_bus import TurnEventBus, create_bus, get_bus, remove_bus


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- basic
def test_publish_and_stream_from() -> None:
    async def _test():
        bus = TurnEventBus()
        await bus.publish({"event": "connector_token", "data": {"content": "hi"}})
        await bus.mark_complete()
        events = []
        async for ev in bus.stream_from(cursor=0):
            events.append(ev)
        assert len(events) == 1
        assert events[0]["event"] == "connector_token"
    _run(_test())


def test_stream_from_replay_from_cursor() -> None:
    async def _test():
        bus = TurnEventBus()
        await bus.publish({"event": "a"})
        await bus.publish({"event": "b"})
        await bus.publish({"event": "c"})
        await bus.mark_complete()
        events = []
        async for ev in bus.stream_from(cursor=1):
            events.append(ev)
        assert [e["event"] for e in events] == ["b", "c"]
    _run(_test())


def test_mark_complete_terminates_empty_stream() -> None:
    async def _test():
        bus = TurnEventBus()
        await bus.mark_complete()
        events = []
        async for ev in bus.stream_from(cursor=0):
            events.append(ev)
        assert events == []
    _run(_test())


def test_stream_receives_events_published_after_subscribe() -> None:
    async def _test():
        bus = TurnEventBus()

        async def producer():
            await asyncio.sleep(0)
            await bus.publish({"event": "late"})
            await bus.mark_complete()

        async def consumer():
            events = []
            async for ev in bus.stream_from(cursor=0):
                events.append(ev)
            return events

        results, _ = await asyncio.gather(consumer(), producer())
        assert len(results) == 1
        assert results[0]["event"] == "late"
    _run(_test())


def test_multiple_events_ordering() -> None:
    async def _test():
        bus = TurnEventBus()
        for i in range(5):
            await bus.publish({"event": "token", "idx": i})
        await bus.mark_complete()
        events = []
        async for ev in bus.stream_from(cursor=0):
            events.append(ev)
        assert [e["idx"] for e in events] == list(range(5))
    _run(_test())


def test_stream_from_cursor_zero_replays_all() -> None:
    async def _test():
        bus = TurnEventBus()
        await bus.publish({"event": "x"})
        await bus.publish({"event": "y"})
        await bus.mark_complete()
        events = []
        async for ev in bus.stream_from(cursor=0):
            events.append(ev)
        assert len(events) == 2
    _run(_test())


# --------------------------------------------------------------------------- registry
def test_create_get_remove_bus() -> None:
    bus = create_bus("turn-001")
    assert get_bus("turn-001") is bus
    remove_bus("turn-001")
    assert get_bus("turn-001") is None


def test_remove_nonexistent_bus_is_noop() -> None:
    remove_bus("does-not-exist")  # must not raise


def test_get_missing_bus_returns_none() -> None:
    assert get_bus("no-such-turn") is None
