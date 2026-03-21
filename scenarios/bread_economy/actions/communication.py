from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scenarios.bread_economy.actions.helpers import charge
from scenarios.bread_economy.config import get_config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


def _post_to_board(agent: Agent, ctx: TickContext, args: dict) -> str:
    cfg = get_config()
    # Cooldown: 6 ticks between board posts
    mem = ctx.store.get(agent.handle, "memory")
    last_post_tick = mem.get("last_board_post", 0)
    if last_post_tick and ctx.tick - last_post_tick < 6:
        return f"You posted recently. Wait {6 - (ctx.tick - last_post_tick)} more ticks."
    err = charge(ctx.store, agent.handle, 25, "post_to_board")
    if err:
        return err
    content = args.get("message", "")
    ctx.board.post(agent.handle, content)
    mem["last_board_post"] = ctx.tick
    ctx.store.set(agent.handle, "memory", mem)
    ctx.events.log(agent.handle, "board_post", {"content": content})
    log.info(f"[{agent.handle}] posted: {content}")
    if ctx.pool:
        for a in ctx.pool.alive():
            if a.handle != agent.handle and a.handle in content:
                other_eco = ctx.store.get(a.handle, "economy")
                other_eco["coins"] += cfg.energy_gain["referenced"]
                ctx.store.set(a.handle, "economy", other_eco)
                if ctx.perception:
                    ctx.perception.notify(
                        a.handle,
                        f"+{cfg.energy_gain['referenced']} coins (referenced on board)",
                    )
    return f"posted to board: {content}"


def _send_message(agent: Agent, ctx: TickContext, args: dict) -> str:
    cfg = get_config()
    to = args.get("to", "")
    message = args.get("message", "")
    if not to:
        return "missing 'to' field"
    tick_data = ctx.tick_state.get(agent.handle, {})
    dm_sent = tick_data.get("dm_sent", 0)
    if dm_sent >= 2:
        return "you already sent 2 DMs this tick. Wait until next tick."
    err = ctx.bus.send(agent.handle, to, message)
    if err:
        log.info(f"[{agent.handle}] SEND FAILED: {err}")
        return f"DM failed: {err}"
    tick_data["dm_sent"] = dm_sent + 1
    ctx.tick_state[agent.handle] = tick_data
    ctx.events.log(agent.handle, "dm_sent", {"to": to, "content": message})
    log.info(f"[{agent.handle}] -> [{to}]: {message}")
    if ctx.pool:
        recipient = ctx.pool.by_handle(to)
        if recipient:
            rec_eco = ctx.store.get(to, "economy")
            rec_eco["coins"] += cfg.energy_gain["dm_received"]
            ctx.store.set(to, "economy", rec_eco)
            if ctx.perception:
                ctx.perception.notify(
                    to,
                    f"+{cfg.energy_gain['dm_received']} coins (received DM)",
                )
    return f"sent DM to {to}"
