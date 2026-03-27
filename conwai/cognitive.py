"""Generator-based cognitive architecture.

The Mind yields Work items. The runner drives the generator, fulfilling
each Work item however it wants (LLM call, rule engine, lookup table)
and sending the result back via .send().

The framework only cares about Work.type and Work.tick_cost. Everything
else is between the Mind implementation and its runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generator

from conwai.typemap import Percept, State


@dataclass
class Work:
    """A unit of work yielded by the mind.

    type: what kind of work (the mind and runner agree on valid types)
    tick_cost: how long this takes in simulated time
    """
    type: str
    tick_cost: int = 0


@dataclass
class WorkResult:
    """Result sent back to the mind via .send()."""
    pass


CogGen = Generator[Work, WorkResult, None]


class Mind:
    """Generator-based brain. Yields Work items, receives results.

    The Mind owns persistent state that accumulates across cycles.
    Each handle() call produces a generator that the runner drives.
    """

    def __init__(self, state_types: list[type] | None = None):
        self.state = State()
        self._state_registry = {t.__name__: t for t in (state_types or [])}

    def handle(self, percept: Percept) -> CogGen:
        """Override this. Yield Work items, receive results."""
        raise NotImplementedError

    def save_state(self) -> dict:
        return self.state.serialize()

    def load_state(self, data: dict) -> None:
        self.state = State.deserialize(data, self._state_registry)
