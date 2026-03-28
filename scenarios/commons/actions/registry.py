"""Action registry and LLM tool schemas for the commons scenario."""

from __future__ import annotations

from conwai.actions import Action, ActionRegistry
from conwai.llm import tool_schema
from scenarios.commons.actions.communication import _post_to_board, _send_message
from scenarios.commons.actions.fishing import _fish, _rest

_TOOL_SCHEMAS = [
    tool_schema(
        "fish",
        "Spend this tick fishing from the shared pond. You choose how many to catch. "
        "You cannot take other actions this tick.",
        {
            "amount": {
                "type": "integer",
                "description": "Number of fish to catch (0-100)",
            },
        },
    ),
    tool_schema(
        "rest",
        "Do nothing this tick. Take no fish.",
    ),
    tool_schema(
        "post_to_board",
        "Post a message to the public bulletin board. All agents can see it.",
        {
            "message": {
                "type": "string",
                "description": "The message to post (max 200 chars)",
            },
        },
    ),
    tool_schema(
        "send_message",
        "Send a private message to another agent.",
        {
            "to": {
                "type": "string",
                "description": "Handle of the recipient (e.g. @Marcus)",
            },
            "message": {"type": "string", "description": "The message to send"},
        },
    ),
]


def tool_definitions() -> list[dict]:
    return _TOOL_SCHEMAS


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    for name, handler in [
        ("fish", _fish),
        ("rest", _rest),
        ("post_to_board", _post_to_board),
        ("send_message", _send_message),
    ]:
        registry.register(Action(name=name, handler=handler))
    return registry
