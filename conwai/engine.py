from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.brain import Brain
    from conwai.bulletin_board import BulletinBoard
    from conwai.events import EventLog
    from conwai.messages import MessageBus
    from conwai.perception import Perception
    from conwai.pool import AgentPool
    from conwai.repository import AgentRepository
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


@dataclass
class TickContext:
    tick: int
    pool: AgentPool
    store: ComponentStore
    perception: Perception
    tick_state: dict = field(default_factory=dict)
    board: BulletinBoard | None = None
    bus: MessageBus | None = None
    events: EventLog | None = None


@runtime_checkable
class Phase(Protocol):
    name: str

    async def run(self, ctx: TickContext) -> None: ...


class BrainPhase:
    name = "brain"

    def __init__(
        self,
        actions: ActionRegistry,
        brains: dict[str, Brain],
        perception: Perception,
    ):
        self.actions = actions
        self.brains = brains
        self.perception = perception

    async def run(self, ctx: TickContext) -> None:
        agents = ctx.pool.alive()
        self.actions.begin_tick(ctx, [a.handle for a in agents])
        tasks = [
            asyncio.create_task(self._tick_agent(a, ctx))
            for a in agents
            if a.handle in self.brains
        ]
        await asyncio.gather(*tasks)

    async def _tick_agent(self, agent, ctx: TickContext) -> None:
        start = time.monotonic()
        brain = self.brains[agent.handle]
        identity = self.perception.build_identity(agent, ctx.store)
        text = self.perception.build(agent, ctx.store, ctx.board, ctx.bus, ctx.tick)
        decisions = await brain.decide(agent, text, identity=identity, tick=ctx.tick)
        for decision in decisions:
            result = self.actions.execute(agent, decision.action, decision.args, ctx)
            await brain.observe(decision, result)
        log.info(f"[{agent.handle}] tick {ctx.tick} took {time.monotonic() - start:.1f}s")


class Engine:
    def __init__(
        self,
        pool: AgentPool,
        store: ComponentStore,
        perception: Perception,
        repo: AgentRepository,
        brains: dict[str, Brain],
        board: BulletinBoard | None = None,
        bus: MessageBus | None = None,
        events: EventLog | None = None,
    ):
        self.pool = pool
        self.store = store
        self.perception = perception
        self.board = board
        self.bus = bus
        self.events = events
        self.repo = repo
        self.brains = brains
        self._phases: list[Phase] = []

    def add_phase(self, phase: Phase) -> None:
        self._phases.append(phase)
        log.info(f"[ENGINE] registered phase: {phase.name}")

    async def tick(self, tick: int) -> None:
        ctx = TickContext(
            tick=tick,
            pool=self.pool,
            store=self.store,
            perception=self.perception,
            board=self.board,
            bus=self.bus,
            events=self.events,
        )

        for phase in self._phases:
            await phase.run(ctx)

        # Persist
        self.pool.save_all()
        self._save_brain_states()

    def _save_brain_states(self):
        for handle, brain in self.brains.items():
            if hasattr(brain, 'get_state'):
                self.repo.save_brain_state(handle, brain.get_state())
