"""Event bus for decoupled, typed pub/sub messaging within a simulation tick."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

import structlog

log = structlog.get_logger()


@dataclass
class Event:
    """Base class for all typed events."""

    pass


Handler = Callable[..., None]


class EventBus:
    """Synchronous, in-process event bus with cascade support.

    Events are queued by emit() and delivered to subscribers only when
    drain() is called.  Handlers may themselves call emit(), causing
    secondary events to be appended to the queue; drain() continues until
    the queue is empty, so cascades are handled naturally.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Handler]] = defaultdict(list)
        self._queue: deque[Event] = deque()

    def subscribe(self, event_type: type[Event], handler: Handler) -> None:
        """Register *handler* to be called whenever *event_type* is drained."""
        self._handlers[event_type].append(handler)
        log.debug("subscribed", handler=str(handler), event_type=event_type.__name__)

    def emit(self, event: Event) -> None:
        """Queue *event* for delivery on the next drain()."""
        self._queue.append(event)
        log.debug("queued", event_type=type(event).__name__)

    def drain(self, max_iterations: int = 10_000) -> None:
        """Deliver all queued events, including any emitted by handlers (cascades)."""
        iterations = 0
        while self._queue:
            if iterations >= max_iterations:
                raise RuntimeError(
                    f"EventBus.drain() exceeded {max_iterations} iterations "
                    f"(likely cascade loop, {len(self._queue)} events still queued)"
                )
            event = self._queue.popleft()
            handlers = self._handlers.get(type(event), [])
            log.debug(
                "delivering", event_type=type(event).__name__, handlers=len(handlers)
            )
            for handler in handlers:
                handler(event)
            iterations += 1

    def pending(self) -> int:
        """Return the number of events currently waiting to be drained."""
        return len(self._queue)
