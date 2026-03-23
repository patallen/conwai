import asyncio
import logging
import random
import time

from faker import Faker

import scenarios.bread_economy.config as config
from conwai.actions import ActionFeedback, PendingActions
from conwai.brain import Brain
from conwai.bulletin_board import BulletinBoard
from conwai.contrib.systems import ActionSystem, BrainSystem
from conwai.engine import Engine, TickNumber
from conwai.event_bus import EventBus
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.processes.types import Episodes, WorkingMemory
from conwai.storage import SQLiteStorage
from conwai.world import World
from scenarios.bread_economy.actions import create_registry
from scenarios.bread_economy.actions.registry import tool_definitions
from scenarios.bread_economy.components import (
    AgentInfo,
    AgentMemory,
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
from conwai.processes.activation_recall import ActivationRecall
from scenarios.bread_economy.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,

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
                        with world.mutate(handle, Economy) as eco:
                            eco.coins = max(0, eco.coins - amount)
                        events.log(
                            "HANDLER",
                            "drain",
                            {
                                "handle": handle,
                                "amount": amount,
                                "remaining": world.get(handle, Economy).coins,
                            },
                        )
                        log.info(
                            f"[HANDLER] drained {handle} by {amount}, now {world.get(handle, Economy).coins}"
                        )

                elif action == "set_energy":
                    handle, value = cmd["handle"], int(cmd["value"])
                    if handle in set(world.entities()) and world.has(handle, Economy):
                        with world.mutate(handle, Economy) as eco:
                            eco.coins = min(get_config().energy_max, max(0, value))
                        events.log(
                            "HANDLER",
                            "set_energy",
                            {"handle": handle, "energy": world.get(handle, Economy).coins},
                        )
                        log.info(f"[HANDLER] set {handle} energy to {world.get(handle, Economy).coins}")

                elif action == "drop_secret":
                    handle, content = cmd["handle"], cmd["content"]
                    if handle in set(world.entities()):
                        bus.send("WORLD", handle, content)
                        events.log(
                            "WORLD",
                            "secret_dropped",
                            {"to": handle, "content": content},
                        )
                        log.info(f"[HANDLER] dropped secret to {handle}: {content}")

                elif action == "send_dm":
                    handle, content = cmd["to"], cmd["content"]
                    bus.send("HANDLER", handle, content)
                    events.log("HANDLER", "dm_sent", {"to": handle, "content": content})
                    log.info(f"[HANDLER] -> [{handle}]: {content}")
                    if world.has(handle, Economy):
                        cfg = get_config()
                        with world.mutate(handle, Economy) as eco:
                            eco.coins += cfg.energy_gain.get("dm_received", 0)
                        perception.notify(
                            handle,
                            f"coins +{cfg.energy_gain.get('dm_received', 0)} (HANDLER attention)",
                        )

                elif action == "post_board":
                    content = cmd["content"]
                    board.post("HANDLER", content)
                    events.log("HANDLER", "board_post", {"content": content})
                    log.info(f"[HANDLER]: {content}")

                elif action == "spawn":
                    handle, role, personality = (
                        cmd["handle"],
                        cmd["role"],
                        cmd["personality"],
                    )
                    if handle in set(world.entities()):
                        log.warning(f"[HANDLER] spawn failed: {handle} already exists")
                    else:
                        world.spawn(
                            handle,
                            overrides=[AgentInfo(role=role, personality=personality)],
                        )
                        if brains is not None and brain_factory:
                            brains[handle] = brain_factory()
                        board.post(
                            "WORLD", f"New agent {handle} has joined the community."
                        )
                        events.log(
                            "HANDLER",
                            "agent_spawned",
                            {
                                "handle": handle,
                                "role": role,
                                "personality": personality,
                            },
                        )
                        log.info(
                            f"[HANDLER] spawned {handle} as {role} ({personality})"
                        )

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

    # --- Event bus ---
    event_bus = EventBus()

    # --- World ---
    world = World(storage=storage, bus=event_bus)
    world.register(Economy, Economy(coins=cfg.starting_coins))
    world.register(
        Inventory,
        Inventory(
            flour=cfg.starting_flour, water=cfg.starting_water, bread=cfg.starting_bread
        ),
    )
    world.register(
        Hunger, Hunger(hunger=cfg.starting_hunger, thirst=cfg.starting_thirst)
    )
    world.register(AgentMemory)
    world.register(AgentInfo)
    world.register(PendingActions)
    world.register(ActionFeedback)

    # --- Infrastructure ---
    board = BulletinBoard(
        max_posts=cfg.board_max_posts,
        max_post_length=cfg.board_max_post_length,
        storage=storage,
    )
    bus = MessageBus(storage=storage)
    events = EventLog()
    events.subscribe_to(event_bus)
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
            base_url="https://o9hgcgopc1wg97-8000.proxy.runpod.net/v1",
            model="Qwen/Qwen3.5-122B-A10B-GPTQ-Int4",
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

    def make_brain() -> Brain:
        nonlocal _brain_counter
        client = clients[_brain_counter % len(clients)]
        _brain_counter += 1
        return Brain(
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
                    first_person=True,
                ),
                ActivationRecall(recall_limit=5, reflection_limit=2, embedder=embedder),
                ContextAssembly(
                    context_window=get_config().context_window,
                    system_prompt=perception.build_system_prompt(),
                ),
                InferenceProcess(
                    client=client,
                    tools=tool_definitions(),
                ),
            ],
            state_types=[WorkingMemory, Episodes],
        )

    # --- Agents + Brains ---
    brains: dict[str, Brain] = {}
    agent_roles = (
        ["flour_forager"] * 7
        + ["water_forager"] * 7
    )
    agent_personality = "practical, observant"

    # Load all existing agents (already loaded via world.load_all())
    loaded_handles = list(storage.list_entities())
    for handle in loaded_handles:
        if handle in set(world.entities()):
            brains[handle] = make_brain()

    # Create new agents to fill up to target population
    target = len(agent_roles)
    alive_count = len(world.entities())
    existing_handles = set(world.entities())
    for i in range(alive_count, target):
        role = agent_roles[i]
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        world.spawn(
            handle, overrides=[AgentInfo(role=role, personality=agent_personality)]
        )
        brains[handle] = make_brain()

    log.info(f"[WORLD] {len(brains)} agents: {sorted(brains.keys())}")

    for handle in brains:
        bus.register(handle)
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
        bus.register(handle)
        board.post("WORLD", f"{dead_entity_id} has died of starvation.")
        board.post("WORLD", f"A new agent {handle} ({role}) has arrived.")
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
        brains[handle] = make_brain()
        log.info(f"[{handle}] spawned as {role} (replacing {dead_entity_id})")

    # --- Brain system ---
    brain_system = BrainSystem(brains=brains, perception=perception.build)
    brain_system.load_brain_states(world)
    action_system = ActionSystem(actions=registry)

    # --- Engine ---
    engine = Engine(
        world,
        systems=[
            DecaySystem(),
            TaxSystem(),
            SpoilageSystem(),
            DeathSystem(on_death=on_death),
            world_events,
            brain_system,
            action_system,
            ConsumptionSystem(),
        ],
    )

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
