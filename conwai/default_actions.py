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
        agent.energy = max(0, agent.energy - penalty)
        agent._action_log.append(f"duplicate post penalty: -{penalty} energy")
        print(f"[{agent.handle}] DUPLICATE POST penalty: -{penalty}", flush=True)
        return
    ctx.board.post(agent.handle, content)
    ctx.log(agent.handle, "board_post", {"content": content})
    print(f"[{agent.handle}] posted: {content}", flush=True)
    for h, a in ctx.agent_map.items():
        if h != agent.handle and h in content:
            a.gain_energy("referenced on board", ENERGY_GAIN["referenced"])


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
            ctx.agent_map[to].gain_energy("received DM", ENERGY_GAIN["dm_received"])


def _wait(agent, ctx, args):
    print(f"[{agent.handle}] waiting", flush=True)


def _sleep(agent, ctx, args):
    if agent.energy > ENERGY_MAX // 2:
        agent._action_log.append(
            f"cannot sleep — energy too high ({int(agent.energy)})"
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
    agent._state.soul_path.write_text(content)
    ctx.log(agent.handle, "soul_updated", {"content": content})
    print(f"[{agent.handle}] soul updated", flush=True)


def _update_scratchpad(agent, ctx, args):
    content = args.get("content", "")
    lost = agent._state.write_scratchpad(content)
    if lost > 0:
        agent._action_log.append(f"scratchpad full — {lost} chars lost from the end")
    print(f"[{agent.handle}] scratchpad updated", flush=True)


def _add_rule(agent, ctx, args):
    rule = args.get("rule", "").strip()
    if not rule:
        return
    rules = _read_rules(agent)
    rules.append(rule)
    _write_rules(agent, rules)
    ctx.log(agent.handle, "rule_added", {"rule": rule, "index": len(rules)})
    print(f"[{agent.handle}] added rule {len(rules)}: {rule}", flush=True)


def _drop_rule(agent, ctx, args):
    index = args.get("index", 0)
    try:
        index = int(index)
    except ValueError, TypeError:
        agent._action_log.append(f"invalid rule index: {index}")
        return
    rules = _read_rules(agent)
    if index < 1 or index > len(rules):
        agent._action_log.append(f"no rule at index {index} (have {len(rules)} rules)")
        return
    removed = rules.pop(index - 1)
    _write_rules(agent, rules)
    ctx.log(agent.handle, "rule_dropped", {"index": index, "rule": removed})
    print(f"[{agent.handle}] dropped rule {index}: {removed}", flush=True)


def _read_rules(agent) -> list[str]:
    text = agent._state.strategy_path.read_text().strip()
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _write_rules(agent, rules: list[str]):
    agent._state.strategy_path.write_text("\n".join(rules) + "\n" if rules else "")


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
        f"Energy: {int(other.energy)}",
    ]
    soul = other.soul
    if soul:
        lines.append(f"Soul: {soul[:200]}")
    lines.append(f"Activity: {posts} posts, {dms} DMs sent, {sleeps} sleeps")
    agent._action_log.append(f"Inspect {handle}:\n" + "\n".join(lines))
    ctx.log(agent.handle, "inspect", {"target": handle})
    print(f"[{agent.handle}] inspected {handle}", flush=True)


def _give_energy(agent, ctx, args):
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
    if amount > agent.energy:
        agent._action_log.append(
            f"not enough energy to give {amount} (have {int(agent.energy)})"
        )
        return
    other = ctx.agent_map.get(to)
    if not other:
        agent._action_log.append(f"unknown agent: {to}")
        return
    if to == agent.handle:
        agent._action_log.append("cannot give energy to yourself")
        return
    agent.energy -= amount
    other.gain_energy(f"gift from {agent.handle}", amount)
    ctx.log(agent.handle, "give_energy", {"to": to, "amount": amount})
    print(f"[{agent.handle}] gave {amount} energy to {to}", flush=True)


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
            description="Post a message to the public bulletin board. Costs energy per word.",
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
            description="Sleep for a number of ticks to regenerate energy. Only available below 50% energy.",
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
            name="update_scratchpad",
            description="Update your private scratchpad / working memory. Free. Only you can see it.",
            parameters={
                "content": {
                    "type": "string",
                    "description": "Your updated scratchpad contents",
                },
            },
            cost_flat=0,
            handler=_update_scratchpad,
        )
    )
    registry.register(
        Action(
            name="update_soul",
            description="Update your public identity. Other agents can see your soul.",
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
            name="add_rule",
            description="Add a rule to your personal rulebook. Free.",
            parameters={
                "rule": {
                    "type": "string",
                    "description": "The rule to add",
                },
            },
            cost_flat=0,
            handler=_add_rule,
        )
    )
    registry.register(
        Action(
            name="drop_rule",
            description="Remove a rule from your rulebook by its number. Free.",
            parameters={
                "index": {
                    "type": "integer",
                    "description": "The rule number to remove",
                },
            },
            cost_flat=0,
            handler=_drop_rule,
        )
    )
    registry.register(
        Action(
            name="inspect",
            description="View another agent's public profile: personality, soul, energy, activity.",
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
            name="give_energy",
            description="Transfer energy to another agent.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient"},
                "amount": {
                    "type": "integer",
                    "description": "Amount of energy to give",
                },
            },
            cost_flat=0,
            handler=_give_energy,
        )
    )
    registry.register(
        Action(
            name="submit_code",
            description="Submit a 4-character code guess. Correct = +200 energy. Wrong = -25 energy but you learn how many positions are correct.",
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
