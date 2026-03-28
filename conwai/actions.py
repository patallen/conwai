from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from conwai.component import Component

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

    @classmethod
    def from_dict(cls, data: dict) -> PendingActions:
        return cls(
            entries=[Decision(**e) if isinstance(e, dict) else e for e in data.get("entries", [])]
        )


@dataclass
class ActionFeedback(Component):
    """Results of executed actions. Written by ActionSystem, read by perception."""

    entries: list[ActionResult] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> ActionFeedback:
        return cls(
            entries=[ActionResult(**e) if isinstance(e, dict) else e for e in data.get("entries", [])]
        )


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

        raw = action.handler(entity_id, world, args)
        if isinstance(raw, tuple):
            result, data = raw
        else:
            result = raw or "ok"
            data = {}

        bus = world.bus
        if bus:
            from conwai.events import ActionExecuted
            bus.emit(ActionExecuted(
                entity=entity_id, action=name, args=args, result=result, data=data
            ))

        return result


class WorldActionAdapter:
    """Standard adapter: writes PendingActions, executes via registry, writes ActionFeedback."""

    def __init__(self, world: World, registry: ActionRegistry):
        self._world = world
        self._registry = registry

    async def execute(self, handle: str, decisions: list[Decision]) -> list[ActionResult]:
        self._world.set(handle, PendingActions(entries=decisions))
        results = []
        for d in decisions:
            result = self._registry.execute(handle, d.action, d.args, self._world)
            results.append(ActionResult(action=d.action, args=d.args, result=result))
        self._world.set(handle, ActionFeedback(entries=results))
        return results
