from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.cognition.perception import PerceptionBuilder
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore

from scenarios.bread_economy.components import Economy

log = logging.getLogger("conwai")


class ElectionSystem:
    """Runs periodic elections where agents vote for a coin reward recipient."""

    def __init__(
        self,
        board: BulletinBoard,
        pool: AgentPool,
        store: ComponentStore,
        perception: PerceptionBuilder,
        interval: int = 50,
        duration: int = 15,
        reward: int = 200,
    ):
        self._board = board
        self._pool = pool
        self._store = store
        self._perception = perception
        self.interval = interval
        self.duration = duration
        self._reward = reward

        self._active: bool = False
        self._started_tick: int = 0
        self._votes: dict[str, str] = {}  # voter_handle -> candidate_handle

    def tick(self, tick: int) -> None:
        if self._active:
            self._check_end(tick)
        elif tick == 10 or (tick > 10 and tick % self.interval == 0):
            self._start(tick)

    def cast_vote(self, agent: Agent, candidate: str, tick: int) -> str:
        if not self._active:
            return "No active election."
        candidate = candidate.strip()
        if not self._pool.by_handle(candidate):
            return f"Unknown agent: {candidate}"
        if candidate == agent.handle:
            return "You cannot vote for yourself."
        old = self._votes.get(agent.handle)
        self._votes[agent.handle] = candidate
        ticks_left = self.duration - (tick - self._started_tick)
        if old and old != candidate:
            return f"Vote changed from {old} to {candidate}. {ticks_left} ticks left."
        return f"Voted for {candidate}. {ticks_left} ticks left in the election."

    # -- Internal --

    def _start(self, tick: int) -> None:
        self._active = True
        self._started_tick = tick
        self._votes.clear()
        self._board.post(
            "WORLD",
            f"ELECTION: Vote for one agent to receive {self._reward} coins. "
            f"Use the vote action. You can change your vote. "
            f"Voting ends in {self.duration} ticks. Most votes wins.",
        )
        log.info(f"[WORLD] election started (reward: {self._reward}, ends tick {tick + self.duration})")

    def _check_end(self, tick: int) -> None:
        if tick - self._started_tick < self.duration:
            return

        self._active = False

        if not self._votes:
            self._board.post("WORLD", "ELECTION ENDED: No votes cast. No winner.")
            log.info("[WORLD] election ended with no votes")
            return

        # Count votes
        tally: dict[str, list[str]] = {}
        for voter, candidate in self._votes.items():
            tally.setdefault(candidate, []).append(voter)

        # Find winner (most votes, random tiebreak)
        max_votes = max(len(v) for v in tally.values())
        winners = [c for c, v in tally.items() if len(v) == max_votes]
        winner = random.choice(winners)
        vote_count = len(tally[winner])

        # Award coins
        if self._store.has(winner, Economy):
            eco = self._store.get(winner, Economy)
            eco.coins += self._reward
            self._store.set(winner, eco)
            self._perception.notify(winner, f"+{self._reward} coins (won election)")

        # Announce results
        results = ", ".join(f"{c}: {len(v)} votes" for c, v in sorted(tally.items(), key=lambda x: -len(x[1])))
        self._board.post(
            "WORLD",
            f"ELECTION WON by {winner} with {vote_count} votes! "
            f"They receive {self._reward} coins. Results: {results}",
        )
        log.info(f"[WORLD] election won by {winner} ({vote_count} votes). Tally: {results}")

        self._votes.clear()

    # -- State persistence helpers --

    def save_state(self) -> dict:
        return {
            "election_active": self._active,
            "election_started_tick": self._started_tick,
            "votes": self._votes,
        }

    def load_state(self, state: dict) -> None:
        self._active = state.get("election_active", False)
        self._started_tick = state.get("election_started_tick", 0)
        self._votes = state.get("votes", {})
