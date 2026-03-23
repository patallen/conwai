from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


@dataclass
class TickNumber:
    value: int = 0


@runtime_checkable
class System(Protocol):
    name: str

    async def run(self, world: World) -> None: ...


class Engine:
    def __init__(self, world: World, systems: list[System] | None = None):
        self.world = world
        self._systems: list[System] = []
        for system in systems or []:
            self.add_system(system)

    def add_system(self, system: System) -> None:
        self._systems.append(system)
        log.info(f"[ENGINE] registered system: {system.name}")

    async def tick(self) -> None:
        tick = self.world.get_resource(TickNumber)
        tick.value += 1
        log.info(f"[ENGINE] tick {tick.value}")

        bus = self.world._bus

        if bus:
            from conwai.event_types import TickStarted
            bus.emit(TickStarted(tick=tick.value))
            bus.drain()

        for system in self._systems:
            await system.run(self.world)
            if bus:
                bus.drain()

        if bus:
            from conwai.event_types import TickEnded
            bus.emit(TickEnded(tick=tick.value))
            bus.drain()

        self.world.flush()
        self.world.save_metadata("tick", {"value": tick.value})
