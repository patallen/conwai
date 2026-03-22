from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.actions import Action, ActionRegistry
from conwai.bulletin_board import BulletinBoard
from conwai.events import EventLog
from conwai.messages import MessageBus

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


def _broadcast(entity_id: str, world: World, args: dict) -> str:
    content = args.get("content", "")
    world.get_resource(BulletinBoard).post(entity_id, content)
    world.get_resource(EventLog).log(entity_id, "broadcast", {"content": content})
    log.info(f"[{entity_id}] broadcast: {content}")
    return f"broadcast: {content}"


def _message(entity_id: str, world: World, args: dict) -> str:
    to = args.get("to", "").lstrip("@")
    content = args.get("content", "")
    if not to:
        return "missing 'to' field"
    err = world.get_resource(MessageBus).send(entity_id, to, content)
    if err:
        return f"message failed: {err}"
    world.get_resource(EventLog).log(entity_id, "message_sent", {"to": to, "content": content})
    log.info(f"[{entity_id}] -> [{to}]: {content}")
    return f"sent message to {to}"


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(
        Action(
            name="broadcast",
            description="Post a message to the shared broadcast channel. All agents will see it.",
            parameters={
                "content": {"type": "string", "description": "The message to broadcast"},
            },
            handler=_broadcast,
        )
    )
    registry.register(
        Action(
            name="message",
            description="Send a private message to another agent.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient (e.g. @Alice)"},
                "content": {"type": "string", "description": "The message to send"},
            },
            handler=_message,
        )
    )
    return registry
