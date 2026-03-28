"""Typed components for the commons scenario."""

from __future__ import annotations

from dataclasses import dataclass

from conwai.component import Component

__all__ = ["FishHaul", "AgentMemory", "AgentInfo"]


@dataclass
class FishHaul(Component):
    fish: int = 0


@dataclass
class AgentMemory(Component):
    memory: str = ""
    soul: str = ""
    strategy: str = ""
    last_board_post: int = 0


@dataclass
class AgentInfo(Component):
    role: str = "fisher"
    personality: str = ""
