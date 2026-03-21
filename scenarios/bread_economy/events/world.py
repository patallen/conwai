from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scenarios.bread_economy.events.ciphers import CipherSystem
from scenarios.bread_economy.events.elections import ElectionSystem
from scenarios.bread_economy.events.questions import QuestionSystem

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.cognition.perception import PerceptionBuilder
    from conwai.engine import TickContext
    from conwai.messages import MessageBus
    from conwai.pool import AgentPool
    from conwai.storage import Storage
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class WorldEvents:
    """Phase that coordinates question, election, and cipher sub-systems."""

    name = "world"

    def __init__(
        self,
        board: BulletinBoard,
        bus: MessageBus,
        pool: AgentPool,
        store: ComponentStore,
        perception: PerceptionBuilder,
        question_interval: int = 60,
        cipher_interval: int = 40,
        election_interval: int = 50,
        election_duration: int = 15,
        storage: Storage | None = None,
    ):
        self._tick = 0
        self._storage = storage
        self.questions = QuestionSystem(board, interval=question_interval)
        self.elections = ElectionSystem(
            board, pool, store, perception,
            interval=election_interval,
            duration=election_duration,
        )
        self.ciphers = CipherSystem(
            board, bus, pool, store, perception,
            interval=cipher_interval,
        )
        self._load_state()

    async def run(self, ctx: TickContext) -> None:
        self._tick = ctx.tick
        self.questions.tick(ctx.tick)
        self.ciphers.tick(ctx.tick)
        self.elections.tick(ctx.tick)
        self._save_state()

    # -- Delegation methods for action handlers --

    def submit_code(self, agent: Agent, guess: str) -> str:
        return self.ciphers.submit_code(agent, guess)

    def cast_vote(self, agent: Agent, candidate: str) -> str:
        return self.elections.cast_vote(agent, candidate, self._tick)

    def get_cipher_status(self) -> dict | None:
        return self.ciphers.get_status()

    # -- State persistence --

    def _save_state(self) -> None:
        state = {
            **self.questions.save_state(),
            **self.elections.save_state(),
            **self.ciphers.save_state(),
        }
        if self._storage:
            self._storage.save_component("WORLD", "world_events", state)

    def _load_state(self) -> None:
        if not self._storage:
            return
        state = self._storage.load_component("WORLD", "world_events")
        if not state:
            return
        self.questions.load_state(state)
        self.elections.load_state(state)
        self.ciphers.load_state(state)
