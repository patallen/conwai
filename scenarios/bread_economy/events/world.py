from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from conwai.scheduler import TickNumber
from scenarios.bread_economy.events.ciphers import CipherSystem
from scenarios.bread_economy.events.elections import ElectionSystem
from scenarios.bread_economy.events.questions import QuestionSystem

if TYPE_CHECKING:
    from conwai.storage import Storage
    from conwai.world import World

log = structlog.get_logger()


class WorldEvents:
    """Phase that coordinates question, election, and cipher sub-systems."""

    name = "world"

    def __init__(
        self,
        world: World,
        question_interval: int = 60,
        cipher_interval: int = 40,
        election_interval: int = 50,
        election_duration: int = 15,
        storage: Storage | None = None,
    ):
        self._world = world
        self._tick = 0
        self._storage = storage
        self.questions = QuestionSystem(world, interval=question_interval)
        self.elections = ElectionSystem(
            world,
            interval=election_interval,
            duration=election_duration,
        )
        self.ciphers = CipherSystem(
            world,
            interval=cipher_interval,
        )
        self._load_state()

    async def run(self, world: World) -> None:
        self._tick = world.get_resource(TickNumber).value
        self.questions.tick(self._tick)
        self.ciphers.tick(self._tick)
        self.elections.tick(self._tick)
        self._save_state()

    # -- Delegation methods for action handlers --

    def submit_code(self, entity_id: str, guess: str) -> str:
        return self.ciphers.submit_code(entity_id, guess)

    def cast_vote(self, entity_id: str, candidate: str) -> str:
        return self.elections.cast_vote(entity_id, candidate)

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
            self._storage.save_component("_meta", "world_events", state)

    def _load_state(self) -> None:
        if not self._storage:
            return
        state = self._storage.load_component("_meta", "world_events")
        if not state:
            return
        self.questions.load_state(state)
        self.elections.load_state(state)
        self.ciphers.load_state(state)
