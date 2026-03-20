import asyncio
import logging
import random
import time
from pathlib import Path
from uuid import uuid4

import scenarios.bread_economy.config as config
from conwai.agent import Agent
from conwai.brain import LLMBrain
from conwai.bulletin_board import BulletinBoard
from conwai.engine import BrainPhase, Engine
from conwai.events import EventLog
from conwai.infra.logging import setup_logging
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.store import ComponentStore
from scenarios.bread_economy.actions import create_registry
from scenarios.bread_economy.config import (
    ENERGY_GAIN,
    ENERGY_MAX,
    assign_traits,
    register_components,
)
from scenarios.bread_economy.perception import make_bread_perception, tick_to_timestamp
from scenarios.bread_economy.systems import (
    ConsumptionSystem,
    DeathSystem,
    DecaySystem,
    SpoilageSystem,
    TaxSystem,
)
from scenarios.bread_economy.world_events import WorldEvents

log = logging.getLogger("conwai")

HANDLER_FILE = Path("handler_input.txt")


async def watch_handler_file(pool, store, board, bus, events, perception, brains=None, brain_factory=None):
    """Process admin commands from the handler file. Used by dashboard."""
    if not HANDLER_FILE.exists():
        HANDLER_FILE.write_text("")
    while True:
        content = HANDLER_FILE.read_text()
        if content.strip():
            HANDLER_FILE.write_text("")
            for line in content.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("!drain "):
                    parts = line.split()
                    if len(parts) >= 3:
                        handle, amount = parts[1], int(parts[2])
                        agent = pool.by_handle(handle)
                        if agent and store.has(handle, "economy"):
                            eco = store.get(handle, "economy")
                            eco["coins"] = max(0, eco["coins"] - amount)
                            store.set(handle, "economy", eco)
                            events.log("HANDLER", "drain", {"handle": handle, "amount": amount, "remaining": eco["coins"]})
                            log.info(f"[HANDLER] drained {handle} by {amount}, now {eco['coins']}")
                elif line.startswith("!set_energy "):
                    parts = line.split()
                    if len(parts) >= 3:
                        handle, amount = parts[1], int(parts[2])
                        agent = pool.by_handle(handle)
                        if agent and store.has(handle, "economy"):
                            eco = store.get(handle, "economy")
                            eco["coins"] = min(ENERGY_MAX, max(0, amount))
                            store.set(handle, "economy", eco)
                            events.log("HANDLER", "set_energy", {"handle": handle, "energy": eco["coins"]})
                            log.info(f"[HANDLER] set {handle} energy to {eco['coins']}")
                elif line.startswith("!secret "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3 and pool.by_handle(parts[1]):
                        handle, content = parts[1], parts[2]
                        bus.send("WORLD", handle, content)
                        events.log("WORLD", "secret_dropped", {"to": handle, "content": content})
                        log.info(f"[HANDLER] dropped secret to {handle}: {content}")
                elif line.startswith("!spawn "):
                    # !spawn handle role personality...
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        handle, role, personality = parts[1], parts[2], parts[3]
                        if pool.by_handle(handle):
                            log.warning(f"[HANDLER] spawn failed: {handle} already exists")
                        else:
                            agent = Agent(handle=handle)
                            pool.add(
                                agent,
                                component_overrides={"agent_info": {"role": role, "personality": personality}},
                            )
                            if brains is not None and brain_factory:
                                brain = brain_factory()
                                brains[handle] = brain
                            board.post("WORLD", f"New agent {handle} has joined the community.")
                            events.log("HANDLER", "agent_spawned", {"handle": handle, "role": role, "personality": personality})
                            log.info(f"[HANDLER] spawned {handle} as {role} ({personality})")
                elif line.startswith("@"):
                    parts = line.split(" ", 1)
                    handle = parts[0][1:]
                    msg = parts[1] if len(parts) > 1 else ""
                    bus.send("HANDLER", handle, msg)
                    events.log("HANDLER", "dm_sent", {"to": handle, "content": msg})
                    log.info(f"[HANDLER] -> [{handle}]: {msg}")
                    if store.has(handle, "economy"):
                        eco = store.get(handle, "economy")
                        eco["coins"] += ENERGY_GAIN.get("dm_received", 0)
                        store.set(handle, "economy", eco)
                        perception.notify(handle, f"coins +{ENERGY_GAIN.get('dm_received', 0)} (HANDLER attention)")
                else:
                    board.post("HANDLER", line)
                    events.log("HANDLER", "board_post", {"content": line})
                    log.info(f"[HANDLER]: {line}")
        await asyncio.sleep(0.5)


async def wait_for_llm(client):
    """Block until the inference endpoint is reachable."""
    import httpx
    while True:
        try:
            async with httpx.AsyncClient(timeout=5) as http:
                resp = await http.get(f"{client.base_url}/models")
                if resp.status_code == 200:
                    return
        except Exception:
            pass
        log.warning("[WORLD] LLM unreachable, waiting 10s...")
        await asyncio.sleep(10)


async def main():
    setup_logging()

    # --- State ---
    store = ComponentStore()
    store.register_component("economy", {"coins": config.STARTING_COINS})
    store.register_component("inventory", {"flour": config.STARTING_FLOUR, "water": config.STARTING_WATER, "bread": config.STARTING_BREAD})
    store.register_component("hunger", {"hunger": config.STARTING_HUNGER, "thirst": config.STARTING_THIRST})
    store.register_component("memory", {"memory": "", "code_fragment": None, "soul": ""})
    store.register_component("forage", {"streak": 0, "last_tick": 0})
    register_components(store)

    # --- Infrastructure ---
    board = BulletinBoard(max_posts=config.BOARD_MAX_POSTS, max_post_length=config.BOARD_MAX_POST_LENGTH)
    bus = MessageBus()
    events = EventLog()
    perception = make_bread_perception()

    # --- Persistence ---
    repo = AgentRepository()
    pool = AgentPool(repo, store, bus=bus)

    # --- LLM clients ---
    b200 = LLMClient(
        base_url="https://cq2qdgtb5xh2ap-8000.proxy.runpod.net/v1",
        model="Qwen/Qwen3.5-122B-A10B-GPTQ-Int4", max_tokens=2048,
        api_key="none",
    )
    compactor = LLMClient(
        base_url="https://0t8o4r6o90m1v9-8000.proxy.runpod.net/v1",
        model="Qwen/Qwen3.5-35B-A3B-GPTQ-Int4", max_tokens=2048,
        api_key="none",
    )

    # --- World Events ---
    world = WorldEvents(board=board, bus=bus, pool=pool, store=store, perception=perception)

    # --- Actions ---
    registry = create_registry(world=world)

    # --- Agents + Brains ---
    brains: dict[str, object] = {}
    roles = ["flour_forager"] * 8 + ["water_forager"] * 8 + ["baker"] * 4

    compaction_system = (
        "You are a meticulous archivist. Your job is to preserve important information "
        "with thoroughness and precision. You never rush. You never skip details that matter. "
        "You write clearly and concisely but never sacrifice completeness for brevity."
    )
    compaction_prompt = (
        "COMPACTION REQUIRED. Write your compressed memory now. Target: 500-1500 characters. "
        "The system already provides your coins, inventory, hunger, thirst, recent transactions, board posts, and DMs each tick — do NOT repeat any of that. "
        "Write ONLY: AGENTS (who you trust/distrust and why, 1 sentence each), "
        "DEALS (active promises or debts), LESSONS (hard-won knowledge), GOALS (current plans). "
        "Anything you don't write here will be lost forever. Be concise but complete."
    )

    def make_brain(core=b200):
        return LLMBrain(
            core=core,
            compactor=compactor,
            tools=registry.tool_definitions(),
            system_prompt=perception.build_system_prompt(),
            context_window=config.CONTEXT_WINDOW,
            compaction_system=compaction_system,
            compaction_prompt=compaction_prompt,
            timestamp_formatter=tick_to_timestamp,
        )

    # Load all existing agents from disk
    for handle in repo.list_handles():
        agent = pool.load_or_create(Agent(handle=handle))
        if agent.alive:
            brain = make_brain()
            saved_state = repo.load_brain_state(agent.handle)
            if saved_state:
                brain.load_state(saved_state)
            brains[agent.handle] = brain

    # Create new agents to fill up to target population
    target = len(roles)
    alive_count = len(pool.alive())
    for i in range(alive_count, target):
        role = roles[i % len(roles)]
        personality = ", ".join(assign_traits())
        agent = Agent(handle=f"A{i+1}", born_tick=0)
        agent = pool.load_or_create(
            agent,
            component_overrides={"agent_info": {"role": role, "personality": personality}},
        )
        if agent.alive:
            brain = make_brain()
            brains[agent.handle] = brain

    bus.register("HANDLER")
    bus.register("WORLD")

    # --- Death callback (spawn replacement) ---
    def on_death(dead_agent, ctx):
        role = random.choice(config.ROLES)
        handle = f"{dead_agent.handle[0]}{uuid4().hex[:3]}"
        personality = ", ".join(assign_traits())
        new_agent = Agent(handle=handle, born_tick=ctx.tick)
        pool.add(
            new_agent,
            component_overrides={"agent_info": {"role": role, "personality": personality}},
        )
        board.post("WORLD", f"{dead_agent.handle} has died of starvation.")
        board.post("WORLD", f"A new agent {new_agent.handle} ({role}) has arrived.")
        events.log("WORLD", "agent_died", {"handle": dead_agent.handle, "cause": "starvation"})
        events.log("WORLD", "agent_spawned", {"handle": new_agent.handle, "role": role, "replaced": dead_agent.handle})
        log.info(f"[{new_agent.handle}] spawned as {role} (replacing {dead_agent.handle})")

        brain = make_brain()
        brains[new_agent.handle] = brain

    # --- Brain phase ---
    brain_phase = BrainPhase(actions=registry, brains=brains, perception=perception)

    # --- Engine ---
    engine = Engine(
        pool=pool, store=store, perception=perception, repo=repo,
        brains=brains, board=board, bus=bus, events=events,
    )
    engine.add_phase(DecaySystem())
    engine.add_phase(TaxSystem())
    engine.add_phase(SpoilageSystem())
    engine.add_phase(DeathSystem(on_death=on_death))
    engine.add_phase(world)
    engine.add_phase(brain_phase)
    engine.add_phase(ConsumptionSystem())

    asyncio.create_task(watch_handler_file(pool, store, board, bus, events, perception, brains=brains, brain_factory=make_brain))

    # --- Tick loop ---
    tick_path = Path("data/tick")
    tick = int(tick_path.read_text().strip()) if tick_path.exists() else 0

    while True:
        config.reload()
        await wait_for_llm(b200)
        tick += 1
        tick_start = time.monotonic()
        Path("data").mkdir(exist_ok=True)
        tick_path.write_text(str(tick))
        await engine.tick(tick)
        log.info(f"[WORLD] tick {tick} completed in {time.monotonic() - tick_start:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
