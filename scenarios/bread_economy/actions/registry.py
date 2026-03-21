from __future__ import annotations

from conwai.actions import Action, ActionRegistry
from scenarios.bread_economy.actions.communication import _post_to_board, _send_message
from scenarios.bread_economy.actions.economy import _give, _pay, make_offer_handlers
from scenarios.bread_economy.actions.personal import _inspect, _update_journal, _update_soul
from scenarios.bread_economy.actions.world import make_world_handlers


def create_registry(world=None) -> ActionRegistry:
    registry = ActionRegistry()

    _offer, _accept = make_offer_handlers()
    _submit_code, _vote = make_world_handlers(world)

    registry.register(
        Action(
            name="post_to_board",
            description="Post a message to the public bulletin board. Costs 25 coins.",
            parameters={
                "message": {"type": "string", "description": "The message to post"},
            },
            handler=_post_to_board,
        )
    )
    registry.register(
        Action(
            name="send_message",
            description="Send a private DM to another agent. LIMIT: 2 DMs per tick.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient"},
                "message": {"type": "string", "description": "The message to send"},
            },
            handler=_send_message,
        )
    )
    registry.register(
        Action(
            name="update_soul",
            description="Update your public identity. Other agents can see your soul. Costs coins.",
            parameters={
                "content": {
                    "type": "string",
                    "description": "Your new soul description",
                },
            },
            handler=_update_soul,
        )
    )
    registry.register(
        Action(
            name="update_journal",
            description="Update your private journal/memory.",
            parameters={
                "content": {
                    "type": "string",
                    "description": "Your journal content",
                },
            },
            handler=_update_journal,
        )
    )
    registry.register(
        Action(
            name="inspect",
            description="View another agent's public profile: personality, soul, coins, food, activity.",
            parameters={
                "handle": {
                    "type": "string",
                    "description": "Handle of the agent to inspect",
                },
            },
            handler=_inspect,
        )
    )
    registry.register(
        Action(
            name="pay",
            description="Pay coins to another agent.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient"},
                "amount": {
                    "type": "integer",
                    "description": "Amount of coins to pay",
                },
            },
            handler=_pay,
        )
    )
    registry.register(
        Action(
            name="give",
            description="Give flour, water, or bread to another agent.",
            parameters={
                "resource": {
                    "type": "string",
                    "description": "What to give: flour, water, or bread",
                },
                "to": {"type": "string", "description": "Handle of the recipient"},
                "amount": {
                    "type": "integer",
                    "description": "Amount to give",
                },
            },
            handler=_give,
        )
    )
    registry.register(
        Action(
            name="submit_code",
            description="Submit your answer to the cipher challenge. Correct = big coin reward. Wrong = coin penalty. Submit the decoded PLAINTEXT.",
            parameters={
                "code": {
                    "type": "string",
                    "description": "Your decoded plaintext answer",
                },
            },
            handler=_submit_code,
        )
    )
    registry.register(
        Action(
            name="vote",
            description="Vote for an agent to win the election reward. You can change your vote before the election ends. You cannot vote for yourself.",
            parameters={
                "candidate": {
                    "type": "string",
                    "description": "Handle of the agent you're voting for",
                },
            },
            handler=_vote,
        )
    )
    registry.register(
        Action(
            name="offer",
            description="Propose a trade to another agent. They must accept for the trade to happen. Offers expire after 12 ticks. Max 3 pending offers.",
            parameters={
                "to": {"type": "string", "description": "Handle of the agent to trade with"},
                "give_type": {"type": "string", "description": "What you're offering: coins, flour, water, or bread"},
                "give_amount": {"type": "integer", "description": "How much you're offering"},
                "want_type": {"type": "string", "description": "What you want in return: coins, flour, water, or bread"},
                "want_amount": {"type": "integer", "description": "How much you want"},
            },
            handler=_offer,
        )
    )
    registry.register(
        Action(
            name="accept",
            description="Accept a pending trade offer. Both sides transfer atomically.",
            parameters={
                "offer_id": {"type": "integer", "description": "The offer number to accept"},
            },
            handler=_accept,
        )
    )
    return registry
