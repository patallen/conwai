"""Typed components for the bread economy scenario."""

from __future__ import annotations

from dataclasses import dataclass

from conwai.component import Component

__all__ = ["Economy", "Inventory", "Hunger", "AgentMemory", "AgentInfo"]


@dataclass
class Economy(Component):
    coins: float = 500


@dataclass
class Inventory(Component):
    flour: int = 0
    water: int = 0
    bread: int = 0


@dataclass
class Hunger(Component):
    hunger: int = 100
    thirst: int = 100


@dataclass
class AgentMemory(Component):
    memory: str = ""
    code_fragment: str | None = None
    soul: str = ""
    strategy: str = ""
    last_board_post: int = 0


@dataclass
class AgentInfo(Component):
    role: str = ""
    personality: str = ""
