import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Action:
    name: str
    description: str  # shown in system prompt
    cost_per_word: int | None = None  # if set, cost = words * this
    cost_flat: int = 0  # if cost_per_word is None, use this
    handler: Callable = None  # fn(agent, ctx, content, target) -> None

    def cost(self, content: str) -> int:
        if self.cost_per_word is not None:
            return max(1, len(content.split()) * self.cost_per_word)
        return self.cost_flat

    def prompt_line(self) -> str:
        if self.name in ("send_message",):
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

    def cost_description(self) -> str:
        parts = []
        for a in self._actions.values():
            if a.cost_per_word is not None:
                parts.append(f"{a.name} costs {a.cost_per_word} per word")
            elif a.cost_flat > 0:
                parts.append(f"{a.name} costs {a.cost_flat} flat")
            else:
                parts.append(f"{a.name} is free")
        return ". ".join(parts)
