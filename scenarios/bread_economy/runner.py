import asyncio
import json
import logging
import random
import time

from faker import Faker

import scenarios.bread_economy.config as config
from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition import BlackboardBrain
from conwai.engine import BrainPhase, Engine
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.bread_economy.actions import create_registry
from scenarios.bread_economy.components import (
    AgentInfo,
    AgentMemory,
    BrainState,
    Economy,
    Hunger,
    Inventory,
)
from scenarios.bread_economy.config import (
    assign_traits,
    get_config,
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
                    if pool.by_handle(handle) and store.has(handle, Economy):
                        eco = store.get(handle, Economy)
                        eco.coins = max(0, eco.coins - amount)
                        store.set(handle, eco)
                        events.log("HANDLER", "drain", {"handle": handle, "amount": amount, "remaining": eco.coins})
                        log.info(f"[HANDLER] drained {handle} by {amount}, now {eco.coins}")

                elif action == "set_energy":
                    handle, value = cmd["handle"], int(cmd["value"])
                    if pool.by_handle(handle) and store.has(handle, Economy):
                        eco = store.get(handle, Economy)
                        eco.coins = min(get_config().energy_max, max(0, value))
                        store.set(handle, eco)
                        events.log("HANDLER", "set_energy", {"handle": handle, "energy": eco.coins})
                        log.info(f"[HANDLER] set {handle} energy to {eco.coins}")

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
                    if store.has(handle, Economy):
                        cfg = get_config()
                        eco = store.get(handle, Economy)
                        eco.coins += cfg.energy_gain.get("dm_received", 0)
                        store.set(handle, eco)
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
                        pool.add(agent, component_overrides=[AgentInfo(role=role, personality=personality)])
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
    store.register(Economy, Economy(coins=cfg.starting_coins))
    store.register(
        Inventory,
        Inventory(flour=cfg.starting_flour, water=cfg.starting_water, bread=cfg.starting_bread),
    )
    store.register(Hunger, Hunger(hunger=cfg.starting_hunger, thirst=cfg.starting_thirst))
    store.register(AgentMemory)
    store.register(BrainState)
    store.register(AgentInfo)

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
            base_url="http://ai-lab.lan:8081/v1",
            model="/mnt/models/Qwen3.5-27B-GPTQ-Int4",
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

    log.info("[WORLD] loading embedding model...")
    embedder = FastEmbedder()
    log.info("[WORLD] embedding model ready")

    # --- Brain pipeline: round-robin across LLM clients ---
    from scenarios.bread_economy.processes.consolidation import ConsolidationProcess
    from scenarios.bread_economy.processes.review import StrategicReview

    articulator = LLMClient(
        base_url="http://ai-lab.lan:8081/v1",
        model="/mnt/models/Qwen3.5-27B-GPTQ-Int4",
        max_tokens=256,
        api_key="none",
    )

    _brain_counter = 0

    def make_brain(first_person: bool = True) -> BlackboardBrain:
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
                    noise_actions={"update_journal", "wait"},
                ),
                ConsolidationProcess(
                    interval=24,
                    articulator=articulator,
                    embedder=embedder,
                    first_person=first_person,
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
        )

    # --- Agents + Brains ---
    # A/B test: first-person vs third-person reflections
    brains: dict[str, BlackboardBrain] = {}
    first_person_group: set[str] = set()
    # 20 agents: indices 0-9 = first-person, 10-19 = third-person
    # Each group: 5 flour + 5 water, all same neutral personality
    ab_roles = (
        ["flour_forager"] * 2 + ["water_forager"] * 2  # first-person
        + ["flour_forager"] * 1 + ["water_forager"] * 1  # third-person
    )
    ab_personality = "practical, observant"

    # Restore A/B group assignments from events DB if resuming
    saved_groups: dict[str, str] = {}
    try:
        import sqlite3 as _sql
        _edb = _sql.connect("data/events.db")
        for entity, data in _edb.execute(
            "SELECT entity, data FROM events WHERE type='ab_group'"
        ).fetchall():
            saved_groups[entity] = json.loads(data)["group"]
        _edb.close()
    except Exception:
        pass

    # Load all existing agents from storage
    loaded_handles = list(repo.list_handles())
    for handle in loaded_handles:
        agent = pool.load_or_create(Agent(handle=handle))
        if agent.alive:
            if handle in saved_groups:
                fp = saved_groups[handle] == "first_person"
            else:
                fp = len(first_person_group) < 4
            brains[agent.handle] = make_brain(first_person=fp)
            if fp:
                first_person_group.add(agent.handle)

    # Create new agents to fill up to target population
    target = len(ab_roles)
    alive_count = len(pool.alive())
    existing_handles = {a.handle for a in pool.alive()}
    for i in range(alive_count, target):
        role = ab_roles[i]
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        agent = Agent(handle=handle, born_tick=0)
        agent = pool.load_or_create(
            agent,
            component_overrides=[AgentInfo(role=role, personality=ab_personality)],
        )
        if agent.alive:
            fp = len(first_person_group) < 4
            brains[agent.handle] = make_brain(first_person=fp)
            if fp:
                first_person_group.add(agent.handle)

    log.info(f"[WORLD] A/B test: FIRST PERSON for {sorted(first_person_group)}")
    log.info(f"[WORLD] A/B test: THIRD PERSON for {sorted(set(brains.keys()) - first_person_group)}")
    # Only log ab_group events for new agents (avoid duplicates on resume)
    for handle in brains:
        if handle not in saved_groups:
            group = "first_person" if handle in first_person_group else "third_person"
            events.log(handle, "ab_group", {"group": group})

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
            component_overrides=[AgentInfo(role=role, personality=personality)],
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
        was_fp = dead_agent.handle in first_person_group
        if was_fp:
            first_person_group.discard(dead_agent.handle)
            first_person_group.add(new_agent.handle)
        brains[new_agent.handle] = make_brain(first_person=was_fp)
        group_label = "1P" if was_fp else "3P"
        log.info(
            f"[{new_agent.handle}] spawned as {role} (replacing {dead_agent.handle}, {group_label})"
        )

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
