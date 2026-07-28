"""Per-job SSE event bus for the headless execution API (020).

Each headless job gets one HeadlessJobEventBus for the duration of its
execution. The bus buffers all events so that late-connecting clients receive
the full event history including the terminal event (late-connect replay).

The engine runs on sync daemon threads; `push()` must be called via
`loop.call_soon_threadsafe(bus.push, event_type, payload)` to safely cross
the thread boundary into the asyncio event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

_buses: dict[str, "HeadlessJobEventBus"] = {}

_TERMINAL_EVENTS = frozenset({"job_complete", "job_failed"})


class HeadlessJobEventBus:
    """Ordered, replayable event buffer for one headless job's SSE stream."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._ready = asyncio.Event()
        self._closed = False

    def push(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append an event and wake waiting stream consumers.

        Must be called from within the asyncio event loop thread — use
        ``loop.call_soon_threadsafe(bus.push, ...)`` from engine threads.
        """
        self._events.append({"event": event_type, "data": payload})
        self._ready.set()
        if event_type in _TERMINAL_EVENTS:
            self._closed = True

    async def stream(self, cursor: int = 0) -> AsyncIterator[dict[str, Any]]:
        """Yield events from *cursor* onward; wait for new events when caught up.

        Exits after yielding the terminal event. Late-connecting clients
        (cursor=0 after the bus is closed) receive the full history and exit
        immediately.
        """
        while True:
            while cursor < len(self._events):
                yield self._events[cursor]
                cursor += 1
            if self._closed:
                return
            self._ready.clear()
            await self._ready.wait()


def create_bus(job_id: str) -> HeadlessJobEventBus:
    """Create and register a new event bus for *job_id*."""
    bus = HeadlessJobEventBus()
    _buses[job_id] = bus
    return bus


def get_bus(job_id: str) -> HeadlessJobEventBus | None:
    """Return the registered bus for *job_id*, or None."""
    return _buses.get(job_id)


def remove_bus(job_id: str) -> None:
    """Remove the bus for *job_id* from the registry."""
    _buses.pop(job_id, None)
