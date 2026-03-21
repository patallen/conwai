from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

import scenarios.bread_economy.config as config
from conwai.actions import Action, ActionRegistry

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


def _capped_add(inv: dict, resource: str, amount: int) -> int:
    """Add to inventory respecting cap. Returns actual amount added."""
    cap = config.INVENTORY_CAP
    actual = min(amount, max(0, cap - inv.get(resource, 0)))
    inv[resource] = inv.get(resource, 0) + actual
    return actual


def charge(store, handle: str, amount: int, reason: str) -> str | None:
    """Deduct coins. Returns error string if insufficient, None on success."""
    eco = store.get(handle, "economy")
    if amount > eco["coins"]:
        return f"not enough coins for {reason} ({amount} needed, have {int(eco['coins'])})"
    eco["coins"] -= amount
    store.set(handle, "economy", eco)
    return None


def _post_to_board(agent: Agent, ctx: TickContext, args: dict) -> str:
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
                other_eco["coins"] += config.ENERGY_GAIN["referenced"]
                ctx.store.set(a.handle, "economy", other_eco)
                if ctx.perception:
                    ctx.perception.notify(
                        a.handle,
                        f"+{config.ENERGY_GAIN['referenced']} coins (referenced on board)",
                    )
    return f"posted to board: {content}"


def _send_message(agent: Agent, ctx: TickContext, args: dict) -> str:
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
            rec_eco["coins"] += config.ENERGY_GAIN["dm_received"]
            ctx.store.set(to, "economy", rec_eco)
            if ctx.perception:
                ctx.perception.notify(
                    to,
                    f"+{config.ENERGY_GAIN['dm_received']} coins (received DM)",
                )
    return f"sent DM to {to}"


def _wait(agent: Agent, ctx: TickContext, args: dict) -> str:
    ctx.events.log(agent.handle, "wait", {})
    log.info(f"[{agent.handle}] waiting")
    return "waiting"


def _update_soul(agent: Agent, ctx: TickContext, args: dict) -> str:
    cost = config.ENERGY_COST_FLAT.get("update_soul", 5)
    if cost > 0:
        err = charge(ctx.store, agent.handle, cost, "update_soul")
        if err:
            return err
    content = args.get("content", "")
    mem = ctx.store.get(agent.handle, "memory")
    mem["soul"] = content
    ctx.store.set(agent.handle, "memory", mem)
    ctx.events.log(agent.handle, "soul_updated", {"content": content})
    log.info(f"[{agent.handle}] soul updated")
    return "soul updated"


def _update_journal(agent: Agent, ctx: TickContext, args: dict) -> str:
    content = args.get("content", "")
    mem = ctx.store.get(agent.handle, "memory")
    max_len = config.MEMORY_MAX
    lost = 0
    if len(content) > max_len:
        lost = len(content) - max_len
        content = content[:max_len]
    mem["memory"] = content
    ctx.store.set(agent.handle, "memory", mem)
    ctx.events.log(agent.handle, "journal_updated", {"chars": len(content)})
    log.info(f"[{agent.handle}] journal updated")
    if lost > 0:
        return f"journal updated ({lost} chars truncated)"
    return "journal updated"


def _inspect(agent: Agent, ctx: TickContext, args: dict) -> str:
    handle = args.get("handle", "")
    if not ctx.pool:
        return "inspection unavailable"
    other = ctx.pool.by_handle(handle)
    if not other:
        log.info(f"[{agent.handle}] inspect failed: unknown agent {handle}")
        return f"unknown agent: {handle}"
    eco = ctx.store.get(handle, "economy")
    inv = ctx.store.get(handle, "inventory")
    hun = ctx.store.get(handle, "hunger")
    posts = ctx.events.count_by_entity_type(handle, "board_post")
    dms = ctx.events.count_by_entity_type(handle, "dm_sent")
    role_labels = {
        "flour_forager": "flour forager",
        "water_forager": "water forager",
        "baker": "baker",
    }
    other_info = ctx.store.get(handle, "agent_info")
    mem = ctx.store.get(handle, "memory")
    lines = [
        f"Handle: {handle}",
        f"Role: {role_labels.get(other_info['role'], other_info['role'])}",
        f"Personality: {other_info['personality']}",
        f"Coins: {int(eco['coins'])}",
        f"Hunger: {hun['hunger']}/100, Thirst: {hun['thirst']}/100",
        f"Flour: {inv['flour']}, Water: {inv['water']}, Bread: {inv['bread']}",
    ]
    soul = mem.get("soul", "")
    if soul:
        lines.append(f"Soul: {soul[:200]}")
    lines.append(f"Activity: {posts} posts, {dms} DMs sent")
    ctx.events.log(agent.handle, "inspect", {"target": handle})
    log.info(f"[{agent.handle}] inspected {handle}")
    return f"Inspect {handle}:\n" + "\n".join(lines)


def _pay(agent: Agent, ctx: TickContext, args: dict) -> str:
    to = args.get("to", "")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "invalid amount"
    if amount <= 0:
        return "amount must be positive"
    eco = ctx.store.get(agent.handle, "economy")
    if amount > eco["coins"]:
        return f"not enough coins to pay {amount} (have {int(eco['coins'])})"
    if not ctx.pool:
        return "payment unavailable"
    other = ctx.pool.by_handle(to)
    if not other:
        return f"unknown agent: {to}"
    if to == agent.handle:
        return "cannot pay yourself"
    eco["coins"] -= amount
    ctx.store.set(agent.handle, "economy", eco)
    other_eco = ctx.store.get(to, "economy")
    other_eco["coins"] += amount
    ctx.store.set(to, "economy", other_eco)
    if ctx.perception:
        ctx.perception.notify(agent.handle, f"-{amount} coins (paid to {to})")
        ctx.perception.notify(to, f"+{amount} coins (payment from {agent.handle})")
    ctx.events.log(agent.handle, "payment", {"to": to, "amount": amount})
    log.info(f"[{agent.handle}] paid {amount} coins to {to}")
    return f"paid {amount} coins to {to}"


def _forage(agent: Agent, ctx: TickContext, args: dict) -> str:
    info = ctx.store.get(agent.handle, "agent_info")
    skills = config.FORAGE_SKILL_BY_ROLE.get(info["role"], {"flour": 1, "water": 1})

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
    flour_needed = config.BAKE_COST["flour"]
    water_needed = config.BAKE_COST["water"]
    inv = ctx.store.get(agent.handle, "inventory")
    if inv["flour"] < flour_needed or inv["water"] < water_needed:
        return f"need {flour_needed} flour and {water_needed} water to bake (have {inv['flour']} flour, {inv['water']} water)"
    info = ctx.store.get(agent.handle, "agent_info")
    bread_yield = config.BAKE_BAKER_YIELD if info["role"] == "baker" else config.BAKE_YIELD
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


def _give(agent: Agent, ctx: TickContext, args: dict) -> str:
    resource = args.get("resource", "")
    to = args.get("to", "")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "invalid amount"
    if amount <= 0:
        return "amount must be positive"
    if resource not in ("flour", "water", "bread"):
        return f"invalid resource: {resource}. Must be flour, water, or bread."
    inv = ctx.store.get(agent.handle, "inventory")
    if amount > inv[resource]:
        return f"not enough {resource} to give {amount} (have {inv[resource]})"
    if not ctx.pool:
        return "giving unavailable"
    other = ctx.pool.by_handle(to)
    if not other:
        return f"unknown agent: {to}"
    if to == agent.handle:
        return "cannot give to yourself"
    inv[resource] -= amount
    ctx.store.set(agent.handle, "inventory", inv)
    other_inv = ctx.store.get(to, "inventory")
    _capped_add(other_inv, resource, amount)
    ctx.store.set(to, "inventory", other_inv)
    if ctx.perception:
        ctx.perception.notify(to, f"received {amount} {resource} from {agent.handle}")
    ctx.events.log(
        agent.handle, "give", {"to": to, "resource": resource, "amount": amount}
    )
    log.info(f"[{agent.handle}] gave {amount} {resource} to {to}")
    return f"gave {amount} {resource} to {to}"


_next_offer_id = 1
_pending_offers: dict[int, dict] = {}  # offer_id -> {from, to, give_type, give_amount, want_type, want_amount, tick}
OFFER_EXPIRY = 12
VALID_RESOURCES = ("coins", "flour", "water", "bread")


def _expire_offers(tick: int) -> None:
    expired = [oid for oid, o in _pending_offers.items() if tick - o["tick"] >= OFFER_EXPIRY]
    for oid in expired:
        del _pending_offers[oid]


def _offer(agent: Agent, ctx: TickContext, args: dict) -> str:
    global _next_offer_id
    _expire_offers(ctx.tick)

    to = args.get("to", "")
    give_type = args.get("give_type", "")
    give_amount = int(args.get("give_amount", 0))
    want_type = args.get("want_type", "")
    want_amount = int(args.get("want_amount", 0))

    if not to or not give_type or not want_type:
        return "missing fields: to, give_type, give_amount, want_type, want_amount"
    if give_type not in VALID_RESOURCES or want_type not in VALID_RESOURCES:
        return f"invalid resource. Must be one of: {', '.join(VALID_RESOURCES)}"
    if give_amount <= 0 or want_amount <= 0:
        return "amounts must be positive"
    if to == agent.handle:
        return "cannot trade with yourself"
    if not ctx.pool or not ctx.pool.by_handle(to):
        return f"unknown agent: {to}"

    # Check the offerer actually has the resources
    if give_type == "coins":
        eco = ctx.store.get(agent.handle, "economy")
        if give_amount > eco["coins"]:
            return f"not enough coins (have {int(eco['coins'])})"
    else:
        inv = ctx.store.get(agent.handle, "inventory")
        if give_amount > inv.get(give_type, 0):
            return f"not enough {give_type} (have {inv.get(give_type, 0)})"

    # Max 3 pending offers per agent
    my_offers = [o for o in _pending_offers.values() if o["from"] == agent.handle]
    if len(my_offers) >= 3:
        return "you already have 3 pending offers. Wait for them to be accepted or expire."

    oid = _next_offer_id
    _next_offer_id += 1
    _pending_offers[oid] = {
        "from": agent.handle, "to": to,
        "give_type": give_type, "give_amount": give_amount,
        "want_type": want_type, "want_amount": want_amount,
        "tick": ctx.tick,
    }

    if ctx.perception:
        ctx.perception.notify(
            to,
            f"Trade offer #{oid} from {agent.handle}: {give_amount} {give_type} for {want_amount} {want_type}. Use accept(offer_id={oid}) to accept.",
        )

    ctx.events.log(agent.handle, "offer", {
        "id": oid, "to": to, "give_type": give_type, "give_amount": give_amount,
        "want_type": want_type, "want_amount": want_amount,
    })
    log.info(f"[{agent.handle}] offer #{oid} to {to}: {give_amount} {give_type} for {want_amount} {want_type}")
    return f"Offer #{oid} sent to {to}: {give_amount} {give_type} for {want_amount} {want_type}. Expires in {OFFER_EXPIRY} ticks."


def _accept(agent: Agent, ctx: TickContext, args: dict) -> str:
    _expire_offers(ctx.tick)

    oid = int(args.get("offer_id", 0))
    offer = _pending_offers.get(oid)
    if not offer:
        return f"Offer #{oid} not found or expired."
    if offer["to"] != agent.handle:
        return f"Offer #{oid} is not for you."

    offerer = offer["from"]
    give_type = offer["give_type"]
    give_amount = offer["give_amount"]
    want_type = offer["want_type"]
    want_amount = offer["want_amount"]

    # Verify offerer still has resources
    if give_type == "coins":
        off_eco = ctx.store.get(offerer, "economy")
        if give_amount > off_eco["coins"]:
            del _pending_offers[oid]
            return f"Offer #{oid} failed: {offerer} no longer has enough {give_type}."
    else:
        off_inv = ctx.store.get(offerer, "inventory")
        if give_amount > off_inv.get(give_type, 0):
            del _pending_offers[oid]
            return f"Offer #{oid} failed: {offerer} no longer has enough {give_type}."

    # Verify accepter has the wanted resources
    if want_type == "coins":
        acc_eco = ctx.store.get(agent.handle, "economy")
        if want_amount > acc_eco["coins"]:
            return f"You don't have enough coins (have {int(acc_eco['coins'])}, need {want_amount})."
    else:
        acc_inv = ctx.store.get(agent.handle, "inventory")
        if want_amount > acc_inv.get(want_type, 0):
            return f"You don't have enough {want_type} (have {acc_inv.get(want_type, 0)}, need {want_amount})."

    # Execute the swap atomically
    # Offerer gives give_type, accepter receives it
    if give_type == "coins":
        off_eco = ctx.store.get(offerer, "economy")
        off_eco["coins"] -= give_amount
        ctx.store.set(offerer, "economy", off_eco)
        acc_eco = ctx.store.get(agent.handle, "economy")
        acc_eco["coins"] += give_amount
        ctx.store.set(agent.handle, "economy", acc_eco)
    else:
        off_inv = ctx.store.get(offerer, "inventory")
        off_inv[give_type] -= give_amount
        ctx.store.set(offerer, "inventory", off_inv)
        acc_inv = ctx.store.get(agent.handle, "inventory")
        _capped_add(acc_inv, give_type, give_amount)
        ctx.store.set(agent.handle, "inventory", acc_inv)

    # Accepter gives want_type, offerer receives it
    if want_type == "coins":
        acc_eco = ctx.store.get(agent.handle, "economy")
        acc_eco["coins"] -= want_amount
        ctx.store.set(agent.handle, "economy", acc_eco)
        off_eco = ctx.store.get(offerer, "economy")
        off_eco["coins"] += want_amount
        ctx.store.set(offerer, "economy", off_eco)
    else:
        acc_inv = ctx.store.get(agent.handle, "inventory")
        acc_inv[want_type] -= want_amount
        ctx.store.set(agent.handle, "inventory", acc_inv)
        off_inv = ctx.store.get(offerer, "inventory")
        _capped_add(off_inv, want_type, want_amount)
        ctx.store.set(offerer, "inventory", off_inv)

    del _pending_offers[oid]

    if ctx.perception:
        ctx.perception.notify(offerer, f"Offer #{oid} accepted by {agent.handle}: gave {give_amount} {give_type}, received {want_amount} {want_type}")
        ctx.perception.notify(agent.handle, f"Accepted offer #{oid} from {offerer}: received {give_amount} {give_type}, gave {want_amount} {want_type}")

    ctx.events.log(agent.handle, "trade", {
        "id": oid, "with": offerer,
        "received_type": give_type, "received_amount": give_amount,
        "gave_type": want_type, "gave_amount": want_amount,
    })
    ctx.events.log(offerer, "trade", {
        "id": oid, "with": agent.handle,
        "received_type": want_type, "received_amount": want_amount,
        "gave_type": give_type, "gave_amount": give_amount,
    })
    log.info(f"[TRADE] #{oid}: {offerer} gave {give_amount} {give_type}, {agent.handle} gave {want_amount} {want_type}")
    return f"Trade complete: received {give_amount} {give_type} from {offerer}, gave {want_amount} {want_type}."


def create_registry(world=None) -> ActionRegistry:
    registry = ActionRegistry()

    def _submit_code(agent: Agent, ctx: TickContext, args: dict) -> str:
        if world is None:
            return "No active code challenge."
        guess = args.get("code", "")
        return world.submit_code(agent, guess)

    def _vote(agent: Agent, ctx: TickContext, args: dict) -> str:
        if world is None:
            return "No active election."
        candidate = args.get("candidate", "")
        return world.cast_vote(agent, candidate)

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
