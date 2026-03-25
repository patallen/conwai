"""Board and DM actions — simplified from bread economy (no coin costs)."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from conwai.actions import ActionRegistry
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickNumber
from conwai.messages import MessageBus
from scenarios.commons.components import AgentMemory
from scenarios.commons.config import get_config

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


def _post_to_board(entity_id: str, world: World, args: dict) -> str:
    tick = world.get_resource(TickNumber).value
    mem = world.get(entity_id, AgentMemory)
    if mem.last_board_post and tick - mem.last_board_post < 3:
        return f"You posted recently. Wait {3 - (tick - mem.last_board_post)} more ticks."
    content = args.get("message", "")
    board = world.get_resource(BulletinBoard)
    board.post(entity_id, content)
    with world.mutate(entity_id, AgentMemory) as mem:
        mem.last_board_post = tick
    log.info(f"[{entity_id}] posted: {content}")
    return f"posted to board: {content}"


def _send_message(entity_id: str, world: World, args: dict) -> str:
    cfg = get_config()
    to = args.get("to", "").lstrip("@")
    message = args.get("message", "")
    if not to:
        return "missing 'to' field"
    action_reg = world.get_resource(ActionRegistry)
    dm_sent = action_reg.get_tick_state(entity_id, "dm_sent", 0)
    if dm_sent >= cfg.dm_limit_per_tick:
        return f"you already sent {cfg.dm_limit_per_tick} DMs this tick."
    bus = world.get_resource(MessageBus)
    err = bus.send(entity_id, to, message)
    if err:
        return f"DM failed: {err}"
    action_reg.set_tick_state(entity_id, "dm_sent", dm_sent + 1)
    log.info(f"[{entity_id}] -> [{to}]: {message}")
    return f"sent DM to {to}"
