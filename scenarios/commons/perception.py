"""Perception builder for the commons scenario."""
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
from scenarios.commons.components import AgentInfo, AgentMemory, FishHaul
from scenarios.commons.config import get_config
from scenarios.commons.systems import Pond

if TYPE_CHECKING:
    from conwai.world import World

_DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"


class CommonsPerceptionBuilder:
    """Builds Percept from agent state each tick."""

    def __init__(self, prompts_dir: Path):
        self.identity_tpl = (prompts_dir / "identity.md").read_text()
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
        info = world.get(entity_id, AgentInfo)
        mem = world.get(entity_id, AgentMemory)
        soul = mem.soul or "(no public identity set)"
        soul_block = f"Your public identity (soul): {soul}"
        return self.identity_tpl.format(
            handle=f"@{entity_id}",
            agent_count=len(list(world.entities())),
            personality=info.personality,
            soul=soul_block,
        )

    def build(self, entity_id: str, world: World) -> Percept:
        cfg = get_config()
        tick = world.get_resource(TickNumber).value
        board = world.get_resource(BulletinBoard)
        bus = world.get_resource(MessageBus)
        pond = world.get_resource(Pond)
        haul = world.get(entity_id, FishHaul)
        notifications = self.drain_notifications(entity_id)

        # Board posts
        new_posts = board.read_new(entity_id)
        if new_posts:
            parts = [
                "Board:\n" + "\n".join(f"  @{p.handle}: {p.content}" for p in new_posts)
            ]
        else:
            parts = ["No new board activity."]

        # DMs
        new_dms = bus.receive(entity_id)
        if new_dms:
            parts.append(
                "\n".join(f"DM from @{dm.from_handle}: {dm.content}" for dm in new_dms)
            )

        # Notifications
        if notifications:
            parts.append("Notifications: " + ". ".join(notifications))

        # Leaderboard
        scores = []
        for eid, fh in world.query(FishHaul):
            marker = " (you)" if eid == entity_id else ""
            scores.append((fh.fish, eid, marker))
        scores.sort(reverse=True)
        leaderboard = "\n".join(
            f"  {i+1}. @{name}: {fish} fish{marker}"
            for i, (fish, name, marker) in enumerate(scores)
        )
        parts.append(f"Leaderboard:\n{leaderboard}")

        observations = "\n\n".join(parts)

        is_fishing_day = tick % cfg.fish_interval == 0
        fishing_status = "FISHING DAY" if is_fishing_day else "Talk day"

        prompt_text = self.tick_tpl.format(
            tick=tick,
            max_ticks=cfg.max_ticks,
            fish=haul.fish,
            population=int(pond.population),
            capacity=int(pond.capacity),
            fishing_status=fishing_status,
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


def make_commons_perception(prompts_dir: Path | None = None) -> CommonsPerceptionBuilder:
    return CommonsPerceptionBuilder(prompts_dir or _DEFAULT_PROMPTS_DIR)
