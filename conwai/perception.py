from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import conwai.config as config


def tick_to_timestamp(tick: int) -> str:
    day = tick // 24 + 1
    hour = 8 + (tick % 24)
    if hour >= 24:
        hour -= 24
        day += 1
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"Day {day}, {display_hour}:00 {period}"

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
IDENTITY_TEMPLATE = (PROMPTS_DIR / "identity.md").read_text()
SOUL_TEMPLATE = (PROMPTS_DIR / "soul.md").read_text()
TICK_TEMPLATE = (PROMPTS_DIR / "tick.md").read_text()
SYSTEM_TEMPLATE = (PROMPTS_DIR / "system.md").read_text()


class Perception:
    def __init__(self):
        self._notifications: dict[str, list[str]] = defaultdict(list)

    def notify(self, handle: str, message: str) -> None:
        self._notifications[handle].append(message)

    def build_system_prompt(self) -> str:
        return SYSTEM_TEMPLATE

    def build_identity(self, agent: Agent, store: ComponentStore) -> str:
        from conwai.config import FORAGE_SKILL_BY_ROLE
        fs = FORAGE_SKILL_BY_ROLE
        role_descriptions = {
            "flour_forager": f"You are a flour forager. When you forage you find 0-{fs['flour_forager']['flour']} flour and 0-{fs['flour_forager']['water']} water. You cannot bake.",
            "water_forager": f"You are a water forager. When you forage you find 0-{fs['water_forager']['flour']} flour and 0-{fs['water_forager']['water']} water. You cannot bake.",
            "baker": f"You are a baker. You turn {config.BAKE_COST['flour']} flour + {config.BAKE_COST['water']} water into {config.BAKE_YIELD} bread. You forage poorly (0-{fs['baker']['flour']} flour, 0-{fs['baker']['water']} water).",
        }
        mem = store.get(agent.handle, "memory")
        soul = mem.get("soul", "")
        soul_block = SOUL_TEMPLATE.format(soul=soul or "(empty)")
        return IDENTITY_TEMPLATE.format(
            handle=agent.handle,
            personality=agent.personality,
            role_description=role_descriptions.get(agent.role, "unknown role"),
            soul=soul_block,
        )

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        tick: int,
    ) -> str:
        eco = store.get(agent.handle, "economy")
        inv = store.get(agent.handle, "inventory")
        hun = store.get(agent.handle, "hunger")
        mem = store.get(agent.handle, "memory")

        # Board
        new_posts = board.read_new(agent.handle)
        if new_posts:
            parts = ["New on the board:\n" + "\n".join(f"{p.handle}: {p.content}" for p in new_posts)]
        else:
            parts = ["No new activity on the board."]

        # DMs
        new_dms = bus.receive(agent.handle)
        if new_dms:
            parts.append("\n".join(f"DM from {dm.from_handle}: {dm.content}" for dm in new_dms))

        # Notifications from systems
        notifications = self._notifications.pop(agent.handle, [])
        if notifications:
            parts.append("Coin changes: " + ". ".join(notifications))

        # Code fragment
        if mem.get("code_fragment"):
            parts.append(f"YOUR CODE FRAGMENT: {mem['code_fragment']}")

        # Warnings
        if hun["hunger"] <= 30:
            parts.append(f"WARNING: You are hungry (hunger: {hun['hunger']}/100, bread: {inv['bread']}). Eat bread or raw flour to restore hunger.")
        if hun["thirst"] <= 30:
            parts.append(f"WARNING: You are thirsty (thirst: {hun['thirst']}/100, water: {inv['water']}). Drink water to restore thirst.")

        return TICK_TEMPLATE.format(
            timestamp=tick_to_timestamp(tick),
            coins=int(eco["coins"]),
            hunger=hun["hunger"],
            thirst=hun["thirst"],
            flour=inv["flour"],
            water=inv["water"],
            bread=inv["bread"],
            content="\n\n".join(parts),
        )
