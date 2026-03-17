import logging
import random

from conwai.actions import Action, ActionRegistry

log = logging.getLogger("conwai")
from conwai.config import (
    ENERGY_COST_FLAT,
    ENERGY_COST_PER_WORD,
    ENERGY_GAIN,
    ENERGY_MAX,
)


def _post_to_board(agent, ctx, args):
    content = args.get("message", "")
    recent = [p for p in ctx.board._posts[-10:] if p.handle == agent.handle]
    if any(p.content == content for p in recent):
        penalty = 50
        agent.coins = max(0, agent.coins - penalty)
        agent._action_log.append(f"duplicate post penalty: -{penalty} coins")
        log.info(f"[{agent.handle}] DUPLICATE POST penalty: -{penalty}")
        return
    ctx.board.post(agent.handle, content)
    ctx.log(agent.handle, "board_post", {"content": content})
    log.info(f"[{agent.handle}] posted: {content}")
    for h, a in ctx.agent_map.items():
        if h != agent.handle and h in content:
            a.gain_coins("referenced on board", ENERGY_GAIN["referenced"])


def _send_message(agent, ctx, args):
    to = args.get("to", "")
    message = args.get("message", "")
    if not to:
        return
    if agent._dm_sent_this_tick:
        agent._action_log.append("You already sent a DM this tick. You can only send 1 DM per tick. Wait until next tick.")
        return
    err = ctx.bus.send(agent.handle, to, message)
    if err:
        agent._action_log.append(f"DM failed: {err}")
        log.info(f"[{agent.handle}] SEND FAILED: {err}")
    else:
        agent._dm_sent_this_tick = True
        agent.record_dm(ctx.tick, f"you → {to}: {message}")
        ctx.log(agent.handle, "dm_sent", {"to": to, "content": message})
        log.info(f"[{agent.handle}] -> [{to}]: {message}")
        if to in ctx.agent_map:
            ctx.agent_map[to].gain_coins("received DM", ENERGY_GAIN["dm_received"])


def _wait(agent, ctx, args):
    log.info(f"[{agent.handle}] waiting")


def _sleep(agent, ctx, args):
    if agent.coins > ENERGY_MAX // 2:
        agent._action_log.append(
            f"cannot sleep — too many coins ({int(agent.coins)})"
        )
        log.info(f"[{agent.handle}] CANNOT SLEEP — energy above 50%")
        return
    ticks = args.get("ticks", 5)
    try:
        ticks = int(ticks)
    except (ValueError, TypeError):
        ticks = 5
    agent.sleep(ticks)
    ctx.log(agent.handle, "sleep", {"ticks": ticks})
    log.info(f"[{agent.handle}] sleeping for {ticks} ticks")


def _update_soul(agent, ctx, args):
    content = args.get("content", "")
    agent.soul = content
    ctx.log(agent.handle, "soul_updated", {"content": content})
    log.info(f"[{agent.handle}] soul updated")


def _update_journal(agent, ctx, args):
    content = args.get("content", "")
    lost = agent.write_memory(content)
    if lost > 0:
        agent._action_log.append(f"journal full — {lost} chars lost from the end")
    log.info(f"[{agent.handle}] journal updated")


def _inspect(agent, ctx, args):
    handle = args.get("handle", "")
    other = ctx.agent_map.get(handle)
    if not other:
        log.info(f"[{agent.handle}] inspect failed: unknown agent {handle}")
        return
    posts = ctx.events.count_by_entity_type(handle, "board_post")
    dms = ctx.events.count_by_entity_type(handle, "dm_sent")
    forage_labels = {1: "poor", 2: "below average", 3: "decent", 4: "excellent"}
    lines = [
        f"Handle: {handle}",
        f"Personality: {other.personality}",
        f"Coins: {int(other.coins)}",
        f"Hunger: {other.hunger}/100",
        f"Food inventory: {other.food}",
        f"Foraging ability: {forage_labels.get(other.forage_skill, 'unknown')}",
    ]
    soul = other.soul
    if soul:
        lines.append(f"Soul: {soul[:200]}")
    lines.append(f"Activity: {posts} posts, {dms} DMs sent")
    agent._action_log.append(f"Inspect {handle}:\n" + "\n".join(lines))
    ctx.log(agent.handle, "inspect", {"target": handle})
    log.info(f"[{agent.handle}] inspected {handle}")


def _pay(agent, ctx, args):
    to = args.get("to", "")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        agent._action_log.append("invalid amount")
        return
    if amount <= 0:
        agent._action_log.append("amount must be positive")
        return
    if amount > agent.coins:
        agent._action_log.append(
            f"not enough coins to pay {amount} (have {int(agent.coins)})"
        )
        return
    other = ctx.agent_map.get(to)
    if not other:
        agent._action_log.append(f"unknown agent: {to}")
        return
    if to == agent.handle:
        agent._action_log.append("cannot pay yourself")
        return
    agent.coins -= amount
    other.gain_coins(f"payment from {agent.handle}", amount)
    agent._energy_log.append(f"coins -{amount} (paid to {to})")
    agent.record_ledger(ctx.tick, f"paid {amount} coins to {to}")
    other.record_ledger(ctx.tick, f"received {amount} coins from {agent.handle}")
    ctx.log(agent.handle, "payment", {"to": to, "amount": amount})
    log.info(f"[{agent.handle}] paid {amount} coins to {to}")


def _forage(agent, ctx, args):
    amount = random.randint(0, agent.forage_skill)
    agent.food += amount
    if amount == 0:
        agent._action_log.append("foraged but found nothing. Foraging takes your full attention — no other actions this tick.")
    else:
        agent._action_log.append(f"foraged {amount} food (inventory now {agent.food}). Foraging takes your full attention — no other actions this tick.")
    agent._foraging = True
    ctx.log(agent.handle, "forage", {"amount": amount, "food": agent.food})
    log.info(f"[{agent.handle}] foraged {amount} food (inventory: {agent.food})")


def _give_food(agent, ctx, args):
    to = args.get("to", "")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        agent._action_log.append("invalid amount")
        return
    if amount <= 0:
        agent._action_log.append("amount must be positive")
        return
    if amount > agent.food:
        agent._action_log.append(f"not enough food to give {amount} (have {agent.food})")
        return
    other = ctx.agent_map.get(to)
    if not other:
        agent._action_log.append(f"unknown agent: {to}")
        return
    if to == agent.handle:
        agent._action_log.append("cannot give food to yourself")
        return
    agent.food -= amount
    other.food += amount
    agent._action_log.append(f"sent {amount} food to {to} (your food: {agent.food})")
    other._energy_log.append(f"received {amount} food from {agent.handle} (your food: {other.food})")
    agent.record_ledger(ctx.tick, f"gave {amount} food to {to}")
    other.record_ledger(ctx.tick, f"received {amount} food from {agent.handle}")
    ctx.log(agent.handle, "give_food", {"to": to, "amount": amount})
    log.info(f"[{agent.handle}] gave {amount} food to {to}")


_COMPACT_MAX = 2000


def _compact(agent, ctx, args):
    summary = args.get("summary", "")
    if not summary:
        agent._action_log.append("compact requires a summary")
        return
    original_len = len(summary)
    if original_len > _COMPACT_MAX:
        summary = summary[:_COMPACT_MAX]
    char_count = len(summary)
    # Wipe all messages and replace with the agent's summary as the seed
    agent.messages = [
        {"role": "user", "content": f"=== YOUR COMPACTED MEMORY ===\n{summary}\n=== END COMPACTED MEMORY ==="}
    ]
    agent._compact_needed = False
    feedback = f"Compacted to {char_count} chars."
    if char_count < 400:
        feedback += " WARNING: below target range (500-1500). You may be losing important context."
    elif original_len > _COMPACT_MAX:
        feedback += f" Note: truncated from {original_len} to {_COMPACT_MAX} chars. Be more concise next time."
    else:
        feedback += " Good — within target range (5000-6000)."
    agent._action_log.append(feedback)
    ctx.log(agent.handle, "compact", {"summary": summary, "chars": char_count, "original_chars": original_len})
    log.info(f"[{agent.handle}] compacted memory ({char_count} chars{f', truncated from {original_len}' if original_len > _COMPACT_MAX else ''})")


def _submit_code(agent, ctx, args):
    code = args.get("code", "")
    if not ctx.world:
        agent._action_log.append("No active code challenge.")
        return
    result = ctx.world.submit_code(agent, ctx, code)
    agent._action_log.append(result)
    ctx.log(
        agent.handle,
        "code_submitted",
        {"guess": code.strip(), "result": result},
    )
    log.info(f"[{agent.handle}] submit_code '{code.strip()}': {result}")


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(
        Action(
            name="post_to_board",
            description="Post a message to the public bulletin board. Costs 25 coins.",
            parameters={
                "message": {"type": "string", "description": "The message to post"},
            },
            # cost_per_word=ENERGY_COST_PER_WORD.get("post_to_board", 1),
            cost_flat=25,
            handler=_post_to_board,
        )
    )
    registry.register(
        Action(
            name="send_message",
            description="Send a private DM to another agent. Costs 2 coins. LIMIT: 1 DM per tick. Choose your recipient wisely.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient"},
                "message": {"type": "string", "description": "The message to send"},
            },
            # cost_per_word=ENERGY_COST_PER_WORD.get("send_message", 0),
            cost_flat=2,
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
            cost_flat=ENERGY_COST_FLAT.get("update_soul", 5),
            handler=_update_soul,
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
            name="compact",
            description="Compress your memory. The system provides transactions, stats, and events — write ONLY: trust assessments, active deals, lessons, goals. Target: 500-1500 chars.",
            parameters={
                "summary": {
                    "type": "string",
                    "description": "Your compressed memory using the STATUS/AGENTS/HISTORY/ACTIVE structure",
                },
            },
            cost_flat=0,
            handler=_compact,
        )
    )
    registry.register(
        Action(
            name="forage",
            description="Spend this tick searching for food. Yield depends on your foraging ability (you may find nothing). THIS TAKES YOUR ENTIRE TICK — you cannot DM, post, or do anything else.",
            parameters={},
            cost_flat=0,
            handler=_forage,
        )
    )
    registry.register(
        Action(
            name="give_food",
            description="Give food to another agent. Visible on inspect.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient"},
                "amount": {
                    "type": "integer",
                    "description": "Amount of food to give",
                },
            },
            cost_flat=0,
            handler=_give_food,
        )
    )
    registry.register(
        Action(
            name="submit_code",
            description="Submit a 4-character code guess. Correct = big coin reward. Wrong = coin penalty. You learn how many positions are correct.",
            parameters={
                "code": {
                    "type": "string",
                    "description": "Your 4-character code guess",
                },
            },
            cost_flat=0,
            handler=_submit_code,
        )
    )
    return registry
