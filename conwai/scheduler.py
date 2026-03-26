"""Sub-tick scheduler. Manages a timeline of async work within a tick."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Coroutine
from typing import Any, Callable

log = logging.getLogger("conwai")

TaskFn = Callable[[], Coroutine[Any, Any, Any]]


class Scheduler:
    """Manages async work across sub-ticks within a simulation tick.

    schedule() places work on the timeline at current_subtick + cost.
    run_tick() walks through simulated time. At each sub-tick, due tasks
    are created and awaited. Between sub-ticks the EventBus is drained,
    so event handlers can call schedule() to add more work.

    Work that doesn't resolve within the tick carries over to the next.
    """

    def __init__(self, bus, resolution: int = 1, default_cost: int = 0):
        self.bus = bus
        self.resolution = max(1, resolution)
        self.default_cost = default_cost
        self.current_subtick: int = 0
        # resolve_subtick -> [(key, task_fn)]
        self._timeline: dict[int, list[tuple[str, TaskFn]]] = defaultdict(list)
        self._active: set[str] = set()

    def schedule(self, key: str, task_fn: TaskFn, cost: int | None = None) -> None:
        """Place work on the timeline at current_subtick + cost.

        If key is already scheduled or running, the call is ignored.
        """
        if key in self._active:
            return
        cost = cost if cost is not None else self.default_cost
        resolve_at = self.current_subtick + cost
        self._timeline[resolve_at].append((key, task_fn))
        self._active.add(key)

    async def run_tick(self) -> None:
        """Walk through simulated time, running tasks as they come due."""
        self.current_subtick = 0

        for self.current_subtick in range(self.resolution):
            work = self._timeline.pop(self.current_subtick, [])
            if not work:
                continue

            keys = [k for k, _ in work]
            tasks = [asyncio.create_task(fn()) for _, fn in work]

            log.info(f"[SCHEDULER] subtick {self.current_subtick}: {len(keys)} task(s)")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for key, result in zip(keys, results):
                self._active.discard(key)
                if isinstance(result, Exception):
                    log.error(f"[SCHEDULER] {key} error: {result}", exc_info=result)

            if self.bus:
                self.bus.drain()

        # Carry over unresolved work — shift resolve times into next tick
        carried: dict[int, list[tuple[str, TaskFn]]] = defaultdict(list)
        for resolve_at, entries in self._timeline.items():
            new_resolve = max(0, resolve_at - self.resolution)
            carried[new_resolve].extend(entries)
            for key, _ in entries:
                log.info(f"[SCHEDULER] {key} carrying over (resolves subtick {new_resolve})")
        self._timeline = carried
