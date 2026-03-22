from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.actions import ActionRegistry
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickNumber
from conwai.events import EventLog
from conwai.messages import MessageBus

from scenarios.bread_economy.actions.helpers import charge
from scenarios.bread_economy.components import AgentMemory, Economy
from scenarios.bread_economy.config import get_config
from scenarios.bread_economy.perception import BreadPerceptionBuilder

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


def _post_to_board(entity_id: str, world: World, args: dict) -> str:
    cfg = get_config()
    tick = world.get_resource(TickNumber).value
    # Cooldown: 6 ticks between board posts
    mem = world.get(entity_id, AgentMemory)
    if mem.last_board_post and tick - mem.last_board_post < 6:
        return f"You posted recently. Wait {6 - (tick - mem.last_board_post)} more ticks."
    err = charge(world, entity_id, 25, "post_to_board")
    if err:
        return err
    content = args.get("message", "")
    board = world.get_resource(BulletinBoard)
    board.post(entity_id, content)
    mem.last_board_post = tick
    world.get_resource(EventLog).log(entity_id, "board_post", {"content": content})
    log.info(f"[{entity_id}] posted: {content}")
    perception = world.get_resource(BreadPerceptionBuilder)
    for other in world.entities():
        if other != entity_id and f"@{other}" in content:
            other_eco = world.get(other, Economy)
            other_eco.coins += cfg.energy_gain["referenced"]
            perception.notify(
                other,
                f"+{cfg.energy_gain['referenced']} coins (referenced on board)",
            )
    return f"posted to board: {content}"


def _send_message(entity_id: str, world: World, args: dict) -> str:
    cfg = get_config()
    to = args.get("to", "").lstrip("@")
    message = args.get("message", "")
    if not to:
        return "missing 'to' field"
    # DM rate limit via ActionRegistry tick_state
    action_reg = world.get_resource(ActionRegistry)
    ts = action_reg._tick_state.get(entity_id, {})
    dm_sent = ts.get("dm_sent", 0)
    if dm_sent >= 2:
        return "you already sent 2 DMs this tick. Wait until next tick."
    bus = world.get_resource(MessageBus)
    err = bus.send(entity_id, to, message)
    if err:
        log.info(f"[{entity_id}] SEND FAILED: {err}")
        return f"DM failed: {err}"
    ts["dm_sent"] = dm_sent + 1
    action_reg._tick_state[entity_id] = ts
    world.get_resource(EventLog).log(entity_id, "dm_sent", {"to": to, "content": message})
    log.info(f"[{entity_id}] -> [{to}]: {message}")
    alive = set(world.entities())
    if to in alive:
        rec_eco = world.get(to, Economy)
        rec_eco.coins += cfg.energy_gain["dm_received"]
        world.get_resource(BreadPerceptionBuilder).notify(
            to,
            f"+{cfg.energy_gain['dm_received']} coins (received DM)",
        )
    return f"sent DM to {to}"
