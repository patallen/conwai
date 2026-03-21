from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from conwai.cognition.percept import ActionFeedback

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore

_DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"


def tick_to_timestamp(tick: int) -> str:
    day = tick // 24 + 1
    hour = 8 + (tick % 24)
    if hour >= 24:
        hour -= 24
        day += 1
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"Day {day}, {display_hour}:00 {period}"


@dataclass
class BreadPercept:
    agent_id: str
    tick: int
    identity: str
    prompt_text: str
    action_feedback: list[ActionFeedback] = field(default_factory=list)

    def to_prompt(self) -> str:
        return self.prompt_text


class BreadPerceptionBuilder:
    """Builds BreadPercept objects from agent state each tick."""

    def __init__(self, prompts_dir: Path):
        self.identity_tpl = (prompts_dir / "identity.md").read_text()
        self.soul_tpl = (prompts_dir / "soul.md").read_text()
        self.memory_tpl = (prompts_dir / "memory.md").read_text()
        self.strategy_tpl = (prompts_dir / "strategy.md").read_text()
        self.tick_tpl = (prompts_dir / "tick.md").read_text()
        self.system_prompt = (prompts_dir / "system.md").read_text()
        self._notifications: dict[str, list[str]] = {}

    def notify(self, handle: str, message: str) -> None:
        self._notifications.setdefault(handle, []).append(message)

    def drain_notifications(self, handle: str) -> list[str]:
        return self._notifications.pop(handle, [])

    def build_system_prompt(self) -> str:
        return self.system_prompt

    def build_identity(self, agent: Agent, store: ComponentStore) -> str:
        from scenarios.bread_economy.config import get_config

        info = store.get(agent.handle, "agent_info")
        role_desc = get_config().role_descriptions.get(info["role"], "unknown role")
        mem = store.get(agent.handle, "memory")
        soul = mem.get("soul", "") or "(empty)"
        soul_block = self.soul_tpl.format(soul=soul)
        journal = mem.get("memory", "") or "(empty)"
        journal_block = self.memory_tpl.format(memory=journal)
        strategy = mem.get("strategy", "") or "(no strategy yet — set one at your next morning review)"
        strategy_block = self.strategy_tpl.format(strategy=strategy)
        return (
            self.identity_tpl.format(
                handle=f"@{agent.handle}",
                personality=info["personality"],
                role_description=role_desc,
                soul=soul_block,
            )
            + "\n\n"
            + strategy_block
            + "\n\n"
            + journal_block
        )

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        tick: int,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> BreadPercept:
        eco = store.get(agent.handle, "economy")
        inv = store.get(agent.handle, "inventory")
        hun = store.get(agent.handle, "hunger")
        mem = store.get(agent.handle, "memory")
        notifications = self.drain_notifications(agent.handle)

        new_posts = board.read_new(agent.handle)
        if new_posts:
            parts = [
                "New on the board:\n"
                + "\n".join(f"@{p.handle}: {p.content}" for p in new_posts)
            ]
        else:
            parts = ["No new activity on the board."]

        new_dms = bus.receive(agent.handle)
        if new_dms:
            parts.append(
                "\n".join(f"DM from @{dm.from_handle}: {dm.content}" for dm in new_dms)
            )

        if notifications:
            parts.append("Coin changes: " + ". ".join(notifications))

        if mem.get("code_fragment"):
            parts.append(f"YOUR CODE FRAGMENT: {mem['code_fragment']}")

        if hun["hunger"] <= 30:
            parts.append(
                f"WARNING: You are hungry (hunger: {hun['hunger']}/100, bread: {inv['bread']}). "
                "Eat bread or raw flour to restore hunger."
            )
        if hun["thirst"] <= 30:
            parts.append(
                f"WARNING: You are thirsty (thirst: {hun['thirst']}/100, water: {inv['water']}). "
                "Drink water to restore thirst."
            )

        prompt_text = self.tick_tpl.format(
            timestamp=tick_to_timestamp(tick),
            coins=int(eco["coins"]),
            hunger=hun["hunger"],
            thirst=hun["thirst"],
            flour=inv["flour"],
            water=inv["water"],
            bread=inv["bread"],
            content="\n\n".join(parts),
        )

        return BreadPercept(
            agent_id=agent.handle,
            tick=tick,
            identity=self.build_identity(agent, store),
            prompt_text=prompt_text,
            action_feedback=action_feedback or [],
        )


def make_bread_perception(prompts_dir: Path | None = None) -> BreadPerceptionBuilder:
    return BreadPerceptionBuilder(prompts_dir or _DEFAULT_PROMPTS_DIR)
