from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from conwai.cognition.percept import Percept


@dataclass
class Decision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Brain(Protocol):
    async def think(self, percept: Percept) -> list[Decision]: ...
