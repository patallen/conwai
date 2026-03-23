"""Typed components for the workbench scenario."""

from __future__ import annotations

from dataclasses import dataclass

from conwai.component import Component

__all__ = ["AgentInfo"]


@dataclass
class AgentInfo(Component):
    role: str = ""
    personality: str = ""
