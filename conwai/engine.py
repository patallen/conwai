from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from conwai.cognition.percept import ActionFeedback
from conwai.cognition.perception import PerceptionBuilder

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.cognition import Brain
    from conwai.events import EventLog
    from conwai.messages import MessageBus
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


@dataclass
class TickContext:
    tick: int
    pool: AgentPool
    store: ComponentStore
    perception: PerceptionBuilder
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
        perception: PerceptionBuilder,
    ):
        self.actions = actions
        self.brains = brains
        self.perception = perception
        self._action_feedback: dict[str, list[ActionFeedback]] = {}

    async def run(self, ctx: TickContext) -> None:
        agents = ctx.pool.alive()
        alive_handles = {a.handle for a in agents}
        self._action_feedback = {h: fb for h, fb in self._action_feedback.items() if h in alive_handles}
        self.actions.begin_tick(ctx, [a.handle for a in agents])
        tasks = [
            asyncio.create_task(self._tick_agent(a, ctx))
            for a in agents
            if a.handle in self.brains
        ]
        await asyncio.gather(*tasks)

    async def _tick_agent(self, agent: Agent, ctx: TickContext) -> None:
        start = time.monotonic()
        brain = self.brains[agent.handle]
        feedback = self._action_feedback.pop(agent.handle, [])

        percept = self.perception.build(
            agent, ctx.store, ctx.board, ctx.bus, ctx.tick,
            action_feedback=feedback,
        )

        decisions = await brain.think(percept)

        tick_feedback: list[ActionFeedback] = []
        for decision in decisions:
            result = self.actions.execute(agent, decision.action, decision.args, ctx)
            tick_feedback.append(ActionFeedback(
                action=decision.action,
                args=decision.args,
                result=result,
            ))

        if tick_feedback:
            self._action_feedback[agent.handle] = tick_feedback

        log.info(f"[{agent.handle}] tick {ctx.tick} took {time.monotonic() - start:.1f}s")


class Engine:
    def __init__(
        self,
        pool: AgentPool,
        store: ComponentStore,
        perception: PerceptionBuilder,
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
