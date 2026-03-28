"""Discrete event scheduler. Heap-based simulated time."""

from __future__ import annotations

import asyncio
import heapq
import itertools
import structlog
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Callable

from conwai.events import EventBus


@dataclass
class TickNumber:
    value: int = 0

log = structlog.get_logger()

TaskFn = Callable[[], Coroutine[Any, Any, Any]]

MAX_CASCADES = 1000


class Scheduler:
    """Discrete event scheduler with simulated time.

    schedule() fires the task immediately and places it on a heap
    at sim_time + cost. run() pops events in time order, waits for
    the result (barrier), drains the EventBus, and continues until
    the heap is empty or a time limit is reached.

    Time jumps from event to event — no stepping through empty slots.
    """

    def __init__(self, bus: EventBus, default_cost: int = 0):
        self.bus = bus
        self.default_cost = default_cost
        self.sim_time: int = 0
        # heap of (resolve_time, tie_breaker, key, task_fn)
        self._heap: list[tuple[int, int, str, TaskFn]] = []
        self._counter = itertools.count()
        self._active: set[str] = set()

    def schedule(self, key: str, task_fn: TaskFn, cost: int | None = None) -> None:
        """Schedule work at sim_time + cost. Task runs when its time comes."""
        if key in self._active:
            return
        cost = cost if cost is not None else self.default_cost
        if cost < 0:
            raise ValueError(f"cost must be >= 0, got {cost}")
        resolve_at = self.sim_time + cost
        heapq.heappush(self._heap, (resolve_at, next(self._counter), key, task_fn))
        self._active.add(key)

    async def run(self, until: int | None = None) -> None:
        """Process events until the heap is empty or sim_time reaches `until`."""
        cascades = 0

        while self._heap:
            resolve_time = self._heap[0][0]
            if until is not None and resolve_time >= until:
                break

            # Collect all events at this time step
            batch: list[tuple[str, TaskFn]] = []
            while self._heap and self._heap[0][0] == resolve_time:
                _, _, key, task_fn = heapq.heappop(self._heap)
                batch.append((key, task_fn))

            self.sim_time = resolve_time

            # Clear keys from _active before running — tasks may re-schedule themselves
            keys = [k for k, _ in batch]
            for key in keys:
                self._active.discard(key)

            # Create and run all tasks at this time step
            tasks = [asyncio.create_task(fn()) for _, fn in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            log.info("scheduler_batch", sim_time=self.sim_time, keys=keys, batch_size=len(keys))

            for key, result in zip(keys, results):
                if isinstance(result, Exception):
                    log.error("scheduler_task_error", key=key, error=str(result), sim_time=self.sim_time)

            self.bus.drain()

            cascades += 1
            if cascades >= MAX_CASCADES:
                log.error("scheduler_cascade_limit", cascades=cascades, max=MAX_CASCADES, sim_time=self.sim_time)
                break

        # Advance sim_time to `until` if specified
        if until is not None:
            self.sim_time = max(self.sim_time, until)

        # Clean up _active
        active_on_heap = {key for _, _, key, _ in self._heap}
        self._active = active_on_heap
