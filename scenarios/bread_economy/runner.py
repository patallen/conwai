import asyncio
import json
import logging
import random
import time

from faker import Faker

import scenarios.bread_economy.config as config
from conwai.bulletin_board import BulletinBoard
from conwai.cognition import BlackboardBrain
from conwai.engine import BrainSystem, Engine, TickNumber
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.storage import SQLiteStorage
from conwai.world import World
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
    BreadPerceptionBuilder,
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

async def process_commands(world: World, brains=None, brain_factory=None):
    """Poll the command queue and execute admin commands from the dashboard."""
    storage = world._storage
    if not storage:
        return
    board = world.get_resource(BulletinBoard)
    bus = world.get_resource(MessageBus)
    events = world.get_resource(EventLog)
    perception = world.get_resource(BreadPerceptionBuilder)

    while True:
        for cmd in storage.pop_commands():
            action = cmd.get("action", "")
            try:
                if action == "drain_energy":
                    handle, amount = cmd["handle"], int(cmd["amount"])
                    if handle in set(world.entities()) and world.has(handle, Economy):
                        eco = world.get(handle, Economy)
                        eco.coins = max(0, eco.coins - amount)
                        events.log("HANDLER", "drain", {"handle": handle, "amount": amount, "remaining": eco.coins})
                        log.info(f"[HANDLER] drained {handle} by {amount}, now {eco.coins}")

                elif action == "set_energy":
                    handle, value = cmd["handle"], int(cmd["value"])
                    if handle in set(world.entities()) and world.has(handle, Economy):
                        eco = world.get(handle, Economy)
                        eco.coins = min(get_config().energy_max, max(0, value))
                        events.log("HANDLER", "set_energy", {"handle": handle, "energy": eco.coins})
                        log.info(f"[HANDLER] set {handle} energy to {eco.coins}")

                elif action == "drop_secret":
                    handle, content = cmd["handle"], cmd["content"]
                    if handle in set(world.entities()):
                        bus.send("WORLD", handle, content)
                        events.log("WORLD", "secret_dropped", {"to": handle, "content": content})
                        log.info(f"[HANDLER] dropped secret to {handle}: {content}")

                elif action == "send_dm":
                    handle, content = cmd["to"], cmd["content"]
                    bus.send("HANDLER", handle, content)
                    events.log("HANDLER", "dm_sent", {"to": handle, "content": content})
                    log.info(f"[HANDLER] -> [{handle}]: {content}")
                    if world.has(handle, Economy):
                        cfg = get_config()
                        eco = world.get(handle, Economy)
                        eco.coins += cfg.energy_gain.get("dm_received", 0)
                        perception.notify(handle, f"coins +{cfg.energy_gain.get('dm_received', 0)} (HANDLER attention)")

                elif action == "post_board":
                    content = cmd["content"]
                    board.post("HANDLER", content)
                    events.log("HANDLER", "board_post", {"content": content})
                    log.info(f"[HANDLER]: {content}")

                elif action == "spawn":
                    handle, role, personality = cmd["handle"], cmd["role"], cmd["personality"]
                    if handle in set(world.entities()):
                        log.warning(f"[HANDLER] spawn failed: {handle} already exists")
                    else:
                        world.spawn(handle, overrides=[AgentInfo(role=role, personality=personality)])
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

    # --- World ---
    world = World(storage=storage)
    world.register(Economy, Economy(coins=cfg.starting_coins))
    world.register(
        Inventory,
        Inventory(flour=cfg.starting_flour, water=cfg.starting_water, bread=cfg.starting_bread),
    )
    world.register(Hunger, Hunger(hunger=cfg.starting_hunger, thirst=cfg.starting_thirst))
    world.register(AgentMemory)
    world.register(BrainState)
    world.register(AgentInfo)

    # --- Infrastructure ---
    board = BulletinBoard(
        max_posts=cfg.board_max_posts, max_post_length=cfg.board_max_post_length,
        storage=storage,
    )
    bus = MessageBus(storage=storage)
    events = EventLog()
    perception = make_bread_perception()

    # Register resources on World
    world.set_resource(board)
    world.set_resource(bus)
    world.set_resource(events)
    world.set_resource(perception)
    world.set_resource(TickNumber(value=0))

    # --- Load persisted state ---
    world.load_all()

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
    world_events = WorldEvents(
        world=world,
        storage=storage,
    )

    # --- Actions ---
    registry = create_registry(world=world_events)
    world.set_resource(registry)

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
                StrategicReview(client=client, store=world, interval=24),
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

    # Load all existing agents (already loaded via world.load_all())
    loaded_handles = list(storage.list_entities())
    for handle in loaded_handles:
        if handle in set(world.entities()):
            if handle in saved_groups:
                fp = saved_groups[handle] == "first_person"
            else:
                fp = len(first_person_group) < 4
            brains[handle] = make_brain(first_person=fp)
            if fp:
                first_person_group.add(handle)

    # Create new agents to fill up to target population
    target = len(ab_roles)
    alive_count = len(world.entities())
    existing_handles = set(world.entities())
    for i in range(alive_count, target):
        role = ab_roles[i]
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        world.spawn(handle, overrides=[AgentInfo(role=role, personality=ab_personality)])
        fp = len(first_person_group) < 4
        brains[handle] = make_brain(first_person=fp)
        if fp:
            first_person_group.add(handle)

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
    def on_death(dead_entity_id, world):
        role = random.choice(get_config().roles)
        handle = fake.first_name()
        current_handles = set(world.entities())
        while handle in current_handles:
            handle = fake.first_name()
        personality = ", ".join(assign_traits())
        world.spawn(handle, overrides=[AgentInfo(role=role, personality=personality)])
        board.post("WORLD", f"{dead_entity_id} has died of starvation.")
        board.post(
            "WORLD", f"A new agent {handle} ({role}) has arrived."
        )
        events.log(
            "WORLD",
            "agent_died",
            {"handle": dead_entity_id, "cause": "starvation"},
        )
        events.log(
            "WORLD",
            "agent_spawned",
            {
                "handle": handle,
                "role": role,
                "replaced": dead_entity_id,
            },
        )
        was_fp = dead_entity_id in first_person_group
        if was_fp:
            first_person_group.discard(dead_entity_id)
            first_person_group.add(handle)
        brains[handle] = make_brain(first_person=was_fp)
        group_label = "1P" if was_fp else "3P"
        log.info(
            f"[{handle}] spawned as {role} (replacing {dead_entity_id}, {group_label})"
        )

    # --- Brain system ---
    brain_system = BrainSystem(
        actions=registry, brains=brains, perception=perception
    )

    # --- Engine ---
    engine = Engine(world, systems=[
        DecaySystem(),
        TaxSystem(),
        SpoilageSystem(),
        DeathSystem(on_death=on_death),
        world_events,
        brain_system,
        ConsumptionSystem(),
    ])

    asyncio.create_task(
        process_commands(
            world,
            brains=brains,
            brain_factory=make_brain,
        )
    )

    # --- Tick loop ---
    tick_number = world.get_resource(TickNumber)
    tick_data = storage.load_component("_meta", "tick")
    if tick_data:
        tick_number.value = tick_data["value"]

    while True:
        config.reload()
        await wait_for_llm(clients[0])
        tick_start = time.monotonic()
        storage.save_component("_meta", "tick", {"value": tick_number.value + 1})
        await engine.tick()
        log.info(
            f"[WORLD] tick {tick_number.value} completed in {time.monotonic() - tick_start:.1f}s"
        )
