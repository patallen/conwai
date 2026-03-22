"""Typed components for the workbench scenario."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from conwai.cognition.types import BrainState
from conwai.component import Component

# Re-export framework BrainState so existing imports keep working
__all__ = ["AgentInfo", "BrainState"]


@dataclass
class AgentInfo(Component):
    __component_name__: ClassVar[str] = "agent_info"

    role: str = ""
    personality: str = ""
