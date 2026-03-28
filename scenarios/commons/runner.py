"""Runner for the commons scenario."""
import asyncio
import logging
import random
import time
from pathlib import Path

from faker import Faker

import scenarios.commons.config as config
from conwai.actions import ActionFeedback, PendingActions, WorldActionAdapter
from conwai.brain import PipelineBrain, Process
from conwai.comm import BulletinBoard, MessageBus
from conwai.events import ActionExecuted, EventBus, EventLog
from conwai.scheduler import Scheduler, TickNumber
from conwai.llm import LLMClient
from conwai.processes.types import Episodes, WorkingMemory
from conwai.storage import SQLiteStorage
from conwai.world import World
from scenarios.commons.actions import create_registry, tool_definitions
from scenarios.commons.components import AgentInfo, AgentMemory, FishHaul
from scenarios.commons.config import get_config
from scenarios.commons.perception import make_commons_perception
from scenarios.commons.systems import Pond, PondSystem
from conwai.processes.activation_recall import ActivationRecall
from conwai.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
)
from conwai.tick_loop import TickLoop

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

    adapter = WorldActionAdapter(world=world, registry=registry)

    # --- Embedder ---
    from conwai.llm import FastEmbedder
    log.info("[WORLD] loading embedding model...")
    embedder = FastEmbedder()
    log.info("[WORLD] embedding model ready")

    # --- Brain pipeline ---
    def make_brain() -> PipelineBrain:
        client = clients[0]
        processes: list[Process] = [
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
        return PipelineBrain(processes=processes, adapter=adapter, state_types=[WorkingMemory, Episodes])

    # --- Agents ---
    brains: dict[str, PipelineBrain] = {}
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

    # --- Load brain states ---
    for handle, brain in brains.items():
        data = world.load_raw(handle, "brain_state")
        if data:
            brain.load_state(data)
            log.info(f"[{handle}] loaded brain state")

    async def on_tick(handle):
        start = time.monotonic()
        tick = world.get_resource(TickNumber)
        percept = perception.build(handle, world)
        brains[handle].perceive(percept, scheduler, handle)
        log.info(f"[{handle}] tick {tick.value} scheduled in {time.monotonic() - start:.3f}s")

    # --- Scheduler ---
    scheduler = Scheduler(bus=event_bus, default_cost=cfg.activation_cost)

    # DM re-triggering
    def on_action(event):
        if event.action == "send_message":
            target = event.args.get("to", "").lstrip("@")
            if target in brains:
                async def retrigger(h=target):
                    percept = perception.build(h, world)
                    brains[h].perceive(percept, scheduler, h)
                scheduler.schedule(target, retrigger, cost=cfg.retrigger_cost)

    event_bus.subscribe(ActionExecuted, on_action)

    # --- TickLoop ---
    loop = TickLoop(scheduler=scheduler, event_bus=event_bus, world=world)
    loop.add_pre_system(PondSystem())

    def persist():
        world.flush()
        for handle in brains:
            world.save_raw(handle, "brain_state", brains[handle].save_state())

    loop.on_persist = persist

    # --- Run loop ---
    tick_number = world.get_resource(TickNumber)
    tick_data = storage.load_component("_meta", "tick")
    if tick_data:
        tick_number.value = tick_data["value"]

    while tick_number.value < cfg.max_ticks:
        config.reload()
        await wait_for_llm(clients[0])
        tick_start = time.monotonic()

        tick_number.value += 1
        storage.save_component("_meta", "tick", {"value": tick_number.value})

        entities = set(world.entities())
        handles = sorted(h for h in brains if h in entities)
        registry.begin_tick(world, handles)

        await loop.tick(handles, on_tick)

        # Log
        pond_pop = int(pond.population)
        scores = [(fh.fish, eid) for eid, fh in world.query(FishHaul)]
        scores.sort(reverse=True)
        top = ", ".join(f"{name}:{fish}" for fish, name in scores[:3])
        log.info(
            f"[WORLD] tick {tick_number.value} done in {time.monotonic() - tick_start:.1f}s | "
            f"pond: {pond_pop}/{int(pond.capacity)} | top: {top}"
        )

    # Final results
    log.info("=== SIMULATION COMPLETE ===")
    scores = [(fh.fish, eid) for eid, fh in world.query(FishHaul)]
    scores.sort(reverse=True)
    for rank, (fish, name) in enumerate(scores, 1):
        log.info(f"  #{rank} @{name}: {fish} fish")
    log.info(f"  Pond final population: {int(pond.population)}/{int(pond.capacity)}")
