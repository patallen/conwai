from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from conwai.component import Component

if TYPE_CHECKING:
    from conwai.brain import Decision
    from conwai.world import World


@dataclass
class ActionResult:
    """Result of a single executed action."""

    action: str
    args: dict[str, Any]
    result: str


@dataclass
class PendingActions(Component):
    """Decisions waiting to be executed."""

    entries: list[Decision] = field(default_factory=list)


@dataclass
class ActionFeedback(Component):
    """Results of executed actions. Written by ActionSystem, read by perception."""

    entries: list[ActionResult] = field(default_factory=list)


@dataclass
class Action:
    name: str
    handler: Callable


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, Action] = {}
        self._tick_state: dict[str, dict] = {}

    def register(self, action: Action):
        self._actions[action.name] = action

    def get(self, name: str) -> Action | None:
        return self._actions.get(name)

    def begin_tick(self, world: World, handles: list[str]) -> None:
        self._tick_state = {h: {} for h in handles}

    def block(self, entity_id: str, reason: str) -> None:
        if entity_id in self._tick_state:
            self._tick_state[entity_id]["blocked"] = reason

    def get_tick_state(self, entity_id: str, key: str, default=None):
        return self._tick_state.get(entity_id, {}).get(key, default)

    def set_tick_state(self, entity_id: str, key: str, value) -> None:
        if entity_id in self._tick_state:
            self._tick_state[entity_id][key] = value

    def execute(self, entity_id: str, name: str, args: dict, world: World) -> str:
        action = self._actions.get(name)
        if not action:
            return f"unknown action: {name}"

        ts = self._tick_state.get(entity_id, {})
        if ts.get("blocked"):
            return ts["blocked"]

        result = action.handler(entity_id, world, args)
        return result or "ok"
