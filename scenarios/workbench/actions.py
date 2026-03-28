from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from conwai.actions import Action, ActionRegistry
from conwai.comm import BulletinBoard, MessageBus
from conwai.events import EventLog
from conwai.llm import tool_schema

if TYPE_CHECKING:
    from conwai.world import World

log = structlog.get_logger()


def _broadcast(entity_id: str, world: World, args: dict) -> str:
    content = args.get("content", "")
    world.get_resource(BulletinBoard).post(entity_id, content)
    world.get_resource(EventLog).log(entity_id, "broadcast", {"content": content})
    log.info("broadcast", handle=entity_id, content=content)
    return f"broadcast: {content}"


def _message(entity_id: str, world: World, args: dict) -> str:
    to = args.get("to", "").lstrip("@")
    content = args.get("content", "")
    if not to:
        return "missing 'to' field"
    err = world.get_resource(MessageBus).send(entity_id, to, content)
    if err:
        return f"message failed: {err}"
    world.get_resource(EventLog).log(
        entity_id, "message_sent", {"to": to, "content": content}
    )
    log.info("message_sent", handle=entity_id, to=to, content=content)
    return f"sent message to {to}"


_TOOL_SCHEMAS = [
    tool_schema(
        "broadcast",
        "Post a message to the shared broadcast channel. All agents will see it.",
        {
            "content": {"type": "string", "description": "The message to broadcast"},
        },
    ),
    tool_schema(
        "message",
        "Send a private message to another agent.",
        {
            "to": {
                "type": "string",
                "description": "Handle of the recipient (e.g. @Alice)",
            },
            "content": {"type": "string", "description": "The message to send"},
        },
    ),
]


def tool_definitions() -> list[dict]:
    return _TOOL_SCHEMAS


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(Action(name="broadcast", handler=_broadcast))
    registry.register(Action(name="message", handler=_message))
    return registry
