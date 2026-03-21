from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Percept(Protocol):
    agent_id: str


@dataclass
class ActionFeedback:
    action: str
    args: dict[str, Any]
    result: str
