"""Per-turn asyncio event bus for streaming connector/evaluator events to the browser.

Each ChatTurn gets one TurnEventBus instance for the duration of its pipeline
execution. The bus buffers all published events so that late or reconnecting
browser SSE clients can replay from the start (cursor=0).
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

_registry: dict[str, "TurnEventBus"] = {}


class TurnEventBus:
    """Ordered buffer + pub/sub for one turn's browser SSE events."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._condition = asyncio.Condition()
        self._done = False

    async def publish(self, event: dict[str, Any]) -> None:
        """Append an event and wake all streaming readers."""
        async with self._condition:
            self._events.append(event)
            self._condition.notify_all()

    async def mark_complete(self) -> None:
        """Signal that no more events will be published for this turn."""
        async with self._condition:
            self._done = True
            self._condition.notify_all()

    async def stream_from(self, cursor: int = 0) -> AsyncIterator[dict[str, Any]]:
        """Async generator: yield buffered events from *cursor*, then stream live events.

        Callers may call this multiple times with cursor=0 for reconnect replay.
        Returns after the bus is marked complete and all events have been yielded.
        """
        pos = cursor
        while True:
            async with self._condition:
                # Yield everything currently buffered ahead of pos.
                while pos < len(self._events):
                    yield self._events[pos]
                    pos += 1
                # If done and nothing left, exit.
                if self._done and pos >= len(self._events):
                    return
                # Wait for new events or completion.
                await self._condition.wait()


def create_bus(turn_id: str) -> TurnEventBus:
    """Create and register a new TurnEventBus for *turn_id*."""
    bus = TurnEventBus()
    _registry[turn_id] = bus
    return bus


def get_bus(turn_id: str) -> TurnEventBus | None:
    """Return the registered bus for *turn_id*, or None if not found."""
    return _registry.get(turn_id)


def remove_bus(turn_id: str) -> None:
    """Remove the bus for *turn_id* from the registry (call after stream closes)."""
    _registry.pop(turn_id, None)
