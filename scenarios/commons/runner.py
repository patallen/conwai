"""Runner for the commons scenario."""
import asyncio
import logging
import random
import time
from pathlib import Path

from faker import Faker

import scenarios.commons.config as config
from conwai.actions import ActionFeedback, PendingActions
from conwai.brain import Brain
from conwai.bulletin_board import BulletinBoard
from conwai.scheduler import SchedulerSystem
from conwai.engine import Engine, TickNumber
from conwai.event_bus import EventBus
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.processes.types import Episodes, WorkingMemory
from conwai.storage import SQLiteStorage
from conwai.world import World
from scenarios.commons.actions import create_registry, tool_definitions
from scenarios.commons.components import AgentInfo, AgentMemory, FishHaul
from scenarios.commons.config import get_config
from scenarios.commons.perception import CommonsPerceptionBuilder, make_commons_perception
from scenarios.commons.systems import Pond, PondSystem
from conwai.processes.activation_recall import ActivationRecall
from conwai.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
)

log = logging.getLogger("conwai")


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
    """Run the commons scenario."""
    cfg = get_config()

    fake = Faker()
    if cfg.seed is not None:
        random.seed(cfg.seed)
        Faker.seed(cfg.seed)
        log.info(f"[WORLD] random seed: {cfg.seed}")

    # --- Storage ---
    storage = SQLiteStorage(path=Path("data/commons.db"))

    # --- Event bus ---
    event_bus = EventBus()

    # --- World ---
    world = World(storage=storage, bus=event_bus)
    world.register(FishHaul, FishHaul())
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
    perception = make_commons_perception()

    pond = Pond(
        population=cfg.pond_starting_population,
        capacity=cfg.pond_capacity,
        growth_rate=cfg.pond_growth_rate,
        collapse_threshold=cfg.pond_collapse_threshold,
    )

    # Register resources
    world.set_resource(board)
    world.set_resource(bus)
    world.set_resource(events)
    world.set_resource(perception)
    world.set_resource(pond)
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

    # --- Actions ---
    registry = create_registry()
    world.set_resource(registry)

    # --- Embedder ---
    from conwai.embeddings import FastEmbedder
    log.info("[WORLD] loading embedding model...")
    embedder = FastEmbedder()
    log.info("[WORLD] embedding model ready")

    # --- Brain pipeline ---
    def make_brain() -> Brain:
        client = clients[0]
        processes = [
            MemoryCompression(
                recent_ticks=16,
                embedder=embedder,
                noise_actions={"rest"},
            ),
            ActivationRecall(
                recall_limit=5, reflection_limit=5, embedder=embedder,
            ),
            ContextAssembly(
                context_window=cfg.context_window,
                system_prompt=perception.build_system_prompt(),
            ),
            InferenceProcess(
                client=client,
                tools=tool_definitions(),
            ),
        ]
        return Brain(processes=processes, state_types=[WorkingMemory, Episodes])

    # --- Agents ---
    brains: dict[str, Brain] = {}
    loaded_handles = list(storage.list_entities())
    for handle in loaded_handles:
        if handle in set(world.entities()):
            brains[handle] = make_brain()

    existing_handles = set(world.entities())
    for i in range(len(existing_handles), cfg.agent_count):
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        world.spawn(handle, overrides=[AgentInfo(role="fisher", personality=cfg.personality)])
        brains[handle] = make_brain()

    for handle in brains:
        bus.register(handle)
    bus.register("WORLD")

    # --- Trigger function ---
    def dm_trigger(result):
        """Re-trigger DM recipients within a tick."""
        if result.action == "send_message":
            target = result.args.get("to", "").lstrip("@")
            if target:
                return [target]
        return []

    # --- Scheduler ---
    scheduler = SchedulerSystem(
        brains=brains,
        perception=perception.build,
        actions=registry,
        resolution=cfg.tick_resolution,
        think_cost=cfg.think_cost,
        retrigger_cost=cfg.retrigger_cost,
        trigger_fn=dm_trigger if cfg.tick_resolution > 1 else None,
    )
    scheduler.load_brain_states(world)

    # --- Engine ---
    engine = Engine(
        world,
        systems=[
            PondSystem(),
            scheduler,
        ],
    )

    # --- Tick loop ---
    tick_number = world.get_resource(TickNumber)
    tick_data = storage.load_component("_meta", "tick")
    if tick_data:
        tick_number.value = tick_data["value"]

    while tick_number.value < cfg.max_ticks:
        config.reload()
        await wait_for_llm(clients[0])
        tick_start = time.monotonic()
        storage.save_component("_meta", "tick", {"value": tick_number.value + 1})
        await engine.tick()

        # Log summary
        pond_pop = int(pond.population)
        scores = [(fh.fish, eid) for eid, fh in world.query(FishHaul)]
        scores.sort(reverse=True)
        top = ", ".join(f"{name}:{fish}" for fish, name in scores[:3])
        log.info(
            f"[WORLD] tick {tick_number.value} done in {time.monotonic() - tick_start:.1f}s | "
            f"pond: {pond_pop}/{int(pond.capacity)} | top: {top}"
        )

    # --- Final results ---
    log.info("=== SIMULATION COMPLETE ===")
    scores = [(fh.fish, eid) for eid, fh in world.query(FishHaul)]
    scores.sort(reverse=True)
    for rank, (fish, name) in enumerate(scores, 1):
        log.info(f"  #{rank} @{name}: {fish} fish")
    log.info(f"  Pond final population: {int(pond.population)}/{int(pond.capacity)}")
