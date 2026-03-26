"""Sub-tick scheduler. Manages a timeline of async work within a tick."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

log = logging.getLogger("conwai")


class Scheduler:
    """Manages async work across sub-ticks within a simulation tick.

    schedule() fires the task immediately and places it on the timeline.
    run_tick() walks through simulated time, gathering results at each
    task's resolve time. If an LLM call hasn't finished when its resolve
    time arrives, the sim blocks until it does.

    Between sub-ticks the EventBus is drained, so event handlers can
    call schedule() to add more work.
    """

    def __init__(self, bus, resolution: int = 1, default_cost: int = 0):
        self.bus = bus
        self.resolution = max(1, resolution)
        self.default_cost = default_cost
        self.current_subtick: int = 0
        # key -> (asyncio.Task, resolve_subtick)
        self._in_flight: dict[str, tuple[asyncio.Task, int]] = {}

    def schedule(self, key: str, task_fn: Callable[[], Awaitable[Any]], cost: int | None = None) -> None:
        """Fire a task immediately and place it on the timeline.

        The task starts running now (real time). Its result is gathered
        at current_subtick + cost (simulated time). If key is already
        in-flight, the call is ignored. If the resolve time is past the
        tick boundary, the call is ignored.
        """
        if key in self._in_flight:
            return
        cost = cost if cost is not None else self.default_cost
        resolve_at = self.current_subtick + cost
        if resolve_at >= self.resolution:
            return
        task = asyncio.create_task(task_fn())
        self._in_flight[key] = (task, resolve_at)

    async def run_tick(self) -> None:
        """Walk through simulated time, gathering results as they come due."""
        self.current_subtick = 0

        for self.current_subtick in range(self.resolution):
            # Collect tasks due at this subtick
            due = {k: t for k, (t, r) in self._in_flight.items() if r <= self.current_subtick}
            if not due:
                continue

            log.info(f"[SCHEDULER] subtick {self.current_subtick}: {len(due)} task(s)")

            # Wait for all due tasks — blocks if LLM calls haven't returned
            results = await asyncio.gather(*due.values(), return_exceptions=True)

            for key, result in zip(due.keys(), results):
                del self._in_flight[key]
                if isinstance(result, Exception):
                    log.error(f"[SCHEDULER] {key} error: {result}", exc_info=result)

            # Drain bus — events from completed tasks get delivered,
            # handlers may call schedule() to add more work
            if self.bus:
                self.bus.drain()

        # Cancel any tasks that didn't resolve within the tick
        for key, (task, _) in self._in_flight.items():
            task.cancel()
            log.warning(f"[SCHEDULER] {key} did not resolve within tick, cancelled")
        self._in_flight.clear()
