from __future__ import annotations

import logging
from typing import Protocol

from conwai.cognition.types import Decision
from conwai.processes.types import Decisions
from conwai.typemap import Blackboard, Percept

log = logging.getLogger("conwai")


class Process(Protocol):
    async def run(self, percept: Percept, bb: Blackboard) -> None: ...


class BlackboardBrain:
    """Run a pipeline of processes, producing decisions.

    The brain owns a persistent Blackboard that accumulates state across
    cycles (working memory, episodes). Each think() call receives a fresh
    Percept from the scenario, runs the process pipeline, and returns
    the decisions produced.
    """

    def __init__(self, processes: list[Process]):
        self.processes = processes
        self.bb = Blackboard()

    async def think(self, percept: Percept) -> list[Decision]:
        self.bb.set(Decisions())

        for process in self.processes:
            await process.run(percept, self.bb)

        decisions = self.bb.get(Decisions)
        return decisions.entries if decisions else []

    def get_state(self) -> Blackboard:
        """Expose the blackboard for external persistence."""
        return self.bb

    def load_state(self, bb: Blackboard) -> None:
        """Restore a previously persisted blackboard."""
        self.bb = bb
