from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scenarios.bread_economy.actions.helpers import charge
from scenarios.bread_economy.components import AgentInfo, AgentMemory, Economy, Hunger, Inventory
from scenarios.bread_economy.config import get_config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


def _update_soul(agent: Agent, ctx: TickContext, args: dict) -> str:
    cfg = get_config()
    cost = cfg.energy_cost_flat.get("update_soul", 5)
    if cost > 0:
        err = charge(ctx.store, agent.handle, cost, "update_soul")
        if err:
            return err
    content = args.get("content", "")
    mem = ctx.store.get(agent.handle, AgentMemory)
    mem.soul = content
    ctx.store.set(agent.handle, mem)
    ctx.events.log(agent.handle, "soul_updated", {"content": content})
    log.info(f"[{agent.handle}] soul updated")
    return "soul updated"


def _update_journal(agent: Agent, ctx: TickContext, args: dict) -> str:
    cfg = get_config()
    content = args.get("content", "")
    mem = ctx.store.get(agent.handle, AgentMemory)
    max_len = cfg.memory_max
    lost = 0
    if len(content) > max_len:
        lost = len(content) - max_len
        content = content[:max_len]
    mem.memory = content
    ctx.store.set(agent.handle, mem)
    ctx.events.log(agent.handle, "journal_updated", {"chars": len(content)})
    log.info(f"[{agent.handle}] journal updated")
    if lost > 0:
        return f"journal updated ({lost} chars truncated)"
    return "journal updated"


def _inspect(agent: Agent, ctx: TickContext, args: dict) -> str:
    handle = args.get("handle", "").lstrip("@")
    if not ctx.pool:
        return "inspection unavailable"
    other = ctx.pool.by_handle(handle)
    if not other:
        log.info(f"[{agent.handle}] inspect failed: unknown agent {handle}")
        return f"unknown agent: {handle}"
    eco = ctx.store.get(handle, Economy)
    inv = ctx.store.get(handle, Inventory)
    hun = ctx.store.get(handle, Hunger)
    posts = ctx.events.count_by_entity_type(handle, "board_post")
    dms = ctx.events.count_by_entity_type(handle, "dm_sent")
    role_labels = {
        "flour_forager": "flour forager",
        "water_forager": "water forager",
        "baker": "baker",
    }
    other_info = ctx.store.get(handle, AgentInfo)
    mem = ctx.store.get(handle, AgentMemory)
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
    ctx.events.log(agent.handle, "inspect", {"target": handle})
    log.info(f"[{agent.handle}] inspected {handle}")
    return f"Inspect {handle}:\n" + "\n".join(lines)


def _wait(agent: Agent, ctx: TickContext, args: dict) -> str:
    ctx.events.log(agent.handle, "wait", {})
    log.info(f"[{agent.handle}] waiting")
    return "waiting"
