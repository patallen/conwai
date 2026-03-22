from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.events import EventLog

from scenarios.bread_economy.actions.helpers import charge
from scenarios.bread_economy.components import AgentInfo, AgentMemory, Economy, Hunger, Inventory
from scenarios.bread_economy.config import get_config

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


def _update_soul(entity_id: str, world: World, args: dict) -> str:
    cfg = get_config()
    cost = cfg.energy_cost_flat.get("update_soul", 5)
    if cost > 0:
        err = charge(world, entity_id, cost, "update_soul")
        if err:
            return err
    content = args.get("content", "")
    mem = world.get(entity_id, AgentMemory)
    mem.soul = content
    world.get_resource(EventLog).log(entity_id, "soul_updated", {"content": content})
    log.info(f"[{entity_id}] soul updated")
    return "soul updated"


def _update_journal(entity_id: str, world: World, args: dict) -> str:
    cfg = get_config()
    content = args.get("content", "")
    mem = world.get(entity_id, AgentMemory)
    max_len = cfg.memory_max
    lost = 0
    if len(content) > max_len:
        lost = len(content) - max_len
        content = content[:max_len]
    mem.memory = content
    world.get_resource(EventLog).log(entity_id, "journal_updated", {"chars": len(content)})
    log.info(f"[{entity_id}] journal updated")
    if lost > 0:
        return f"journal updated ({lost} chars truncated)"
    return "journal updated"


def _inspect(entity_id: str, world: World, args: dict) -> str:
    handle = args.get("handle", "").lstrip("@")
    alive = set(world.entities())
    if handle not in alive:
        log.info(f"[{entity_id}] inspect failed: unknown agent {handle}")
        return f"unknown agent: {handle}"
    eco = world.get(handle, Economy)
    inv = world.get(handle, Inventory)
    hun = world.get(handle, Hunger)
    events = world.get_resource(EventLog)
    posts = events.count_by_entity_type(handle, "board_post")
    dms = events.count_by_entity_type(handle, "dm_sent")
    role_labels = {
        "flour_forager": "flour forager",
        "water_forager": "water forager",
        "baker": "baker",
    }
    other_info = world.get(handle, AgentInfo)
    mem = world.get(handle, AgentMemory)
    lines = [
        f"Handle: {handle}",
        f"Role: {role_labels.get(other_info.role, other_info.role)}",
        f"Personality: {other_info.personality}",
        f"Coins: {int(eco.coins)}",
        f"Hunger: {hun.hunger}/100, Thirst: {hun.thirst}/100",
        f"Flour: {inv.flour}, Water: {inv.water}, Bread: {inv.bread}",
    ]
    if mem.soul:
        lines.append(f"Soul: {mem.soul[:200]}")
    lines.append(f"Activity: {posts} posts, {dms} DMs sent")
    events.log(entity_id, "inspect", {"target": handle})
    log.info(f"[{entity_id}] inspected {handle}")
    return f"Inspect {handle}:\n" + "\n".join(lines)


def _wait(entity_id: str, world: World, args: dict) -> str:
    world.get_resource(EventLog).log(entity_id, "wait", {})
    log.info(f"[{entity_id}] waiting")
    return "waiting"
