"""Sub-tick scheduler. Manages a timeline of async work in simulated time."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Coroutine
from typing import Any, Callable

from conwai.event_bus import EventBus

log = logging.getLogger("conwai")

TaskFn = Callable[[], Coroutine[Any, Any, Any]]

MAX_CASCADES_PER_STEP = 100


class Scheduler:
    """Manages async work on an absolute simulated-time timeline.

    schedule() places work at sim_time + cost. run_tick() advances
    sim_time by `resolution` steps, running tasks as they come due.
    Work scheduled past the current tick resolves in a future tick.
    Between sub-ticks the EventBus is drained, so event handlers
    can call schedule() to add more work.
    """

    def __init__(self, bus: EventBus, resolution: int = 1, default_cost: int = 0):
        self.bus = bus
        self.resolution = max(1, resolution)
        self.default_cost = default_cost
        self.sim_time: int = 0
        # absolute sim_time -> [(key, task_fn)]
        self._timeline: dict[int, list[tuple[str, TaskFn]]] = defaultdict(list)
        self._active: set[str] = set()

    def schedule(self, key: str, task_fn: TaskFn, cost: int | None = None) -> None:
        """Place work on the timeline at sim_time + cost."""
        if key in self._active:
            return
        cost = cost if cost is not None else self.default_cost
        if cost < 0:
            raise ValueError(f"cost must be >= 0, got {cost}")
        resolve_at = self.sim_time + cost
        self._timeline[resolve_at].append((key, task_fn))
        self._active.add(key)

    async def run_tick(self) -> None:
        """Advance sim_time by resolution steps, running due tasks."""
        tick_end = self.sim_time + self.resolution

        while self.sim_time < tick_end:
            work = self._timeline.pop(self.sim_time, [])
            cascades = 0
            while work:
                if cascades >= MAX_CASCADES_PER_STEP:
                    log.error(
                        f"[SCHEDULER] t={self.sim_time}: hit cascade limit "
                        f"({MAX_CASCADES_PER_STEP}), dropping remaining work"
                    )
                    for key, _ in work:
                        self._active.discard(key)
                    break

                keys = [k for k, _ in work]
                tasks = [asyncio.create_task(fn()) for _, fn in work]

                log.info(f"[SCHEDULER] t={self.sim_time}: {len(keys)} task(s)")

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for key, result in zip(keys, results):
                    self._active.discard(key)
                    if isinstance(result, Exception):
                        log.error(f"[SCHEDULER] {key} error: {result}", exc_info=result)

                self.bus.drain()

                # Drain may have scheduled new work at this same sim_time
                work = self._timeline.pop(self.sim_time, [])
                cascades += 1

            self.sim_time += 1

        # Clean up _active for any work still on the timeline
        # (scheduled past tick_end — will resolve in a future tick,
        # but keys should be free to re-schedule if needed)
        scheduled_keys = {k for entries in self._timeline.values() for k, _ in entries}
        self._active = scheduled_keys
