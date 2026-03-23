"""Brain: a cognitive pipeline over a persistent state and per-cycle blackboard."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from conwai.typemap import Blackboard, Percept, State

log = logging.getLogger("conwai")


@dataclass
class Decision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decisions:
    """Actions the agent wants to take this cycle."""

    entries: list[Decision] = field(default_factory=list)


@dataclass
class BrainContext:
    """Everything a process needs for one cognitive cycle."""

    percept: Percept
    state: State
    bb: Blackboard


class Process(Protocol):
    async def run(self, ctx: BrainContext) -> None: ...


class Brain:
    """Run a pipeline of processes, producing decisions.

    The brain owns a persistent State typemap that accumulates across
    cycles (working memory, episodes, etc.). Each think() call creates
    a fresh Blackboard for per-cycle scratch, builds a BrainContext,
    and runs the process pipeline.
    """

    def __init__(
        self,
        processes: list[Process],
        state_types: list[type] | None = None,
    ):
        self.processes = processes
        self.state = State()
        self._state_registry = {t.__name__: t for t in (state_types or [])}

    async def think(self, percept: Percept) -> list[Decision]:
        ctx = BrainContext(percept=percept, state=self.state, bb=Blackboard())

        for process in self.processes:
            await process.run(ctx)

        decisions = ctx.bb.get(Decisions)
        return decisions.entries if decisions else []

    def save_state(self) -> dict:
        """Serialize persistent state for storage."""
        return self.state.serialize()

    def load_state(self, data: dict) -> None:
        """Restore persistent state from storage."""
        self.state = State.deserialize(data, self._state_registry)
