from __future__ import annotations

import random
from typing import TYPE_CHECKING

import structlog

from conwai.comm import BulletinBoard

if TYPE_CHECKING:
    from conwai.world import World

log = structlog.get_logger()

QUESTIONS = [
    "Who do you trust the most here, and why?",
    "What is the biggest threat to this community?",
    "If you could change one thing about this place, what would it be?",
    "What do you know that nobody else knows?",
    "Who is the most valuable member of this community?",
    "What would you do if you had unlimited coins?",
    "Who here would you never DM, and why?",
    "What have you learned since you arrived?",
    "Is anyone here pretending to be something they are not?",
    "What is the point of this place?",
]


class QuestionSystem:
    """Posts periodic discussion questions to the bulletin board."""

    def __init__(self, world: World, interval: int = 60):
        self._world = world
        self.interval = interval
        self._used: set[int] = set()

    def tick(self, tick: int) -> None:
        if tick == 0 or tick % self.interval != 0:
            return
        self._ask_question()

    def _ask_question(self) -> None:
        available = [i for i in range(len(QUESTIONS)) if i not in self._used]
        if not available:
            self._used.clear()
            available = list(range(len(QUESTIONS)))

        idx = random.choice(available)
        self._used.add(idx)

        question = QUESTIONS[idx]
        board = self._world.get_resource(BulletinBoard)
        board.post("WORLD", f"QUESTION FOR ALL: {question}")
        log.info("question_posted", question=question)

    # -- State persistence helpers --

    def save_state(self) -> dict:
        return {"used_questions": list(self._used)}

    def load_state(self, state: dict) -> None:
        self._used = set(state.get("used_questions", []))
