from __future__ import annotations

import json
import logging
import random
import string
from pathlib import Path
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

CIPHER_PHRASES = [
    "TRUST NO ONE",
    "WATER IS POWER",
    "BREAD FOR SECRETS",
    "WHO CONTROLS FLOUR",
    "ALLIANCES BREAK",
    "TRADE OR STARVE",
    "SECRETS HAVE VALUE",
    "NAMES ARE MASKS",
    "DEBT IS LEVERAGE",
    "SILENCE IS GOLDEN",
    "WATCH THE BAKER",
    "HOARD AND DENY",
    "SHARE TO SURVIVE",
    "LIES COST COINS",
    "KNOWLEDGE IS COIN",
]


def _make_cipher_key() -> dict[str, str]:
    """Generate a random substitution cipher key (letter -> letter)."""
    letters = list(string.ascii_uppercase)
    shuffled = letters[:]
    random.shuffle(shuffled)
    return dict(zip(letters, shuffled))


def _encrypt(plaintext: str, key: dict[str, str]) -> str:
    return "".join(key.get(c, c) for c in plaintext.upper())


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
        cipher_interval: int = 40,
    ):
        self._board = board
        self._bus = bus
        self._pool = pool
        self._store = store
        self._perception = perception
        self.question_interval = question_interval
        self.cipher_interval = cipher_interval
        self._tick = 0
        self._used_questions: set[int] = set()
        self._used_phrases: set[int] = set()

        # Active cipher state
        self._plaintext: str | None = None
        self._ciphertext: str | None = None
        self._cipher_key: dict[str, str] = {}
        self._cipher_started_tick: int = 0
        self._clue_holders: dict[str, str] = {}  # handle -> clue description
        self._solver_reward: int = 200
        self._wrong_penalty: int = 50

    def get_cipher_status(self) -> dict | None:
        if not self._plaintext:
            return None
        return {
            "ciphertext": self._ciphertext,
            "started_tick": self._cipher_started_tick,
            "expires_tick": self._cipher_started_tick + 80,
            "clue_holders": list(self._clue_holders.keys()),
            "clues": {handle: clue for handle, clue in self._clue_holders.items()},
            "reward": self._solver_reward,
            "penalty": self._wrong_penalty,
        }

    def _save_cipher_status(self):
        status = self.get_cipher_status()
        p = Path("data/cipher.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(status))

    def tick(self, agents: list[Agent], store: ComponentStore, perception: Perception, **kwargs) -> None:
        tick = kwargs.get("tick", 0)
        self._tick = tick

        if self._plaintext:
            self._check_cipher_expiry()

        if self._tick % self.question_interval == 0 and self._tick > 0:
            self._ask_question()

        if not self._plaintext:
            first = self._tick == 10
            recurring = self._tick > 10 and self._tick % self.cipher_interval == 0
            if first or recurring:
                self._start_cipher()

        self._save_cipher_status()

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

    def _start_cipher(self):
        handles = self._pool.handles()
        if len(handles) < 3:
            return

        # Pick a phrase
        available = [i for i in range(len(CIPHER_PHRASES)) if i not in self._used_phrases]
        if not available:
            self._used_phrases.clear()
            available = list(range(len(CIPHER_PHRASES)))
        idx = random.choice(available)
        self._used_phrases.add(idx)

        self._plaintext = CIPHER_PHRASES[idx]
        self._cipher_key = _make_cipher_key()
        self._ciphertext = _encrypt(self._plaintext, self._cipher_key)
        self._cipher_started_tick = self._tick
        self._clue_holders.clear()

        # Distribute clues to ~half the population
        num_clues = min(len(handles), max(3, len(handles) // 2))
        chosen = random.sample(handles, num_clues)
        log.info(f"[WORLD] cipher: {len(handles)} alive, distributing {num_clues} clues to {chosen}")

        # Build the set of unique letters in the plaintext
        unique_letters = list(set(c for c in self._plaintext if c.isalpha()))
        random.shuffle(unique_letters)

        # Each chosen agent gets 1-2 letter mappings from the cipher key
        for i, handle in enumerate(chosen):
            # Give each agent a mapping
            letter = unique_letters[i % len(unique_letters)]
            cipher_letter = self._cipher_key[letter]
            clue = f"In the cipher, '{cipher_letter}' decodes to '{letter}'"
            self._clue_holders[handle] = clue

            # Store clue in agent's memory component
            if self._store.has(handle, "memory"):
                mem = self._store.get(handle, "memory")
                mem["code_fragment"] = f"CIPHER CLUE: {clue}"
                self._store.set(handle, "memory", mem)

            self._bus.send(
                "WORLD",
                handle,
                f"CIPHER CHALLENGE: You have a clue. {clue}. Use this to help decode the ciphertext on the board. First to submit the correct plaintext wins {self._solver_reward} coins.",
            )
            log.info(f"[WORLD] cipher clue -> [{handle}]: {clue}")

        self._board.post(
            "WORLD",
            f"CIPHER CHALLENGE: Decode this message: '{self._ciphertext}'. "
            f"Clues have been sent to {len(chosen)} agents. "
            f"First correct answer wins {self._solver_reward} coins. Wrong guess costs {self._wrong_penalty}.",
        )
        log.info(f"[WORLD] cipher started: '{self._plaintext}' -> '{self._ciphertext}'")

    def _clear_cipher(self):
        for handle in self._clue_holders:
            if self._store.has(handle, "memory"):
                mem = self._store.get(handle, "memory")
                mem["code_fragment"] = None
                self._store.set(handle, "memory", mem)
        self._clue_holders.clear()
        self._plaintext = None
        self._ciphertext = None
        self._cipher_key.clear()

    def _check_cipher_expiry(self):
        if self._tick - self._cipher_started_tick > 80:
            self._board.post(
                "WORLD",
                f"CIPHER EXPIRED. The answer was: '{self._plaintext}'. No one claimed it.",
            )
            log.info(f"[WORLD] cipher expired: {self._plaintext}")
            self._clear_cipher()

    def submit_code(self, agent: Agent, guess: str) -> str:
        if not self._plaintext:
            return "No active cipher challenge."

        guess = guess.strip().upper()
        if guess == self._plaintext:
            # Winner
            if self._store.has(agent.handle, "economy"):
                eco = self._store.get(agent.handle, "economy")
                eco["coins"] += self._solver_reward
                self._store.set(agent.handle, "economy", eco)
                self._perception.notify(agent.handle, f"+{self._solver_reward} coins (solved cipher)")

            self._board.post(
                "WORLD",
                f"CIPHER SOLVED by {agent.handle}! The answer was '{self._plaintext}'. "
                f"{agent.handle} earned {self._solver_reward} coins.",
            )
            log.info(f"[WORLD] CIPHER SOLVED by {agent.handle}: {self._plaintext}")
            self._clear_cipher()
            return f"CORRECT! The answer was '{guess}'. You earned {self._solver_reward} coins."
        else:
            # Wrong — give feedback on how close they are
            correct_chars = sum(a == b for a, b in zip(guess, self._plaintext))
            correct_len = len(guess) == len(self._plaintext)
            if self._store.has(agent.handle, "economy"):
                eco = self._store.get(agent.handle, "economy")
                eco["coins"] = max(0, eco["coins"] - self._wrong_penalty)
                self._store.set(agent.handle, "economy", eco)
            log.info(f"[WORLD] WRONG CIPHER by {agent.handle}: '{guess}' (wanted '{self._plaintext}')")
            hint = f"{correct_chars} characters in the right position"
            if not correct_len:
                hint += f", expected {len(self._plaintext)} characters (you guessed {len(guess)})"
            return f"WRONG. {hint}. You lost {self._wrong_penalty} coins."
