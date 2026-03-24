from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from conwai.actions import ActionFeedback
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickNumber
from conwai.messages import MessageBus
from conwai.processes.types import (
    AgentHandle,
    Identity,
    Observations,
    PerceptFeedback,
    PerceptTick,
)
from conwai.typemap import Percept
from scenarios.bread_economy.components import (
    AgentInfo,
    AgentMemory,
    Economy,
    Hunger,
    Inventory,
)

if TYPE_CHECKING:
    from conwai.world import World

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


class BreadPerceptionBuilder:
    """Builds Percept from agent state each tick."""

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

    def build_identity(self, entity_id: str, world: World) -> str:
        from scenarios.bread_economy.config import get_config

        info = world.get(entity_id, AgentInfo)
        role_desc = get_config().role_descriptions.get(info.role, "unknown role")
        mem = world.get(entity_id, AgentMemory)
        soul = mem.soul or "(empty)"
        soul_block = self.soul_tpl.format(soul=soul)
        journal = mem.memory or "(empty)"
        journal_block = self.memory_tpl.format(memory=journal)
        strategy = (
            mem.strategy or "(no strategy yet -- set one at your next morning review)"
        )
        strategy_block = self.strategy_tpl.format(strategy=strategy)
        return (
            self.identity_tpl.format(
                handle=f"@{entity_id}",
                personality=info.personality,
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
        entity_id: str,
        world: World,
    ) -> Percept:
        tick = world.get_resource(TickNumber).value
        board = world.get_resource(BulletinBoard)
        bus = world.get_resource(MessageBus)

        eco = world.get(entity_id, Economy)
        inv = world.get(entity_id, Inventory)
        hun = world.get(entity_id, Hunger)
        mem = world.get(entity_id, AgentMemory)
        notifications = self.drain_notifications(entity_id)

        new_posts = board.read_new(entity_id)
        if new_posts:
            parts = [
                "New on the board:\n"
                + "\n".join(f"@{p.handle}: {p.content}" for p in new_posts)
            ]
        else:
            parts = ["No new activity on the board."]

        new_dms = bus.receive(entity_id)
        if new_dms:
            parts.append(
                "\n".join(f"DM from @{dm.from_handle}: {dm.content}" for dm in new_dms)
            )

        if notifications:
            parts.append("Notifications: " + ". ".join(notifications))

        # Show pending trade offers directed at this agent
        from scenarios.bread_economy.actions.economy import OfferBook
        if world.has_resource(OfferBook):
            offer_book = world.get_resource(OfferBook)
            pending = offer_book.offers_for(entity_id, tick)
            if pending:
                offer_lines = []
                for oid, o in pending:
                    remaining = o["tick"] + offer_book.expiry - tick
                    offer_lines.append(
                        f"Offer #{oid} from @{o['from']}: {o['give_amount']} {o['give_type']} "
                        f"for {o['want_amount']} {o['want_type']} "
                        f"(expires in {remaining} ticks). Use accept(offer_id={oid}) to accept."
                    )
                parts.append("Pending trade offers for you:\n" + "\n".join(offer_lines))

        if mem.code_fragment:
            parts.append(f"YOUR CODE FRAGMENT: {mem.code_fragment}")

        if hun.hunger <= 30:
            parts.append(
                f"WARNING: You are hungry (hunger: {hun.hunger}/100, bread: {inv.bread}). "
                "Eat bread or raw flour to restore hunger."
            )
        if hun.thirst <= 30:
            parts.append(
                f"WARNING: You are thirsty (thirst: {hun.thirst}/100, water: {inv.water}). "
                "Drink water to restore thirst."
            )

        observations = "\n\n".join(parts)

        prompt_text = self.tick_tpl.format(
            timestamp=tick_to_timestamp(tick),
            coins=int(eco.coins),
            hunger=hun.hunger,
            thirst=hun.thirst,
            flour=inv.flour,
            water=inv.water,
            bread=inv.bread,
            content=observations,
        )

        percept = Percept()
        percept.set(AgentHandle(value=entity_id))
        percept.set(PerceptTick(value=tick))
        percept.set(Identity(text=self.build_identity(entity_id, world)))
        percept.set(Observations(text=prompt_text))
        if world.has(entity_id, ActionFeedback):
            fb = world.get(entity_id, ActionFeedback)
            percept.set(PerceptFeedback(entries=fb.entries))
        else:
            percept.set(PerceptFeedback(entries=[]))
        return percept


def make_bread_perception(prompts_dir: Path | None = None) -> BreadPerceptionBuilder:
    return BreadPerceptionBuilder(prompts_dir or _DEFAULT_PROMPTS_DIR)
