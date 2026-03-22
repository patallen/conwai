from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from conwai.cognition.percept import ActionFeedback
from conwai.cognition.types import BrainState
from conwai.processes.types import WorkingMemory

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.cognition.blackboard import BlackboardBrain
    from conwai.cognition.perception import PerceptionBuilder
    from conwai.typemap import Percept
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
        actions: ActionRegistry,
        brains: dict[str, BlackboardBrain],
        perception: PerceptionBuilder,
    ):
        self.actions = actions
        self.brains = brains
        self.perception = perception
        self._action_feedback: dict[str, list[ActionFeedback]] = {}

    async def run(self, world: World) -> None:
        alive = world.entities()
        alive_set = set(alive)
        self._action_feedback = {
            h: fb for h, fb in self._action_feedback.items() if h in alive_set
        }
        self.actions.begin_tick(world, [h for h in alive if h in self.brains])
        tasks = [
            asyncio.create_task(self._tick_agent(handle, world))
            for handle in alive
            if handle in self.brains
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for handle, result in zip(
            [h for h in alive if h in self.brains], results
        ):
            if isinstance(result, Exception):
                log.error(f"[{handle}] brain error: {result}")

    async def _tick_agent(self, handle: str, world: World) -> None:
        start = time.monotonic()
        brain = self.brains[handle]
        feedback = self._action_feedback.pop(handle, [])

        tick = world.get_resource(TickNumber)
        percept: Percept = self.perception.build(handle, world, action_feedback=feedback)

        if not brain.bb.has(WorkingMemory):
            if world.has(handle, BrainState):
                world.get(handle, BrainState).load_into(brain.bb)

        decisions = await brain.think(percept)
        world.set(handle, BrainState.save_from(brain.bb))

        tick_feedback: list[ActionFeedback] = []
        for decision in decisions:
            result = self.actions.execute(handle, decision.action, decision.args, world)
            tick_feedback.append(ActionFeedback(
                action=decision.action,
                args=decision.args,
                result=result,
            ))

        if tick_feedback:
            self._action_feedback[handle] = tick_feedback

        log.info(f"[{handle}] tick {tick.value} took {time.monotonic() - start:.1f}s")


class Engine:
    def __init__(self, world: World):
        self.world = world
        self._systems: list[System] = []

    def add_system(self, system: System) -> None:
        self._systems.append(system)
        log.info(f"[ENGINE] registered system: {system.name}")

    async def tick(self) -> None:
        tick = self.world.get_resource(TickNumber)
        tick.value += 1
        log.info(f"[ENGINE] tick {tick.value}")
        for system in self._systems:
            await system.run(self.world)
