from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from scenarios.bread_economy.actions.helpers import _capped_add
from scenarios.bread_economy.config import get_config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


def _forage(agent: Agent, ctx: TickContext, args: dict) -> str:
    cfg = get_config()
    info = ctx.store.get(agent.handle, "agent_info")
    skills = cfg.forage_skill_by_role.get(info["role"], {"flour": 1, "water": 1})

    # Streak bonus: consecutive forages increase yield
    forage_data = ctx.store.get(agent.handle, "forage")
    last_tick = forage_data.get("last_tick", 0)
    current_tick = ctx.tick
    # Streak continues if last forage was the previous tick
    if last_tick > 0 and current_tick - last_tick == 1:
        streak = forage_data.get("streak", 0)
    else:
        streak = 0
    multiplier = 1.0 + streak * 0.5  # 1x, 1.5x, 2x, 2.5x, 3x cap
    multiplier = min(multiplier, 3.0)

    flour = int(random.randint(0, skills["flour"]) * multiplier)
    water = int(random.randint(0, skills["water"]) * multiplier)
    inv = ctx.store.get(agent.handle, "inventory")
    flour = _capped_add(inv, "flour", flour)
    water = _capped_add(inv, "water", water)
    ctx.store.set(agent.handle, "inventory", inv)

    # Update streak
    forage_data["streak"] = streak + 1
    forage_data["last_tick"] = current_tick
    ctx.store.set(agent.handle, "forage", forage_data)

    ctx.tick_state.setdefault(agent.handle, {})["blocked"] = "You are foraging this tick and cannot take other actions."
    ctx.events.log(agent.handle, "forage", {"flour": flour, "water": water, "streak": streak + 1, "multiplier": multiplier})
    log.info(f"[{agent.handle}] foraged {flour} flour, {water} water (streak {streak + 1}, {multiplier}x)")
    parts = []
    if flour > 0:
        parts.append(f"{flour} flour")
    if water > 0:
        parts.append(f"{water} water")
    streak_msg = f" (streak {streak + 1}, {multiplier}x bonus)" if streak > 0 else ""
    if parts:
        return f"foraged {', '.join(parts)}{streak_msg}"
    return f"found nothing{streak_msg}"


def _bake(agent: Agent, ctx: TickContext, args: dict) -> str:
    cfg = get_config()
    flour_needed = cfg.bake_cost["flour"]
    water_needed = cfg.bake_cost["water"]
    inv = ctx.store.get(agent.handle, "inventory")
    if inv["flour"] < flour_needed or inv["water"] < water_needed:
        return f"need {flour_needed} flour and {water_needed} water to bake (have {inv['flour']} flour, {inv['water']} water)"
    info = ctx.store.get(agent.handle, "agent_info")
    bread_yield = cfg.bake_baker_yield if info["role"] == "baker" else cfg.bake_yield
    inv["flour"] -= flour_needed
    inv["water"] -= water_needed
    bread_yield = _capped_add(inv, "bread", bread_yield)
    ctx.store.set(agent.handle, "inventory", inv)
    ctx.events.log(
        agent.handle,
        "bake",
        {"bread": bread_yield, "flour": inv["flour"], "water": inv["water"]},
    )
    log.info(f"[{agent.handle}] baked {bread_yield} bread")
    return f"baked {bread_yield} bread (flour: {inv['flour']}, water: {inv['water']}, bread: {inv['bread']})"
