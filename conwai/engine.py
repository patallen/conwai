from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.brain import Brain
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.perception import Perception
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class Engine:
    def __init__(
        self,
        pool: AgentPool,
        store: ComponentStore,
        perception: Perception,
        actions: ActionRegistry,
        brains: dict[str, Brain],
        board: BulletinBoard,
        bus: MessageBus,
    ):
        self.pool = pool
        self.store = store
        self.perception = perception
        self.actions = actions
        self.brains = brains
        self.board = board
        self.bus = bus
        self._pre_brain_systems: list = []
        self._post_brain_systems: list = []

    def register_pre_brain(self, system) -> None:
        self._pre_brain_systems.append(system)
        log.info(f"[ENGINE] registered pre-brain system: {system.name}")

    def register_post_brain(self, system) -> None:
        self._post_brain_systems.append(system)
        log.info(f"[ENGINE] registered post-brain system: {system.name}")

    async def tick(self, tick: int) -> None:
        agents = self.pool.alive()

        # Reset tick state
        self.actions.tick_state = {a.handle: {} for a in agents}
        self.actions.current_tick = tick

        # Pre-brain systems
        for system in self._pre_brain_systems:
            system.tick(agents, self.store, self.perception, tick=tick)

        # Brain loop — parallel per agent
        agents = self.pool.alive()  # refresh after death system
        tasks = []
        for agent in agents:
            brain = self.brains.get(agent.handle)
            if brain:
                tasks.append(asyncio.create_task(
                    self._tick_agent(agent, brain, tick)
                ))
        await asyncio.gather(*tasks)

        # Post-brain systems
        agents = self.pool.alive()
        for system in self._post_brain_systems:
            system.tick(agents, self.store, self.perception, tick=tick)

        # Persist
        self.pool.save_all()
        self._save_brain_states()

    async def _tick_agent(self, agent, brain, tick):
        start = time.monotonic()

        identity = self.perception.build_identity(agent, self.store)
        text = self.perception.build(agent, self.store, self.board, self.bus, tick)

        decisions = await brain.decide(agent, text, identity=identity, tick=tick)

        for decision in decisions:
            result = self.actions.execute(agent, decision.action, decision.args)
            brain.observe(decision, result)

        log.info(f"[{agent.handle}] tick {tick} took {time.monotonic() - start:.1f}s")

    def _save_brain_states(self):
        for handle, brain in self.brains.items():
            if hasattr(brain, 'get_state'):
                self.pool.save_brain_state(handle, brain.get_state())
