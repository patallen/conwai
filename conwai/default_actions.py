from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from conwai.actions import Action, ActionRegistry
import conwai.config as config

if TYPE_CHECKING:
    from conwai.agent import Agent

log = logging.getLogger("conwai")


def _post_to_board(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    content = args.get("message", "")
    recent = registry.board.recent_by_handle(agent.handle, n=10)
    if any(p.content == content for p in recent):
        eco = registry.store.get(agent.handle, "economy")
        penalty = 50
        eco["coins"] = max(0, eco["coins"] - penalty)
        registry.store.set(agent.handle, "economy", eco)
        log.info(f"[{agent.handle}] DUPLICATE POST penalty: -{penalty}")
        return f"duplicate post penalty: -{penalty} coins"
    registry.board.post(agent.handle, content)
    registry.events.log(agent.handle, "board_post", {"content": content})
    log.info(f"[{agent.handle}] posted: {content}")
    if registry.pool:
        for a in registry.pool.alive():
            if a.handle != agent.handle and a.handle in content:
                other_eco = registry.store.get(a.handle, "economy")
                other_eco["coins"] += config.ENERGY_GAIN["referenced"]
                registry.store.set(a.handle, "economy", other_eco)
                if registry.perception:
                    registry.perception.notify(
                        a.handle,
                        f"+{config.ENERGY_GAIN['referenced']} coins (referenced on board)",
                    )
    return f"posted to board: {content}"


def _send_message(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    to = args.get("to", "")
    message = args.get("message", "")
    if not to:
        return "missing 'to' field"
    tick_data = registry.tick_state.get(agent.handle, {})
    dm_sent = tick_data.get("dm_sent", 0)
    if dm_sent >= 2:
        return "you already sent 2 DMs this tick. Wait until next tick."
    err = registry.bus.send(agent.handle, to, message)
    if err:
        log.info(f"[{agent.handle}] SEND FAILED: {err}")
        return f"DM failed: {err}"
    tick_data["dm_sent"] = dm_sent + 1
    registry.tick_state[agent.handle] = tick_data
    registry.events.log(agent.handle, "dm_sent", {"to": to, "content": message})
    log.info(f"[{agent.handle}] -> [{to}]: {message}")
    if registry.pool:
        recipient = registry.pool.by_handle(to)
        if recipient:
            rec_eco = registry.store.get(to, "economy")
            rec_eco["coins"] += config.ENERGY_GAIN["dm_received"]
            registry.store.set(to, "economy", rec_eco)
            if registry.perception:
                registry.perception.notify(
                    to,
                    f"+{config.ENERGY_GAIN['dm_received']} coins (received DM)",
                )
    return f"sent DM to {to}"


def _wait(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    registry.events.log(agent.handle, "wait", {})
    log.info(f"[{agent.handle}] waiting")
    return "waiting"


def _update_soul(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    content = args.get("content", "")
    mem = registry.store.get(agent.handle, "memory")
    mem["soul"] = content
    registry.store.set(agent.handle, "memory", mem)
    registry.events.log(agent.handle, "soul_updated", {"content": content})
    log.info(f"[{agent.handle}] soul updated")
    return "soul updated"


def _update_journal(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    content = args.get("content", "")
    mem = registry.store.get(agent.handle, "memory")
    max_len = config.MEMORY_MAX
    lost = 0
    if len(content) > max_len:
        lost = len(content) - max_len
        content = content[:max_len]
    mem["memory"] = content
    registry.store.set(agent.handle, "memory", mem)
    registry.events.log(agent.handle, "journal_updated", {"chars": len(content)})
    log.info(f"[{agent.handle}] journal updated")
    if lost > 0:
        return f"journal updated ({lost} chars truncated)"
    return "journal updated"


def _inspect(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    handle = args.get("handle", "")
    if not registry.pool:
        return "inspection unavailable"
    other = registry.pool.by_handle(handle)
    if not other:
        log.info(f"[{agent.handle}] inspect failed: unknown agent {handle}")
        return f"unknown agent: {handle}"
    eco = registry.store.get(handle, "economy")
    inv = registry.store.get(handle, "inventory")
    hun = registry.store.get(handle, "hunger")
    posts = registry.events.count_by_entity_type(handle, "board_post")
    dms = registry.events.count_by_entity_type(handle, "dm_sent")
    role_labels = {
        "flour_forager": "flour forager",
        "water_forager": "water forager",
        "baker": "baker",
    }
    mem = registry.store.get(handle, "memory")
    lines = [
        f"Handle: {handle}",
        f"Role: {role_labels.get(other.role, other.role)}",
        f"Personality: {other.personality}",
        f"Coins: {int(eco['coins'])}",
        f"Hunger: {hun['hunger']}/100, Thirst: {hun['thirst']}/100",
        f"Flour: {inv['flour']}, Water: {inv['water']}, Bread: {inv['bread']}",
    ]
    soul = mem.get("soul", "")
    if soul:
        lines.append(f"Soul: {soul[:200]}")
    lines.append(f"Activity: {posts} posts, {dms} DMs sent")
    registry.events.log(agent.handle, "inspect", {"target": handle})
    log.info(f"[{agent.handle}] inspected {handle}")
    return f"Inspect {handle}:\n" + "\n".join(lines)


def _pay(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    to = args.get("to", "")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "invalid amount"
    if amount <= 0:
        return "amount must be positive"
    eco = registry.store.get(agent.handle, "economy")
    if amount > eco["coins"]:
        return f"not enough coins to pay {amount} (have {int(eco['coins'])})"
    if not registry.pool:
        return "payment unavailable"
    other = registry.pool.by_handle(to)
    if not other:
        return f"unknown agent: {to}"
    if to == agent.handle:
        return "cannot pay yourself"
    eco["coins"] -= amount
    registry.store.set(agent.handle, "economy", eco)
    other_eco = registry.store.get(to, "economy")
    other_eco["coins"] += amount
    registry.store.set(to, "economy", other_eco)
    if registry.perception:
        registry.perception.notify(agent.handle, f"-{amount} coins (paid to {to})")
        registry.perception.notify(to, f"+{amount} coins (payment from {agent.handle})")
    registry.events.log(agent.handle, "payment", {"to": to, "amount": amount})
    log.info(f"[{agent.handle}] paid {amount} coins to {to}")
    return f"paid {amount} coins to {to}"


def _forage(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    skills = config.FORAGE_SKILL_BY_ROLE.get(agent.role, {"flour": 1, "water": 1})

    # Streak bonus: consecutive forages increase yield
    forage_data = registry.store.get(agent.handle, "forage")
    last_tick = forage_data.get("last_tick", 0)
    current_tick = getattr(registry, "current_tick", 0)
    # Streak continues if last forage was the previous tick
    if last_tick > 0 and current_tick - last_tick == 1:
        streak = forage_data.get("streak", 0)
    else:
        streak = 0
    multiplier = 1.0 + streak * 0.5  # 1x, 1.5x, 2x, 2.5x, 3x cap
    multiplier = min(multiplier, 3.0)

    flour = int(random.randint(0, skills["flour"]) * multiplier)
    water = int(random.randint(0, skills["water"]) * multiplier)
    inv = registry.store.get(agent.handle, "inventory")
    inv["flour"] += flour
    inv["water"] += water
    registry.store.set(agent.handle, "inventory", inv)

    # Update streak
    forage_data["streak"] = streak + 1
    forage_data["last_tick"] = current_tick
    registry.store.set(agent.handle, "forage", forage_data)

    tick_data = registry.tick_state.get(agent.handle, {})
    tick_data["foraging"] = True
    registry.tick_state[agent.handle] = tick_data
    registry.events.log(agent.handle, "forage", {"flour": flour, "water": water, "streak": streak + 1, "multiplier": multiplier})
    log.info(f"[{agent.handle}] foraged {flour} flour, {water} water (streak {streak + 1}, {multiplier}x)")
    parts = []
    if flour > 0:
        parts.append(f"{flour} flour")
    if water > 0:
        parts.append(f"{water} water")
    streak_msg = f" (streak {streak + 1}, {multiplier}x bonus)" if streak > 0 else ""
    if parts:
        return f"foraged {', '.join(parts)}{streak_msg}. Foraging takes your full attention — no other actions this tick."
    return f"foraged but found nothing{streak_msg}. Foraging takes your full attention — no other actions this tick."


def _bake(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    flour_needed = config.BAKE_COST["flour"]
    water_needed = config.BAKE_COST["water"]
    inv = registry.store.get(agent.handle, "inventory")
    if inv["flour"] < flour_needed or inv["water"] < water_needed:
        return f"need {flour_needed} flour and {water_needed} water to bake (have {inv['flour']} flour, {inv['water']} water)"
    bread_yield = config.BAKE_BAKER_YIELD if agent.role == "baker" else config.BAKE_YIELD
    inv["flour"] -= flour_needed
    inv["water"] -= water_needed
    inv["bread"] += bread_yield
    registry.store.set(agent.handle, "inventory", inv)
    registry.events.log(
        agent.handle,
        "bake",
        {"bread": bread_yield, "flour": inv["flour"], "water": inv["water"]},
    )
    log.info(f"[{agent.handle}] baked {bread_yield} bread")
    return f"baked {bread_yield} bread (flour: {inv['flour']}, water: {inv['water']}, bread: {inv['bread']})"


def _give(agent: Agent, registry: ActionRegistry, args: dict) -> str:
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
    inv = registry.store.get(agent.handle, "inventory")
    if amount > inv[resource]:
        return f"not enough {resource} to give {amount} (have {inv[resource]})"
    if not registry.pool:
        return "giving unavailable"
    other = registry.pool.by_handle(to)
    if not other:
        return f"unknown agent: {to}"
    if to == agent.handle:
        return "cannot give to yourself"
    inv[resource] -= amount
    registry.store.set(agent.handle, "inventory", inv)
    other_inv = registry.store.get(to, "inventory")
    other_inv[resource] += amount
    registry.store.set(to, "inventory", other_inv)
    if registry.perception:
        registry.perception.notify(to, f"received {amount} {resource} from {agent.handle}")
    registry.events.log(
        agent.handle, "give", {"to": to, "resource": resource, "amount": amount}
    )
    log.info(f"[{agent.handle}] gave {amount} {resource} to {to}")
    return f"gave {amount} {resource} to {to}"


def _submit_code(agent: Agent, registry: ActionRegistry, args: dict) -> str:
    if registry.world is None:
        return "No active code challenge."
    guess = args.get("code", "")
    return registry.world.submit_code(agent, guess)


def create_registry(
    store,
    board,
    bus,
    events,
    pool=None,
    perception=None,
    tick_state=None,
    world=None,
) -> ActionRegistry:
    registry = ActionRegistry(
        store=store,
        board=board,
        bus=bus,
        events=events,
        pool=pool,
        perception=perception,
        world=world,
    )
    if tick_state is not None:
        registry.tick_state = tick_state
    registry.register(
        Action(
            name="post_to_board",
            description="Post a message to the public bulletin board. Costs 25 coins.",
            parameters={
                "message": {"type": "string", "description": "The message to post"},
            },
            cost_flat=25,
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
            cost_flat=0,
            handler=_send_message,
        )
    )
    registry.register(
        Action(
            name="wait",
            description="Do nothing this tick.",
            parameters={},
            cost_flat=0,
            handler=_wait,
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
            cost_flat=config.ENERGY_COST_FLAT.get("update_soul", 5),
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
            cost_flat=0,
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
            cost_flat=0,
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
            cost_flat=0,
            handler=_pay,
        )
    )
    registry.register(
        Action(
            name="forage",
            description="Spend this tick searching for flour and water. Yield depends on your role. Consecutive forages build a streak bonus (up to 3x yield). Doing anything else resets the streak. THIS TAKES YOUR ENTIRE TICK.",
            parameters={},
            cost_flat=0,
            handler=_forage,
        )
    )
    registry.register(
        Action(
            name="bake",
            description=f"Turn {config.BAKE_COST['flour']} flour + {config.BAKE_COST['water']} water into bread. Bakers produce {config.BAKE_BAKER_YIELD}, others produce {config.BAKE_YIELD}.",
            parameters={},
            cost_flat=0,
            handler=_bake,
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
            cost_flat=0,
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
            cost_flat=0,
            handler=_submit_code,
        )
    )
    return registry
