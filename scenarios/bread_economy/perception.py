from __future__ import annotations

from pathlib import Path

from conwai.perception import Perception

_DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"


def tick_to_timestamp(tick: int) -> str:
    day = tick // 24 + 1
    hour = 8 + (tick % 24)
    if hour >= 24:
        hour -= 24
        day += 1
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"Day {day}, {display_hour}:00 {period}"


def make_bread_perception(prompts_dir: Path | None = None) -> Perception:
    """Create Perception configured for the bread economy scenario."""
    d = prompts_dir or _DEFAULT_PROMPTS_DIR
    identity_tpl = (d / "identity.md").read_text()
    soul_tpl = (d / "soul.md").read_text()
    memory_tpl = (d / "memory.md").read_text()
    tick_tpl = (d / "tick.md").read_text()
    system_prompt = (d / "system.md").read_text()

    def build_identity(agent, store):
        import scenarios.bread_economy.config as config
        info = store.get(agent.handle, "agent_info")
        role_desc = config.ROLE_DESCRIPTIONS.get(info["role"], "unknown role")
        mem = store.get(agent.handle, "memory")
        soul = mem.get("soul", "") or "(empty)"
        soul_block = soul_tpl.format(soul=soul)
        journal = mem.get("memory", "") or "(empty)"
        journal_block = memory_tpl.format(memory=journal)
        return identity_tpl.format(
            handle=agent.handle,
            personality=info["personality"],
            role_description=role_desc,
            soul=soul_block,
        ) + "\n\n" + journal_block

    def build_tick(agent, store, board, bus, tick, notifications):
        eco = store.get(agent.handle, "economy")
        inv = store.get(agent.handle, "inventory")
        hun = store.get(agent.handle, "hunger")
        mem = store.get(agent.handle, "memory")

        new_posts = board.read_new(agent.handle)
        if new_posts:
            parts = ["New on the board:\n" + "\n".join(f"{p.handle}: {p.content}" for p in new_posts)]
        else:
            parts = ["No new activity on the board."]

        new_dms = bus.receive(agent.handle)
        if new_dms:
            parts.append("\n".join(f"DM from {dm.from_handle}: {dm.content}" for dm in new_dms))

        if notifications:
            parts.append("Coin changes: " + ". ".join(notifications))

        if mem.get("code_fragment"):
            parts.append(f"YOUR CODE FRAGMENT: {mem['code_fragment']}")

        if hun["hunger"] <= 30:
            parts.append(f"WARNING: You are hungry (hunger: {hun['hunger']}/100, bread: {inv['bread']}). Eat bread or raw flour to restore hunger.")
        if hun["thirst"] <= 30:
            parts.append(f"WARNING: You are thirsty (thirst: {hun['thirst']}/100, water: {inv['water']}). Drink water to restore thirst.")

        return tick_tpl.format(
            timestamp=tick_to_timestamp(tick),
            coins=int(eco["coins"]),
            hunger=hun["hunger"],
            thirst=hun["thirst"],
            flour=inv["flour"],
            water=inv["water"],
            bread=inv["bread"],
            content="\n\n".join(parts),
        )

    return Perception(
        identity_builder=build_identity,
        tick_builder=build_tick,
        system_prompt=system_prompt,
    )
