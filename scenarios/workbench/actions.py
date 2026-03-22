from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.actions import Action, ActionRegistry

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


def _broadcast(agent: Agent, ctx: TickContext, args: dict) -> str:
    content = args.get("content", "")
    ctx.board.post(agent.handle, content)
    ctx.events.log(agent.handle, "broadcast", {"content": content})
    log.info(f"[{agent.handle}] broadcast: {content}")
    return f"broadcast: {content}"


def _message(agent: Agent, ctx: TickContext, args: dict) -> str:
    to = args.get("to", "").lstrip("@")
    content = args.get("content", "")
    if not to:
        return "missing 'to' field"
    err = ctx.bus.send(agent.handle, to, content)
    if err:
        return f"message failed: {err}"
    ctx.events.log(agent.handle, "message_sent", {"to": to, "content": content})
    log.info(f"[{agent.handle}] -> [{to}]: {content}")
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
