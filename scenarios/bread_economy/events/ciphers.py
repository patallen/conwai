from __future__ import annotations

import logging
import random
import string
from typing import TYPE_CHECKING

from scenarios.bread_economy.components import AgentMemory, Economy
from scenarios.bread_economy.config import get_config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.cognition.perception import PerceptionBuilder
    from conwai.messages import MessageBus
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")

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


class CipherSystem:
    """Runs substitution-cipher challenges with distributed clues."""

    def __init__(
        self,
        board: BulletinBoard,
        bus: MessageBus,
        pool: AgentPool,
        store: ComponentStore,
        perception: PerceptionBuilder,
        interval: int = 40,
        reward: int = 300,
        penalty: int = 10,
    ):
        self._board = board
        self._bus = bus
        self._pool = pool
        self._store = store
        self._perception = perception
        self.interval = interval
        self._reward = reward
        self._penalty = penalty

        self._plaintext: str | None = None
        self._ciphertext: str | None = None
        self._cipher_key: dict[str, str] = {}
        self._started_tick: int = 0
        self._clue_holders: dict[str, str] = {}  # handle -> clue description
        self._attempts: list[dict] = []
        self._used_phrases: set[int] = set()

    def tick(self, tick: int) -> None:
        # Hot-reload config
        cipher_cfg = get_config().raw_cfg.get("cipher", {})
        self._reward = cipher_cfg.get("reward", 300)
        self._penalty = cipher_cfg.get("wrong_penalty", 10)

        if self._plaintext:
            self._check_expiry(tick)

        # Cipher disabled — causes 9B models to death-spiral on reasoning
        # if not self._plaintext:
        #     first = tick == 10
        #     recurring = tick > 10 and tick % self.interval == 0
        #     if first or recurring:
        #         self._start(tick)

    def submit_code(self, agent: Agent, guess: str) -> str:
        if not self._plaintext:
            return "No active cipher challenge."

        guess = guess.strip().upper()
        if guess == self._plaintext:
            # Winner
            if self._store.has(agent.handle, Economy):
                eco = self._store.get(agent.handle, Economy)
                eco.coins += self._reward
                self._store.set(agent.handle, eco)
                self._perception.notify(agent.handle, f"+{self._reward} coins (solved cipher)")

            self._board.post(
                "WORLD",
                f"CIPHER SOLVED by {agent.handle}! The answer was '{self._plaintext}'. "
                f"{agent.handle} earned {self._reward} coins.",
            )
            log.info(f"[WORLD] CIPHER SOLVED by {agent.handle}: {self._plaintext}")
            self._clear()
            return f"CORRECT! The answer was '{guess}'. You earned {self._reward} coins."
        else:
            # Wrong — give feedback on how close they are
            correct_chars = sum(a == b for a, b in zip(guess, self._plaintext))
            correct_len = len(guess) == len(self._plaintext)
            if self._store.has(agent.handle, Economy):
                eco = self._store.get(agent.handle, Economy)
                eco.coins = max(0, eco.coins - self._penalty)
                self._store.set(agent.handle, eco)
            self._attempts.append({"handle": agent.handle, "guess": guess, "correct_chars": correct_chars})
            log.info(f"[WORLD] WRONG CIPHER by {agent.handle}: '{guess}' (wanted '{self._plaintext}')")
            hint = f"{correct_chars} characters in the right position"
            if not correct_len:
                hint += f", expected {len(self._plaintext)} characters (you guessed {len(guess)})"
            return f"WRONG. {hint}. You lost {self._penalty} coins."

    def get_status(self) -> dict | None:
        if not self._plaintext:
            return None
        return {
            "ciphertext": self._ciphertext,
            "started_tick": self._started_tick,
            "expires_tick": self._started_tick + 80,
            "clue_holders": list(self._clue_holders.keys()),
            "clues": {handle: clue for handle, clue in self._clue_holders.items()},
            "attempts": self._attempts,
            "reward": self._reward,
            "penalty": self._penalty,
        }

    # -- Internal --

    def _start(self, tick: int) -> None:
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
        self._attempts.clear()
        self._started_tick = tick
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
            letter = unique_letters[i % len(unique_letters)]
            cipher_letter = self._cipher_key[letter]
            clue = f"In the cipher, '{cipher_letter}' decodes to '{letter}'"
            self._clue_holders[handle] = clue

            # Store clue in agent's memory component
            if self._store.has(handle, AgentMemory):
                mem = self._store.get(handle, AgentMemory)
                mem.code_fragment = f"CIPHER CLUE: {clue}"
                self._store.set(handle, mem)

            self._bus.send(
                "WORLD",
                handle,
                f"CIPHER CHALLENGE: The message '{self._ciphertext}' is encrypted with a substitution cipher (each letter maps to a different letter). Your clue: {clue}. Replace that letter everywhere in the ciphertext, then trade clues with others to decode more letters. Do NOT guess random phrases. Submit only when you know the full plaintext. First correct answer wins {self._reward} coins. Wrong guess costs {self._penalty}.",
            )
            log.info(f"[WORLD] cipher clue -> [{handle}]: {clue}")

        self._board.post(
            "WORLD",
            f"CIPHER CHALLENGE: '{self._ciphertext}' — this is a substitution cipher (each letter replaced by another). {len(chosen)} agents have clues. Trade clues to decode it. First correct plaintext wins {self._reward} coins. Wrong = -{self._penalty}.",
        )
        log.info(f"[WORLD] cipher started: '{self._plaintext}' -> '{self._ciphertext}'")

    def _clear(self) -> None:
        for handle in self._clue_holders:
            if self._store.has(handle, AgentMemory):
                mem = self._store.get(handle, AgentMemory)
                mem.code_fragment = None
                self._store.set(handle, mem)
        self._clue_holders.clear()
        self._plaintext = None
        self._ciphertext = None
        self._cipher_key.clear()

    def _check_expiry(self, tick: int) -> None:
        if tick - self._started_tick > 80:
            self._board.post(
                "WORLD",
                f"CIPHER EXPIRED. The answer was: '{self._plaintext}'. No one claimed it.",
            )
            log.info(f"[WORLD] cipher expired: {self._plaintext}")
            self._clear()

    # -- State persistence helpers --

    def save_state(self) -> dict:
        return {
            "plaintext": self._plaintext,
            "ciphertext": self._ciphertext,
            "cipher_key": self._cipher_key,
            "cipher_started_tick": self._started_tick,
            "clue_holders": self._clue_holders,
            "attempts": self._attempts,
            "used_phrases": list(self._used_phrases),
        }

    def load_state(self, state: dict) -> None:
        self._plaintext = state.get("plaintext")
        self._ciphertext = state.get("ciphertext")
        self._cipher_key = state.get("cipher_key", {})
        self._started_tick = state.get("cipher_started_tick", 0)
        self._clue_holders = state.get("clue_holders", {})
        self._attempts = state.get("attempts", [])
        self._used_phrases = set(state.get("used_phrases", []))
