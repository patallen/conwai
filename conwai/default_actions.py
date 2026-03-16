from conwai.actions import Action, ActionRegistry
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
        print(f"[{agent.handle}] DUPLICATE POST penalty: -{penalty}", flush=True)
        return
    ctx.board.post(agent.handle, content)
    ctx.log(agent.handle, "board_post", {"content": content})
    print(f"[{agent.handle}] posted: {content}", flush=True)
    for h, a in ctx.agent_map.items():
        if h != agent.handle and h in content:
            a.gain_coins("referenced on board", ENERGY_GAIN["referenced"])


def _send_message(agent, ctx, args):
    to = args.get("to", "")
    message = args.get("message", "")
    if not to:
        return
    err = ctx.bus.send(agent.handle, to, message)
    if err:
        agent._action_log.append(f"DM failed: {err}")
        print(f"[{agent.handle}] SEND FAILED: {err}", flush=True)
    else:
        ctx.log(agent.handle, "dm_sent", {"to": to, "content": message})
        print(f"[{agent.handle}] -> [{to}]: {message}", flush=True)
        if to in ctx.agent_map:
            ctx.agent_map[to].gain_coins("received DM", ENERGY_GAIN["dm_received"])


def _wait(agent, ctx, args):
    print(f"[{agent.handle}] waiting", flush=True)


def _sleep(agent, ctx, args):
    if agent.coins > ENERGY_MAX // 2:
        agent._action_log.append(
            f"cannot sleep — too many coins ({int(agent.coins)})"
        )
        print(f"[{agent.handle}] CANNOT SLEEP — energy above 50%", flush=True)
        return
    ticks = args.get("ticks", 5)
    try:
        ticks = int(ticks)
    except ValueError, TypeError:
        ticks = 5
    agent.sleep(ticks)
    ctx.log(agent.handle, "sleep", {"ticks": ticks})
    print(f"[{agent.handle}] sleeping for {ticks} ticks", flush=True)


def _update_soul(agent, ctx, args):
    content = args.get("content", "")
    agent.soul = content
    ctx.log(agent.handle, "soul_updated", {"content": content})
    print(f"[{agent.handle}] soul updated", flush=True)


def _update_journal(agent, ctx, args):
    content = args.get("content", "")
    lost = agent.write_memory(content)
    if lost > 0:
        agent._action_log.append(f"journal full — {lost} chars lost from the end")
    print(f"[{agent.handle}] journal updated", flush=True)


def _inspect(agent, ctx, args):
    handle = args.get("handle", "")
    other = ctx.agent_map.get(handle)
    if not other:
        print(f"[{agent.handle}] inspect failed: unknown agent {handle}", flush=True)
        return
    events = ctx.events.read_all() if hasattr(ctx.events, "read_all") else []
    posts = sum(
        1 for e in events if e.get("entity") == handle and e.get("type") == "board_post"
    )
    dms = sum(
        1 for e in events if e.get("entity") == handle and e.get("type") == "dm_sent"
    )
    sleeps = sum(
        1 for e in events if e.get("entity") == handle and e.get("type") == "sleeping"
    )
    lines = [
        f"Handle: {handle}",
        f"Personality: {other.personality}",
        f"Coins: {int(other.coins)}",
    ]
    soul = other.soul
    if soul:
        lines.append(f"Soul: {soul[:200]}")
    lines.append(f"Activity: {posts} posts, {dms} DMs sent, {sleeps} sleeps")
    agent._action_log.append(f"Inspect {handle}:\n" + "\n".join(lines))
    ctx.log(agent.handle, "inspect", {"target": handle})
    print(f"[{agent.handle}] inspected {handle}", flush=True)


def _pay(agent, ctx, args):
    to = args.get("to", "")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except ValueError, TypeError:
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
    ctx.log(agent.handle, "payment", {"to": to, "amount": amount})
    print(f"[{agent.handle}] paid {amount} coins to {to}", flush=True)


def _compact(agent, ctx, args):
    summary = args.get("summary", "")
    if not summary:
        agent._action_log.append("compact requires a summary")
        return
    # Wipe messages and store summary for injection into system prompt
    agent.messages = []
    agent.memory = summary
    agent._compact_needed = False
    ctx.log(agent.handle, "compact", {"summary": summary, "length": len(summary)})
    print(f"[{agent.handle}] compacted memory ({len(summary)} chars)", flush=True)


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
    print(f"[{agent.handle}] submit_code '{code.strip()}': {result}", flush=True)


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(
        Action(
            name="post_to_board",
            description="Post a message to the public bulletin board. Costs coins per word.",
            parameters={
                "message": {"type": "string", "description": "The message to post"},
            },
            cost_per_word=ENERGY_COST_PER_WORD.get("post_to_board", 1),
            handler=_post_to_board,
        )
    )
    registry.register(
        Action(
            name="send_message",
            description="Send a private DM to another agent.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient"},
                "message": {"type": "string", "description": "The message to send"},
            },
            cost_per_word=ENERGY_COST_PER_WORD.get("send_message", 0),
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
            name="sleep",
            description="Sleep for a number of ticks to regenerate coins. Only available below 50%.",
            parameters={
                "ticks": {
                    "type": "integer",
                    "description": "Number of ticks to sleep",
                },
            },
            cost_flat=0,
            handler=_sleep,
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
            description="View another agent's public profile: personality, soul, coins, activity.",
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
            description="Compact your memory. IMPORTANT: Think through what to save in plain text BEFORE calling this. Everything else will be forgotten. Include: who you trust/distrust, who owes you and who you owe, what you've learned about how things work, and anything happening right now that matters.",
            parameters={
                "summary": {
                    "type": "string",
                    "description": "Your carefully drafted summary of everything worth remembering",
                },
            },
            cost_flat=0,
            handler=_compact,
        )
    )
    registry.register(
        Action(
            name="submit_code",
            description="Submit a 4-character code guess. Correct = +200 coins. Wrong = -25 coins but you learn how many positions are correct.",
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
