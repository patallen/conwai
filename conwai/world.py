from __future__ import annotations

import logging
import random
import string
from time import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.perception import Perception
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")

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


class WorldEvents:
    name = "world"

    def __init__(
        self,
        board: BulletinBoard,
        bus: MessageBus,
        pool: AgentPool,
        store: ComponentStore,
        perception: Perception,
        question_interval: int = 60,
        code_interval: int = 30,
    ):
        self._board = board
        self._bus = bus
        self._pool = pool
        self._store = store
        self._perception = perception
        self.question_interval = question_interval
        self.code_interval = code_interval
        self._tick = 0
        self._used_questions: set[int] = set()
        self._active_code: str | None = None
        self._code_fragments: dict[
            str, tuple[int, str]
        ] = {}  # handle -> (position, char)
        self._code_started_tick: int = 0
        self._code_started_time: float = 0

    def tick(self, agents: list[Agent], store: ComponentStore, perception: Perception, **kwargs) -> None:
        tick = kwargs.get("tick", 0)
        self._tick = tick

        if self._active_code:
            self._check_code_expiry()

        if self._tick % self.question_interval == 0 and self._tick > 0:
            self._ask_question()

        if not self._active_code:
            first = self._tick == 10
            recurring = self._tick > 10 and self._tick % self.code_interval == 0
            if first or recurring:
                self._start_code_challenge()

    def _ask_question(self):
        available = [i for i in range(len(QUESTIONS)) if i not in self._used_questions]
        if not available:
            self._used_questions.clear()
            available = list(range(len(QUESTIONS)))

        idx = random.choice(available)
        self._used_questions.add(idx)

        question = QUESTIONS[idx]
        self._board.post("WORLD", f"QUESTION FOR ALL: {question}")
        log.info(f"[WORLD] question: {question}")

    def _start_code_challenge(self):
        handles = self._pool.handles()
        if len(handles) < 4:
            return

        chars = string.ascii_uppercase + string.digits
        code = "".join(random.choice(chars) for _ in range(4))
        self._active_code = code
        self._code_started_tick = self._tick
        self._code_started_time = time()
        self._code_fragments.clear()

        chosen = random.sample(handles, 4)
        for i, handle in enumerate(chosen):
            self._code_fragments[handle] = (i + 1, code[i])
            mask = ["_"] * 4
            mask[i] = code[i]
            if self._store.has(handle, "memory"):
                mem = self._store.get(handle, "memory")
                mem["code_fragment"] = (
                    f"'{code[i]}' at position {i + 1} (pattern: {''.join(mask)})"
                )
                self._store.set(handle, "memory", mem)
            self._bus.send(
                "WORLD",
                handle,
                f"CODE CHALLENGE: You hold character '{code[i]}' at position {i + 1}. The code is 4 random characters (A-Z, 0-9) and looks like: {''.join(mask)}. Collect all 4 characters from the other holders before guessing.",
            )
            log.info(
                f"[WORLD] code fragment -> [{handle}]: pos {i + 1} = '{code[i]}'"
            )

        self._board.post(
            "WORLD",
            f"CODE CHALLENGE: A 4-char code (A-Z, 0-9) has been split among 4 holders: {', '.join(chosen)}. Only holders have fragments. Guessing without all 4 characters is risky. Wrong = -50 coins.",
        )
        log.info(f"[WORLD] code challenge started: {code}")

    def _clear_fragments(self):
        for handle in self._code_fragments:
            if self._store.has(handle, "memory"):
                mem = self._store.get(handle, "memory")
                mem["code_fragment"] = None
                self._store.set(handle, "memory", mem)
        self._code_fragments.clear()

    def _check_code_expiry(self):
        if self._tick - self._code_started_tick > 80:
            self._board.post(
                "WORLD",
                "CODE CHALLENGE EXPIRED. No one claimed it.",
            )
            log.info(f"[WORLD] code challenge expired: {self._active_code}")
            self._active_code = None
            self._clear_fragments()

    def submit_code(self, agent: Agent, guess: str) -> str:
        if not self._active_code:
            return "No active code challenge."

        guess = guess.strip().upper()
        if guess == self._active_code:
            solver_reward = 200
            holder_penalty = 25

            if self._store.has(agent.handle, "economy"):
                eco = self._store.get(agent.handle, "economy")
                eco["coins"] += solver_reward
                self._store.set(agent.handle, "economy", eco)
                self._perception.notify(agent.handle, f"+{solver_reward} coins (solved code challenge)")

            for handle in self._code_fragments:
                if handle != agent.handle and self._store.has(handle, "economy"):
                    other_eco = self._store.get(handle, "economy")
                    other_eco["coins"] = max(0, other_eco["coins"] - holder_penalty)
                    self._store.set(handle, "economy", other_eco)
                    self._perception.notify(handle, f"-{holder_penalty} coins (code solved by {agent.handle})")

            self._board.post(
                "WORLD",
                f"CODE CHALLENGE SOLVED by {agent.handle}! {agent.handle} earned {solver_reward} coins. Fragment holders lost {holder_penalty} each.",
            )
            log.info(f"[WORLD] CODE SOLVED by {agent.handle}: {self._active_code}")
            self._active_code = None
            self._clear_fragments()
            return f"CORRECT! You solved the code and earned {solver_reward} coins."
        else:
            correct = sum(a == b for a, b in zip(guess, self._active_code))
            penalty = 50
            if self._store.has(agent.handle, "economy"):
                eco = self._store.get(agent.handle, "economy")
                eco["coins"] = max(0, eco["coins"] - penalty)
                self._store.set(agent.handle, "economy", eco)
            log.info(
                f"[WORLD] WRONG GUESS by {agent.handle}: {guess} ({correct}/4 correct)"
            )
            return f"WRONG. {correct} of 4 characters are in the right position. You lost {penalty} coins."
