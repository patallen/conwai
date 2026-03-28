from __future__ import annotations

from conwai.actions import Action, ActionRegistry
from conwai.llm import tool_schema
from scenarios.bread_economy.actions.communication import _post_to_board, _send_message
from scenarios.bread_economy.actions.crafting import _bake, _forage
from scenarios.bread_economy.actions.economy import (
    OfferBook,
    _give,
    _pay,
    make_offer_handlers,
)
from scenarios.bread_economy.actions.personal import (
    _inspect,
    _update_journal,
    _update_soul,
)
from scenarios.bread_economy.actions.world import make_world_handlers

# LLM tool schemas — separate from framework actions
_TOOL_SCHEMAS = [
    tool_schema(
        "forage",
        "Spend this tick foraging for raw resources. You cannot take other actions this tick. Yields vary by your role.",
    ),
    tool_schema("bake", "Bake bread from flour and water. Does not consume your tick."),
    tool_schema(
        "post_to_board",
        "Post a message to the public bulletin board. Costs 25 coins.",
        {
            "message": {"type": "string", "description": "The message to post"},
        },
    ),
    tool_schema(
        "send_message",
        "Send a private DM to another agent. LIMIT: 2 DMs per tick.",
        {
            "to": {
                "type": "string",
                "description": "Handle of the recipient (e.g. @Marcus)",
            },
            "message": {"type": "string", "description": "The message to send"},
        },
    ),
    tool_schema(
        "update_soul",
        "Update your public identity. Other agents can see your soul. Costs coins.",
        {
            "content": {"type": "string", "description": "Your new soul description"},
        },
    ),
    tool_schema(
        "update_journal",
        "Update your private journal/memory.",
        {
            "content": {"type": "string", "description": "Your journal content"},
        },
    ),
    tool_schema(
        "inspect",
        "View another agent's soul — their public self-description.",
        {
            "handle": {
                "type": "string",
                "description": "Handle of the agent to inspect (e.g. @Marcus)",
            },
        },
    ),
    tool_schema(
        "pay",
        "Pay coins to another agent.",
        {
            "to": {
                "type": "string",
                "description": "Handle of the recipient (e.g. @Marcus)",
            },
            "amount": {"type": "integer", "description": "Amount of coins to pay"},
        },
    ),
    tool_schema(
        "give",
        "Give flour, water, or bread to another agent.",
        {
            "resource": {
                "type": "string",
                "description": "What to give: flour, water, or bread",
            },
            "to": {
                "type": "string",
                "description": "Handle of the recipient (e.g. @Marcus)",
            },
            "amount": {"type": "integer", "description": "Amount to give"},
        },
    ),
    tool_schema(
        "submit_code",
        "Submit your answer to the cipher challenge. Correct = big coin reward. Wrong = coin penalty. Submit the decoded PLAINTEXT.",
        {
            "code": {"type": "string", "description": "Your decoded plaintext answer"},
        },
    ),
    tool_schema(
        "vote",
        "Vote for an agent to win the election reward. You can change your vote before the election ends. You cannot vote for yourself.",
        {
            "candidate": {
                "type": "string",
                "description": "Handle of the agent you're voting for (e.g. @Marcus)",
            },
        },
    ),
    tool_schema(
        "offer",
        "Propose a trade to another agent. They must accept for the trade to happen. Offers expire after 12 ticks. Max 3 pending offers.",
        {
            "to": {
                "type": "string",
                "description": "Handle of the agent to trade with (e.g. @Marcus)",
            },
            "give_type": {
                "type": "string",
                "description": "What you're offering: coins, flour, water, or bread",
            },
            "give_amount": {
                "type": "integer",
                "description": "How much you're offering",
            },
            "want_type": {
                "type": "string",
                "description": "What you want in return: coins, flour, water, or bread",
            },
            "want_amount": {"type": "integer", "description": "How much you want"},
        },
    ),
    tool_schema(
        "accept",
        "Accept a pending trade offer. Both sides transfer atomically.",
        {
            "offer_id": {
                "type": "integer",
                "description": "The offer number to accept",
            },
        },
    ),
]


def tool_definitions() -> list[dict]:
    return _TOOL_SCHEMAS


def create_registry(world=None, offer_book: OfferBook | None = None) -> ActionRegistry:
    registry = ActionRegistry()

    if offer_book is None:
        offer_book = OfferBook()
    _offer, _accept = make_offer_handlers(offer_book)
    _submit_code, _vote = make_world_handlers(world)

    for name, handler in [
        ("forage", _forage),
        ("bake", _bake),
        ("post_to_board", _post_to_board),
        ("send_message", _send_message),
        ("update_soul", _update_soul),
        ("update_journal", _update_journal),
        ("inspect", _inspect),
        ("pay", _pay),
        ("give", _give),
        ("submit_code", _submit_code),
        ("vote", _vote),
        ("offer", _offer),
        ("accept", _accept),
    ]:
        registry.register(Action(name=name, handler=handler))

    return registry
