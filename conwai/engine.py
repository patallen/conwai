from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

from conwai.actions import ActionFeedback, ActionResult, PendingActions

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.brain import Brain
    from conwai.world import World

log = logging.getLogger("conwai")


@dataclass
class TickNumber:
    value: int = 0


@runtime_checkable
class System(Protocol):
    name: str
    async def run(self, world: World) -> None: ...


class BrainSystem:
    name = "brain"

    def __init__(
        self,
        brains: dict[str, Brain],
        perception: Callable,
    ):
        self.brains = brains
        self.perception = perception

    async def run(self, world: World) -> None:
        entities = set(world.entities())
        handles = [h for h in self.brains if h in entities]
        tasks = [
            asyncio.create_task(self._tick_agent(handle, world))
            for handle in handles
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for handle, result in zip(handles, results):
            if isinstance(result, Exception):
                log.error(f"[{handle}] brain error: {result}")

    async def _tick_agent(self, handle: str, world: World) -> None:
        start = time.monotonic()
        brain = self.brains[handle]
        tick = world.get_resource(TickNumber)

        percept = self.perception(handle, world)
        decisions = await brain.think(percept)

        world.set(handle, PendingActions(entries=decisions))

        world.save_raw(handle, "brain_state", brain.save_state())

        log.info(f"[{handle}] tick {tick.value} took {time.monotonic() - start:.1f}s")

    def load_brain_states(self, world: World) -> None:
        """Load persisted brain state for all agents."""
        for handle, brain in self.brains.items():
            data = world.load_raw(handle, "brain_state")
            if data:
                brain.load_state(data)
                log.info(f"[{handle}] loaded brain state")


class ActionSystem:
    name = "actions"

    def __init__(self, actions: ActionRegistry):
        self.actions = actions

    async def run(self, world: World) -> None:
        pending_pairs = list(world.query(PendingActions))
        self.actions.begin_tick(world, [eid for eid, _ in pending_pairs])

        for entity_id, pending in pending_pairs:
            feedback_entries = []
            for decision in pending.entries:
                result = self.actions.execute(
                    entity_id, decision.action, decision.args, world
                )
                feedback_entries.append(ActionResult(
                    action=decision.action,
                    args=decision.args,
                    result=result,
                ))
            world.set(entity_id, ActionFeedback(entries=feedback_entries))
            pending.entries.clear()


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
        for system in self._systems:
            await system.run(self.world)

        self.world.flush()
        self.world.save_metadata("tick", {"value": tick.value})
