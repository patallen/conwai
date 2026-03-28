"""Framework-level simulation loop.

Eliminates boilerplate from runners by encapsulating the standard tick cycle:
pre-systems -> agent scheduling -> post-systems -> persist.
"""

from __future__ import annotations

import structlog
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from conwai.events import EventBus
from conwai.scheduler import Scheduler
from conwai.world import World

log = structlog.get_logger()

AgentFn = Callable[[str], Awaitable[None]]


@runtime_checkable
class System(Protocol):
    async def run(self, world: World) -> None: ...


class TickLoop:
    """Runs one complete simulation tick.

    Usage::

        loop = TickLoop(scheduler=scheduler, event_bus=bus, world=world)
        loop.add_pre_system(decay)
        loop.add_pre_system(tax)
        loop.add_post_system(consumption)
        loop.on_persist = lambda: (world.flush(), save_brains())

        await loop.tick(handles, on_tick)
    """

    def __init__(
        self,
        scheduler: Scheduler,
        event_bus: EventBus,
        world: World,
    ) -> None:
        self._scheduler = scheduler
        self._bus = event_bus
        self._world = world
        self._pre_systems: list[System] = []
        self._post_systems: list[System] = []
        self.on_persist: Callable[[], None] | None = None

    def add_pre_system(self, system: System) -> None:
        self._pre_systems.append(system)

    def add_post_system(self, system: System) -> None:
        self._post_systems.append(system)

    async def tick(
        self,
        handles: list[str],
        agent_fn: AgentFn,
        *,
        cost: int = 0,
    ) -> None:
        """Run one complete tick: pre-systems, agents, post-systems, persist."""
        # Pre-agent systems (sequential, drain after each)
        for system in self._pre_systems:
            await system.run(self._world)
            self._bus.drain()

        # Schedule all agents (concurrent via scheduler)
        for handle in handles:
            async def _run(h: str = handle) -> None:
                await agent_fn(h)
            self._scheduler.schedule(handle, _run, cost=cost)
        await self._scheduler.run()

        # Post-agent systems (sequential, drain after each)
        for system in self._post_systems:
            await system.run(self._world)
            self._bus.drain()

        # Persist
        if self.on_persist is not None:
            self.on_persist()
