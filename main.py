import asyncio
import logging
import os
import time
from pathlib import Path

from conwai.agent import Agent
from conwai.config import ENERGY_GAIN, ENERGY_MAX, assign_traits
import conwai.config as config
from conwai.bulletin_board import BulletinBoard
from conwai.default_actions import create_registry
from conwai.engine import Engine
from conwai.events import EventLog
from conwai.brain import LLMBrain
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.perception import Perception
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.store import ComponentStore
from conwai.systems.consumption import ConsumptionSystem
from conwai.systems.death import DeathSystem
from conwai.systems.decay import DecaySystem
from conwai.systems.spoilage import SpoilageSystem
from conwai.systems.tax import TaxSystem
from conwai.world import WorldEvents
from conwai.infra.logging import setup_logging

log = logging.getLogger("conwai")

HANDLER_FILE = Path("handler_input.txt")


async def watch_handler_file(pool, store, board, bus, events, perception):
    """Process admin commands from the handler file. Used by dashboard."""
    if not HANDLER_FILE.exists():
        HANDLER_FILE.write_text("")
    last_size = 0
    while True:
        current_size = HANDLER_FILE.stat().st_size
        if current_size > last_size:
            content = HANDLER_FILE.read_text()
            new_content = content[last_size:]
            for line in new_content.strip().splitlines():
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
            last_size = current_size
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

    # --- Infrastructure ---
    board = BulletinBoard(max_posts=config.BOARD_MAX_POSTS, max_post_length=config.BOARD_MAX_POST_LENGTH)
    bus = MessageBus()
    events = EventLog()
    perception = Perception()

    # --- Persistence ---
    repo = AgentRepository()
    pool = AgentPool(repo, bus, store)

    # --- LLM clients ---
    b200 = LLMClient(
        base_url="https://cq2qdgtb5xh2ap-8000.proxy.runpod.net/v1",
        model="Qwen/Qwen3.5-122B-A10B-GPTQ-Int4", max_tokens=512,
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
    registry = create_registry(store=store, board=board, bus=bus, events=events, pool=pool, perception=perception, world=world)

    # --- Agents + Brains ---
    brains: dict[str, object] = {}
    roles = ["flour_forager"] * 8 + ["water_forager"] * 8 + ["baker"] * 4

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
            compaction_prompt=compaction_prompt,
        )

    for i, role in enumerate(roles, 1):
        agent = Agent(handle=f"A{i}", role=role, born_tick=0, personality=", ".join(assign_traits()))
        agent = pool.load_or_create(agent)
        if agent.alive:
            brain = make_brain()
            saved_state = pool.load_brain_state(agent.handle)
            if saved_state:
                brain.load_state(saved_state)
            brains[agent.handle] = brain

    bus.register("HANDLER")
    bus.register("WORLD")

    # --- Death system needs brain factory ---
    def on_spawn(agent):
        brain = make_brain()
        brains[agent.handle] = brain

    # --- Engine ---
    engine = Engine(
        pool=pool, store=store, perception=perception,
        actions=registry, brains=brains, board=board, bus=bus,
    )
    engine.register_pre_brain(DecaySystem())
    engine.register_pre_brain(TaxSystem())
    engine.register_pre_brain(SpoilageSystem())
    engine.register_pre_brain(DeathSystem(pool=pool, board=board, events=events, on_spawn=on_spawn))
    engine.register_pre_brain(world)
    engine.register_post_brain(ConsumptionSystem())

    asyncio.create_task(watch_handler_file(pool, store, board, bus, events, perception))

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
