from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.events import EventLog
    from conwai.messages import MessageBus
    from conwai.perception import Perception
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore


@dataclass
class Action:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    cost_flat: int = 0
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
    def __init__(
        self,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        events: EventLog,
        pool: AgentPool | None = None,
        perception: Perception | None = None,
        world: Any = None,
    ):
        self._actions: dict[str, Action] = {}
        self.store = store
        self.board = board
        self.bus = bus
        self.events = events
        self.pool = pool
        self.perception = perception
        self.world = world
        self.tick_state: dict[str, dict] = {}

    def register(self, action: Action):
        self._actions[action.name] = action

    def get(self, name: str) -> Action | None:
        return self._actions.get(name)

    def tool_definitions(self) -> list[dict]:
        return [a.tool_schema() for a in self._actions.values()]

    def execute(self, agent: Agent, name: str, args: dict) -> str:
        action = self._actions.get(name)
        if not action:
            return f"unknown action: {name}"

        ts = self.tick_state.get(agent.handle, {})
        if ts.get("foraging"):
            return "You are foraging this tick and cannot take other actions."

        # Reset forage streak if doing something else
        if name != "forage" and self.store.has(agent.handle, "forage"):
            forage_data = self.store.get(agent.handle, "forage")
            if forage_data.get("streak", 0) > 0:
                forage_data["streak"] = 0
                self.store.set(agent.handle, "forage", forage_data)

        eco = self.store.get(agent.handle, "economy")
        if action.cost_flat > eco["coins"]:
            return f"not enough coins for {name} ({action.cost_flat} needed, have {int(eco['coins'])})"

        eco["coins"] -= action.cost_flat
        self.store.set(agent.handle, "economy", eco)

        cost_msg = (
            f"{name}: {action.cost_flat} coins spent, {int(eco['coins'])} remaining"
            if action.cost_flat > 0
            else ""
        )

        result = action.handler(agent, self, args) if action.handler else "ok"
        if cost_msg and result:
            return f"{cost_msg}. {result}"
        return cost_msg or result or "ok"
