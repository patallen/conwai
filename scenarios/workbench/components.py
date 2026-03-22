"""Typed components for the workbench scenario."""

from __future__ import annotations

from dataclasses import dataclass

from conwai.cognition.types import BrainState
from conwai.component import Component

# Re-export framework BrainState so existing imports keep working
__all__ = ["AgentInfo", "BrainState"]


@dataclass
class AgentInfo(Component):
    role: str = ""
    personality: str = ""
