import asyncio
import logging
import random
import time

from faker import Faker

import scenarios.bread_economy.config as config
from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition import BlackboardBrain, Brain
from conwai.engine import BrainPhase, Engine
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.bread_economy.actions import create_registry
from scenarios.bread_economy.config import (
    assign_traits,
    get_config,
    register_components,
)
from scenarios.bread_economy.events import WorldEvents
from scenarios.bread_economy.perception import (
    make_bread_perception,
    tick_to_timestamp,
)
from scenarios.bread_economy.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
    MemoryRecall,
)
from scenarios.bread_economy.systems import (
    ConsumptionSystem,
    DeathSystem,
    DecaySystem,
    SpoilageSystem,
    TaxSystem,
)

log = logging.getLogger("conwai")

async def process_commands(
    storage, pool, store, board, bus, events, perception, brains=None, brain_factory=None
):
    """Poll the command queue and execute admin commands from the dashboard."""
    while True:
        for cmd in storage.pop_commands():
            action = cmd.get("action", "")
            try:
                if action == "drain_energy":
                    handle, amount = cmd["handle"], int(cmd["amount"])
                    if pool.by_handle(handle) and store.has(handle, "economy"):
                        eco = store.get(handle, "economy")
                        eco["coins"] = max(0, eco["coins"] - amount)
                        store.set(handle, "economy", eco)
                        events.log("HANDLER", "drain", {"handle": handle, "amount": amount, "remaining": eco["coins"]})
                        log.info(f"[HANDLER] drained {handle} by {amount}, now {eco['coins']}")

                elif action == "set_energy":
                    handle, value = cmd["handle"], int(cmd["value"])
                    if pool.by_handle(handle) and store.has(handle, "economy"):
                        eco = store.get(handle, "economy")
                        eco["coins"] = min(get_config().energy_max, max(0, value))
                        store.set(handle, "economy", eco)
                        events.log("HANDLER", "set_energy", {"handle": handle, "energy": eco["coins"]})
                        log.info(f"[HANDLER] set {handle} energy to {eco['coins']}")

                elif action == "drop_secret":
                    handle, content = cmd["handle"], cmd["content"]
                    if pool.by_handle(handle):
                        bus.send("WORLD", handle, content)
                        events.log("WORLD", "secret_dropped", {"to": handle, "content": content})
                        log.info(f"[HANDLER] dropped secret to {handle}: {content}")

                elif action == "send_dm":
                    handle, content = cmd["to"], cmd["content"]
                    bus.send("HANDLER", handle, content)
                    events.log("HANDLER", "dm_sent", {"to": handle, "content": content})
                    log.info(f"[HANDLER] -> [{handle}]: {content}")
                    if store.has(handle, "economy"):
                        cfg = get_config()
                        eco = store.get(handle, "economy")
                        eco["coins"] += cfg.energy_gain.get("dm_received", 0)
                        store.set(handle, "economy", eco)
                        perception.notify(handle, f"coins +{cfg.energy_gain.get('dm_received', 0)} (HANDLER attention)")

                elif action == "post_board":
                    content = cmd["content"]
                    board.post("HANDLER", content)
                    events.log("HANDLER", "board_post", {"content": content})
                    log.info(f"[HANDLER]: {content}")

                elif action == "spawn":
                    handle, role, personality = cmd["handle"], cmd["role"], cmd["personality"]
                    if pool.by_handle(handle):
                        log.warning(f"[HANDLER] spawn failed: {handle} already exists")
                    else:
                        agent = Agent(handle=handle)
                        pool.add(agent, component_overrides={"agent_info": {"role": role, "personality": personality}})
                        if brains is not None and brain_factory:
                            brains[handle] = brain_factory()
                        board.post("WORLD", f"New agent {handle} has joined the community.")
                        events.log("HANDLER", "agent_spawned", {"handle": handle, "role": role, "personality": personality})
                        log.info(f"[HANDLER] spawned {handle} as {role} ({personality})")

            except (KeyError, ValueError) as e:
                log.warning(f"[HANDLER] bad command {cmd}: {e}")

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


async def run():
    """Run the bread economy scenario."""
    cfg = get_config()

    fake = Faker()
    if cfg.seed is not None:
        random.seed(cfg.seed)
        Faker.seed(cfg.seed)
        log.info(f"[WORLD] random seed: {cfg.seed}")

    # --- Storage ---
    storage = SQLiteStorage()

    # --- State ---
    store = ComponentStore(storage=storage)
    store.register_component(
        "economy", {"coins": cfg.starting_coins}
    )
    store.register_component(
        "inventory",
        {
            "flour": cfg.starting_flour,
            "water": cfg.starting_water,
            "bread": cfg.starting_bread,
        },
    )
    store.register_component(
        "hunger", {"hunger": cfg.starting_hunger, "thirst": cfg.starting_thirst}
    )
    store.register_component(
        "memory", {"memory": "", "code_fragment": None, "soul": "", "strategy": ""}
    )
    store.register_component("brain", {"messages": [], "diary": []})
    register_components(store)

    # Load all persisted state from storage
    store.load_all()

    # --- Infrastructure ---
    board = BulletinBoard(
        max_posts=cfg.board_max_posts, max_post_length=cfg.board_max_post_length,
        storage=storage,
    )
    bus = MessageBus(storage=storage)
    events = EventLog()
    perception = make_bread_perception()

    # --- Persistence ---
    repo = AgentRepository(storage=storage)
    pool = AgentPool(repo, store, bus=bus)

    # --- LLM clients ---
    clients = [
        LLMClient(
            base_url="https://50d7tuyzqnx256-8000.proxy.runpod.net/v1",
            model="Qwen/Qwen3.5-122B-A10B-GPTQ-Int4",
            max_tokens=2048,
            api_key="none",
        ),
    ]

    # --- World Events ---
    world = WorldEvents(
        board=board, bus=bus, pool=pool, store=store, perception=perception,
        storage=storage,
    )

    # --- Actions ---
    registry = create_registry(world=world)

    # --- Embedder (shared across all agents, stateless) ---
    from conwai.embeddings import FastEmbedder

    embedder = FastEmbedder()

    # --- Brain pipeline: round-robin across LLM clients ---
    from scenarios.bread_economy.processes.review import StrategicReview

    _brain_counter = 0

    def make_brain() -> BlackboardBrain:
        nonlocal _brain_counter
        client = clients[_brain_counter % len(clients)]
        _brain_counter += 1
        return BlackboardBrain(
            processes=[
                StrategicReview(client=client, store=store, interval=24),
                MemoryCompression(
                    recent_ticks=16,
                    timestamp_formatter=tick_to_timestamp,
                    embedder=embedder,
                ),
                MemoryRecall(recall_limit=5, embedder=embedder),
                ContextAssembly(
                    context_window=get_config().context_window,
                    system_prompt=perception.build_system_prompt(),
                ),
                InferenceProcess(
                    client=client,
                    tools=registry.tool_definitions(),
                ),
            ],
            store=store,
        )

    # --- Agents + Brains ---
    brains: dict[str, Brain] = {}
    roles = ["flour_forager"] * 13 + ["water_forager"] * 13

    # Load all existing agents from storage
    for handle in repo.list_handles():
        agent = pool.load_or_create(Agent(handle=handle))
        if agent.alive:
            brains[agent.handle] = make_brain()

    # Create new agents to fill up to target population
    target = len(roles)
    alive_count = len(pool.alive())
    existing_handles = {a.handle for a in pool.alive()}
    for i in range(alive_count, target):
        role = roles[i % len(roles)]
        personality = ", ".join(assign_traits())
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        agent = Agent(handle=handle, born_tick=0)
        agent = pool.load_or_create(
            agent,
            component_overrides={
                "agent_info": {"role": role, "personality": personality}
            },
        )
        if agent.alive:
            brains[agent.handle] = make_brain()

    bus.register("HANDLER")
    bus.register("WORLD")

    # --- Death callback (spawn replacement) ---
    def on_death(dead_agent, ctx):
        role = random.choice(get_config().roles)
        handle = fake.first_name()
        current_handles = {a.handle for a in pool.alive()}
        while handle in current_handles:
            handle = fake.first_name()
        personality = ", ".join(assign_traits())
        new_agent = Agent(handle=handle, born_tick=ctx.tick)
        pool.add(
            new_agent,
            component_overrides={
                "agent_info": {"role": role, "personality": personality}
            },
        )
        board.post("WORLD", f"{dead_agent.handle} has died of starvation.")
        board.post(
            "WORLD", f"A new agent {new_agent.handle} ({role}) has arrived."
        )
        events.log(
            "WORLD",
            "agent_died",
            {"handle": dead_agent.handle, "cause": "starvation"},
        )
        events.log(
            "WORLD",
            "agent_spawned",
            {
                "handle": new_agent.handle,
                "role": role,
                "replaced": dead_agent.handle,
            },
        )
        log.info(
            f"[{new_agent.handle}] spawned as {role} (replacing {dead_agent.handle})"
        )

        brains[new_agent.handle] = make_brain()

    # --- Brain phase ---
    brain_phase = BrainPhase(
        actions=registry, brains=brains, perception=perception
    )

    # --- Engine ---
    engine = Engine(
        pool=pool,
        store=store,
        perception=perception,
        board=board,
        bus=bus,
        events=events,
    )
    engine.add_phase(DecaySystem())
    engine.add_phase(TaxSystem())
    engine.add_phase(SpoilageSystem())
    engine.add_phase(DeathSystem(on_death=on_death))
    engine.add_phase(world)
    engine.add_phase(brain_phase)
    engine.add_phase(ConsumptionSystem())

    asyncio.create_task(
        process_commands(
            storage,
            pool,
            store,
            board,
            bus,
            events,
            perception,
            brains=brains,
            brain_factory=make_brain,
        )
    )

    # --- Tick loop ---
    tick_data = storage.load_component("WORLD", "tick")
    tick = tick_data["value"] if tick_data else 0

    while True:
        config.reload()
        await wait_for_llm(clients[0])
        tick += 1
        tick_start = time.monotonic()
        storage.save_component("WORLD", "tick", {"value": tick})
        await engine.tick(tick)
        log.info(
            f"[WORLD] tick {tick} completed in {time.monotonic() - tick_start:.1f}s"
        )
