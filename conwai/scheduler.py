"""Sub-tick scheduler. Manages a timeline of async work within a tick."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

log = logging.getLogger("conwai")


class Scheduler:
    """Manages async work across sub-ticks within a simulation tick.

    Call schedule() to put work on the timeline. Call run_tick() to
    process all sub-ticks. Between sub-ticks, the EventBus is drained,
    so event handlers can call schedule() to add more work.
    """

    def __init__(self, bus, resolution: int = 1, default_cost: int = 0):
        self.bus = bus
        self.resolution = max(1, resolution)
        self.default_cost = default_cost
        self.current_subtick: int = 0
        self._timeline: dict[int, list[tuple[str, Callable[[], Awaitable[Any]]]]] = defaultdict(list)
        self._active: set[str] = set()

    def schedule(self, key: str, task_fn: Callable[[], Awaitable[Any]], cost: int | None = None) -> None:
        """Add work to the timeline.

        If key is already scheduled or in-flight, the call is ignored.
        If the work would resolve past the end of the tick, it is dropped.
        """
        if key in self._active:
            return
        cost = cost if cost is not None else self.default_cost
        resolve_at = self.current_subtick + cost
        if resolve_at >= self.resolution:
            return
        self._timeline[resolve_at].append((key, task_fn))
        self._active.add(key)

    async def run_tick(self) -> None:
        """Process all sub-ticks for one tick."""
        self.current_subtick = 0

        for self.current_subtick in range(self.resolution):
            work = self._timeline.pop(self.current_subtick, [])
            if not work:
                continue

            keys = [k for k, _ in work]
            tasks = [fn() for _, fn in work]

            log.info(f"[SCHEDULER] subtick {self.current_subtick}: {len(keys)} task(s)")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for key, result in zip(keys, results):
                self._active.discard(key)
                if isinstance(result, Exception):
                    log.error(f"[SCHEDULER] {key} error: {result}", exc_info=result)

            if self.bus:
                self.bus.drain()

        # Clean up for next tick
        self._timeline.clear()
        self._active.clear()
