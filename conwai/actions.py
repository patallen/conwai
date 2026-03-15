import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class Action:
    name: str
    description: str  # shown in system prompt
    cost_per_word: float | None = None  # if set, cost = words * this
    cost_flat: int = 0  # if cost_per_word is None, use this
    handler: Callable = None  # fn(agent, ctx, content, target) -> None

    def cost(self, content: str) -> int:
        if self.cost_per_word is not None:
            return max(1, int(len(content.split()) * self.cost_per_word))
        return self.cost_flat

    def prompt_line(self) -> str:
        if self.name in ("send_message", "inspect"):
            return f"[ACTION: {self.name} to=HANDLE] {self.description} [/ACTION]"
        if self.name in ("recall",):
            return f"[ACTION: {self.name}] [/ACTION] or [ACTION: {self.name} query=KEYWORD] [/ACTION]"
        return f"[ACTION: {self.name}] {self.description} [/ACTION]"


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, Action] = {}
        self._pattern: re.Pattern | None = None

    def register(self, action: Action):
        self._actions[action.name] = action
        self._pattern = None  # invalidate cached pattern

    def get(self, name: str) -> Action | None:
        return self._actions.get(name)

    @property
    def pattern(self) -> re.Pattern:
        if self._pattern is None:
            names = "|".join(re.escape(n) for n in self._actions)
            self._pattern = re.compile(
                rf"\[ACTION:\s*({names})"
                r"(?:\s+(?:to|query)=(\S+))?\]"
                r"\s*(.*?)\s*"
                r"(?:\[/ACTION\]|\]\s*$|\]\s*\n)",
                re.DOTALL | re.MULTILINE,
            )
        return self._pattern

    def parse(self, response: str) -> list[tuple[str, str, str]]:
        return [
            (action_type, target.strip() if target else "", content.strip())
            for action_type, target, content in self.pattern.findall(response)
        ]

    def prompt_lines(self) -> list[str]:
        return [a.prompt_line() for a in self._actions.values()]

    def execute(
        self, agent, ctx, action_name: str, content: str, target: str | None
    ) -> None:
        action = self._actions.get(action_name)
        if not action:
            return
        cost = action.cost(content)
        if cost > agent.energy:
            agent._action_log.append(
                f"not enough energy for {action_name} ({cost} needed, have {agent.energy})"
            )
            print(
                f"[{agent.handle}] NOT ENOUGH ENERGY for {action_name} ({cost} needed)",
                flush=True,
            )
            return
        agent.energy -= cost
        if cost > 0:
            agent._action_log.append(
                f"{action_name}: {cost} energy spent, {agent.energy} remaining"
            )
        else:
            agent._action_log.append(
                f"{action_name}: free, {agent.energy} energy remaining"
            )
        if action.handler:
            action.handler(agent, ctx, content, target)

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
