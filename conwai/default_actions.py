from conwai.actions import Action, ActionRegistry
from conwai.config import ENERGY_COST_FLAT, ENERGY_COST_PER_WORD, ENERGY_GAIN, ENERGY_MAX


def _remember(agent, ctx, content, target):
    agent.remember(content)
    ctx.log(agent.handle, "remember", {"content": content})
    print(f"[{agent.handle}] remembered: {content[:80]}", flush=True)


def _recall(agent, ctx, content, target):
    keyword = target or ""
    memories = agent.recall(keyword=keyword)
    agent._messages.append({"role": "user", "content": f"Your memories:\n{memories}"})
    print(f"[{agent.handle}] recalled (query='{keyword}'): {memories[:80]}", flush=True)


def _post_to_board(agent, ctx, content, target):
    ctx.board.post(agent.handle, content)
    ctx.log(agent.handle, "board_post", {"content": content})
    print(f"[{agent.handle}] posted: {content}", flush=True)
    for h, a in ctx.agent_map.items():
        if h != agent.handle and h in content:
            a.gain_energy("referenced on board", ENERGY_GAIN["referenced"])


def _send_message(agent, ctx, content, target):
    if not target:
        return
    err = ctx.bus.send(agent.handle, target, content)
    if err:
        agent._action_log.append(f"DM failed: {err}")
        print(f"[{agent.handle}] SEND FAILED: {err}", flush=True)
    else:
        ctx.log(agent.handle, "dm_sent", {"to": target, "content": content})
        print(f"[{agent.handle}] -> [{target}]: {content}", flush=True)
        if target in ctx.agent_map:
            ctx.agent_map[target].gain_energy("received DM", ENERGY_GAIN["dm_received"])


def _wait(agent, ctx, content, target):
    print(f"[{agent.handle}] waiting", flush=True)


def _sleep(agent, ctx, content, target):
    if agent.energy > ENERGY_MAX // 2:
        agent._action_log.append(
            f"cannot sleep — energy too high ({agent.energy}/{ENERGY_MAX})"
        )
        print(f"[{agent.handle}] CANNOT SLEEP — energy above 50%", flush=True)
        return
    try:
        ticks = int(content.strip())
    except ValueError:
        ticks = 5
    agent.sleep(ticks)
    ctx.log(agent.handle, "sleep", {"ticks": agent._sleep_ticks})
    print(f"[{agent.handle}] sleeping for {agent._sleep_ticks} ticks", flush=True)


def _update_soul(agent, ctx, content, target):
    agent._soul_path.write_text(content)
    ctx.log(agent.handle, "soul_updated", {"content": content})
    print(f"[{agent.handle}] soul updated", flush=True)


def _submit_code(agent, ctx, content, target):
    if not ctx.world:
        agent._action_log.append("No active code challenge.")
        return
    result = ctx.world.submit_code(agent, ctx, content)
    agent._action_log.append(result)
    ctx.log(agent.handle, "code_submitted", {"guess": content.strip(), "result": result})
    print(f"[{agent.handle}] submit_code '{content.strip()}': {result}", flush=True)


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(
        Action(
            name="post_to_board",
            description="your message here",
            cost_per_word=ENERGY_COST_PER_WORD.get("post_to_board", 1),
            handler=_post_to_board,
        )
    )
    registry.register(
        Action(
            name="send_message",
            description="your message here",
            cost_per_word=ENERGY_COST_PER_WORD.get("send_message", 0.5),
            handler=_send_message,
        )
    )
    registry.register(
        Action(
            name="remember",
            description="what you want to store",
            cost_per_word=ENERGY_COST_PER_WORD.get("remember", 0.5),
            handler=_remember,
        )
    )
    registry.register(
        Action(
            name="recall",
            description="",
            cost_flat=ENERGY_COST_FLAT.get("recall", 0),
            handler=_recall,
        )
    )
    registry.register(
        Action(
            name="wait",
            description="do nothing this tick",
            cost_flat=0,
            handler=_wait,
        )
    )
    registry.register(
        Action(
            name="sleep",
            description="number of ticks to sleep (regenerates energy)",
            cost_flat=0,
            handler=_sleep,
        )
    )
    registry.register(
        Action(
            name="update_soul",
            description="your full updated soul here",
            cost_flat=ENERGY_COST_FLAT.get("update_soul", 5),
            handler=_update_soul,
        )
    )
    registry.register(
        Action(
            name="submit_code",
            description="your 4-character code guess (wrong guesses cost 25 energy)",
            cost_flat=0,
            handler=_submit_code,
        )
    )
    return registry
