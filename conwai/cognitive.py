"""Generator-based cognitive architecture.

A CognitiveFunction is a generator that yields Work items with tick costs.
The Brain's handle() method chains cognitive functions using yield from.
The runner drives the generator, feeding results back via .send().

The brain has no knowledge of the scheduler, async, or LLM clients.
It just yields work and receives results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Generator

from conwai.typemap import Percept, State

log = logging.getLogger("conwai")


@dataclass
class Work:
    """A unit of work yielded by the mind.

    type: what kind of thinking or action (triage, deliberate, react, command)
    tick_cost: how long this takes in simulated time
    prompt: what to think about (for thinking work)
    command: what to do (for action work)
    """
    type: str
    tick_cost: int = 1
    prompt: str | None = None
    command: dict | None = None


@dataclass
class WorkResult:
    """Result delivered back to the generator via .send()."""
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    data: dict = field(default_factory=dict)


# Type alias for cognitive function generators
CogGen = Generator[Work, WorkResult, Any]


class Mind:
    """Generator-based brain. Yields Work items, receives WorkResults.

    The Mind owns persistent state that accumulates across cycles.
    Each handle() call produces a generator that the runner drives.
    """

    def __init__(self, state_types: list[type] | None = None):
        self.state = State()
        self._state_registry = {t.__name__: t for t in (state_types or [])}

    def handle(self, percept: Percept) -> CogGen:
        """Override this. Yield Work items, receive WorkResults."""
        raise NotImplementedError

    def save_state(self) -> dict:
        return self.state.serialize()

    def load_state(self, data: dict) -> None:
        self.state = State.deserialize(data, self._state_registry)
