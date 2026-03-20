from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext


@dataclass
class Action:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    handler: Callable | None = None

    def tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys()),
                },
            },
        }


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, Action] = {}
        self._current_tick: int = 0

    def register(self, action: Action):
        self._actions[action.name] = action

    def get(self, name: str) -> Action | None:
        return self._actions.get(name)

    def tool_definitions(self) -> list[dict]:
        return [a.tool_schema() for a in self._actions.values()]

    def begin_tick(self, ctx: TickContext, handles: list[str]) -> None:
        self._current_tick = ctx.tick
        ctx.tick_state = {h: {} for h in handles}

    def execute(self, agent: Agent, name: str, args: dict, ctx: TickContext) -> str:
        action = self._actions.get(name)
        if not action:
            return f"unknown action: {name}"

        ts = ctx.tick_state.get(agent.handle, {})
        if ts.get("blocked"):
            return ts["blocked"]

        result = action.handler(agent, ctx, args) if action.handler else "ok"
        return result or "ok"
