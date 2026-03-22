"""Types for the cognitive pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from conwai.component import Component
from conwai.processes.types import (
    Episodes,
    Episode,
    WorkingMemory,
    WorkingMemoryEntry,
)
from conwai.typemap import Blackboard


@dataclass
class Decision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainState(Component):
    """Persistent cognitive state stored between ticks.

    Serializes/deserializes WorkingMemory and Episodes to/from the
    component store. Call ``load_into`` to hydrate a Blackboard on
    startup, and ``save_from`` to dehydrate for storage.
    """

    working_memory: list[dict] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)
    last_tick: int = 0
    tick_entry_start: int | None = None

    def load_into(self, bb: Blackboard) -> None:
        """Hydrate working memory and episodes onto a blackboard."""
        bb.set(WorkingMemory(
            entries=[WorkingMemoryEntry(**e) for e in self.working_memory],
            last_tick=self.last_tick,
            tick_entry_start=self.tick_entry_start,
        ))
        bb.set(Episodes(
            entries=[Episode(**e) for e in self.episodes],
        ))

    @classmethod
    def save_from(cls, bb: Blackboard) -> BrainState:
        """Dehydrate working memory and episodes from a blackboard."""
        wm = bb.get(WorkingMemory) or WorkingMemory()
        eps = bb.get(Episodes) or Episodes()
        return cls(
            working_memory=[
                {"content": e.content, "kind": e.kind}
                for e in wm.entries
            ],
            episodes=[
                {
                    "content": e.content,
                    "tick": e.tick,
                    **({"embedding": e.embedding} if e.embedding is not None else {}),
                }
                for e in eps.entries
            ],
            last_tick=wm.last_tick,
            tick_entry_start=wm.tick_entry_start,
        )
