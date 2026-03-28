"""Concrete event types for the conwai simulation framework."""

from __future__ import annotations

from dataclasses import dataclass, field

from conwai.component import Component
from conwai.events.bus import Event


@dataclass
class ComponentChanged(Event):
    """A component was modified on an entity."""

    entity: str = ""
    comp_type: type[Component] = Component
    old: Component | None = None
    new: Component | None = None


@dataclass
class EntitySpawned(Event):
    """A new entity was added to the world."""

    entity: str = ""


@dataclass
class EntityDestroyed(Event):
    """An entity was removed from the world."""

    entity: str = ""


@dataclass
class ActionExecuted(Event):
    """An entity executed an action."""

    entity: str = ""
    action: str = ""
    args: dict = field(default_factory=dict)
    result: str = ""
    data: dict = field(default_factory=dict)
