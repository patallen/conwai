from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Agent:
    handle: str
    role: str
    alive: bool = True
    born_tick: int = 0
    personality: str = ""
