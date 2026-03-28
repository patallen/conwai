import asyncio
import logging
import random
import time

from faker import Faker

import scenarios.bread_economy.config as config
from conwai.actions import ActionFeedback, ActionResult, PendingActions
from conwai.brain import Brain
from conwai.comm import BulletinBoard, MessageBus
from conwai.events import EventBus, EventLog
from conwai.scheduler import Scheduler, TickNumber
from conwai.tick_loop import TickLoop
from conwai.llm import LLMClient
from conwai.processes.types import Episodes, WorkingMemory
from conwai.storage import SQLiteStorage
from conwai.world import World
from scenarios.bread_economy.actions import create_registry
from scenarios.bread_economy.actions.economy import OfferBook
from scenarios.bread_economy.actions.registry import tool_definitions
from scenarios.bread_economy.systems import Treasury
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
from conwai.processes.importance import ImportanceScoring
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
    world.set_resource(Treasury())

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
    offer_book = OfferBook()
    world.set_resource(offer_book)
    registry = create_registry(world=world_events, offer_book=offer_book)
    world.set_resource(registry)

    # --- Embedder (shared across all agents, stateless) ---
    from conwai.llm import FastEmbedder

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

    def make_brain(with_importance: bool = False) -> Brain:
        nonlocal _brain_counter
        client = clients[_brain_counter % len(clients)]
        _brain_counter += 1
        processes = [
            StrategicReview(client=client, store=world, interval=24),
            MemoryCompression(
                recent_ticks=16,
                timestamp_formatter=tick_to_timestamp,
                embedder=embedder,
                noise_actions={"update_journal", "wait"},
            ),
        ]
        if with_importance:
            processes.append(ImportanceScoring(articulator=articulator))
        processes.extend([
            ConsolidationProcess(
                interval=24,
                articulator=articulator,
                embedder=embedder,
                first_person=True,
            ),
            ActivationRecall(
                recall_limit=5, reflection_limit=5, embedder=embedder,
                delta=0.2 if with_importance else 0.0,
            ),
            ContextAssembly(
                context_window=get_config().context_window,
                system_prompt=perception.build_system_prompt(),
            ),
            InferenceProcess(
                client=client,
                tools=tool_definitions(),
            ),
        ])
        return Brain(processes=processes, state_types=[WorkingMemory, Episodes])

    # --- Agents + Brains ---
    # A/B test: importance scoring on vs off
    brains: dict[str, Brain] = {}
    importance_group: set[str] = set()
    ab_roles = (
        ["flour_forager"] * 2
        + ["water_forager"] * 1  # importance on
        + ["flour_forager"] * 2
        + ["water_forager"] * 1  # importance off
    )
    agent_personality = "practical, observant"

    # Restore A/B group assignments from events DB if resuming
    saved_groups: dict[str, str] = {}
    try:
        import sqlite3 as _sql

        _edb = _sql.connect("data/events.db")
        for entity, data in _edb.execute(
            "SELECT entity, data FROM events WHERE type='ab_group'"
        ).fetchall():
            import json
            saved_groups[entity] = json.loads(data)["group"]
        _edb.close()
    except Exception:
        pass

    # Load all existing agents (already loaded via world.load_all())
    loaded_handles = list(storage.list_entities())
    target = len(ab_roles)
    for handle in loaded_handles:
        if handle in set(world.entities()):
            if handle in saved_groups:
                imp = saved_groups[handle] == "importance"
            else:
                imp = len(importance_group) < (target // 2)
            brains[handle] = make_brain(with_importance=imp)
            if imp:
                importance_group.add(handle)

    # Create new agents to fill up to target population
    alive_count = len(world.entities())
    existing_handles = set(world.entities())
    for i in range(alive_count, target):
        role = ab_roles[i]
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        world.spawn(
            handle, overrides=[AgentInfo(role=role, personality=agent_personality)]
        )
        imp = len(importance_group) < (target // 2)
        brains[handle] = make_brain(with_importance=imp)
        if imp:
            importance_group.add(handle)

    log.info(f"[WORLD] A/B test: IMPORTANCE for {sorted(importance_group)}")
    log.info(f"[WORLD] A/B test: CONTROL for {sorted(set(brains.keys()) - importance_group)}")
    for handle in brains:
        if handle not in saved_groups:
            group = "importance" if handle in importance_group else "control"
            events.log(handle, "ab_group", {"group": group})

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
        was_imp = dead_entity_id in importance_group
        if was_imp:
            importance_group.discard(dead_entity_id)
            importance_group.add(handle)
        brains[handle] = make_brain(with_importance=was_imp)
        group_label = "IMP" if was_imp else "CTL"
        log.info(f"[{handle}] spawned as {role} (replacing {dead_entity_id}, {group_label})")

    # --- Load brain states ---
    for handle, brain in brains.items():
        data = world.load_raw(handle, "brain_state")
        if data:
            brain.load_state(data)
            log.info(f"[{handle}] loaded brain state")

    async def think_then_act(handle):
        start = time.monotonic()
        brain = brains[handle]
        percept = perception.build(handle, world)
        decisions = await brain.think(percept)
        world.set(handle, PendingActions(entries=decisions))

        feedback_entries = []
        for decision in decisions:
            result = registry.execute(handle, decision.action, decision.args, world)
            feedback_entries.append(
                ActionResult(action=decision.action, args=decision.args, result=result)
            )
        world.set(handle, ActionFeedback(entries=feedback_entries))
        log.info(f"[{handle}] tick {tick_number.value} took {time.monotonic() - start:.1f}s")

    scheduler = Scheduler(bus=event_bus)

    loop = TickLoop(scheduler=scheduler, event_bus=event_bus, world=world)
    for system in [DecaySystem(), TaxSystem(), SpoilageSystem(), DeathSystem(on_death=on_death), world_events]:
        loop.add_pre_system(system)
    loop.add_post_system(ConsumptionSystem())

    def persist():
        world.flush()
        world.save_metadata("tick", {"value": tick_number.value})
        for h in brains:
            world.save_raw(h, "brain_state", brains[h].save_state())

    loop.on_persist = persist

    tick_number = world.get_resource(TickNumber)
    tick_data = storage.load_component("_meta", "tick")
    if tick_data:
        tick_number.value = tick_data["value"]

    asyncio.create_task(
        process_commands(
            world,
            brains=brains,
            brain_factory=make_brain,
        )
    )

    while True:
        config.reload()
        await wait_for_llm(clients[0])
        tick_start = time.monotonic()

        tick_number.value += 1
        storage.save_component("_meta", "tick", {"value": tick_number.value})

        entities = set(world.entities())
        handles = sorted(h for h in brains if h in entities)
        registry.begin_tick(world, handles)

        await loop.tick(handles, think_then_act)

        log.info(f"[WORLD] tick {tick_number.value} completed in {time.monotonic() - tick_start:.1f}s")
