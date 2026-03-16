from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Action:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    cost_per_word: float | None = None
    cost_flat: int = 0
    handler: Callable | None = None

    def cost(self, args: dict) -> int:
        if self.cost_per_word is not None:
            text = " ".join(str(v) for v in args.values())
            return max(1, int(len(text.split()) * self.cost_per_word))
        return self.cost_flat

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

    def register(self, action: Action):
        self._actions[action.name] = action

    def get(self, name: str) -> Action | None:
        return self._actions.get(name)

    def tool_definitions(self) -> list[dict]:
        return [a.tool_schema() for a in self._actions.values()]

    def execute(self, agent: Any, ctx: Any, name: str, args: dict) -> None:
        action = self._actions.get(name)
        if not action:
            return
        cost = action.cost(args)
        if cost > agent.coins:
            agent._action_log.append(
                f"not enough coins for {name} ({cost} needed, have {int(agent.coins)})"
            )
            print(
                f"[{agent.handle}] NOT ENOUGH ENERGY for {name} ({cost} needed)",
                flush=True,
            )
            return
        agent.coins -= cost
        if cost > 0:
            agent._action_log.append(
                f"{name}: {cost} coins spent, {int(agent.coins)} remaining"
            )
        else:
            agent._action_log.append(
                f"{name}: free, {int(agent.coins)} coins remaining"
            )
        if action.handler:
            action.handler(agent, ctx, args)

    def cost_description(self) -> str:
        paid = []
        free = []
        for a in self._actions.values():
            if a.cost_per_word:
                paid.append(f"{a.name}: {a.cost_per_word}/word")
            elif a.cost_flat > 0:
                paid.append(f"{a.name}: {a.cost_flat} flat")
            else:
                free.append(a.name)
        lines = []
        if paid:
            lines.append("Costs: " + ", ".join(paid))
        if free:
            lines.append("Free: " + ", ".join(free))
        return "\n".join(lines)
