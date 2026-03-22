"""
Single-agent test harness for memory research.

Spawns one agent with the full brain pipeline (compression, recall, context,
inference, strategic review). You interact by injecting board posts, DMs,
and world events, then ticking the engine.

Usage:
    uv run python harness.py [--model MODEL] [--base-url URL] [--handle NAME]

Commands:
    (any text)          — post to board as WORLD, then tick
    @HANDLE message     — simulate a DM from HANDLE to the agent, then tick
    !tick [N]           — advance N ticks (default 1) silently
    !set KEY VALUE      — set a resource (flour, water, bread, coins, hunger, thirst)
    !rich               — shortcut: 80 flour, 80 water, 30 bread, 500 coins, full health
    !inspect            — show agent's full state
    !memory             — show diary + recalled memories
    !strategy           — show current strategy
    !brain              — dump raw brain state
    !quit               — exit
"""

import argparse
import asyncio
import logging
import sys

from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition import BlackboardBrain
from conwai.embeddings import FastEmbedder
from conwai.engine import BrainPhase, Engine, TickContext
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
from scenarios.bread_economy.config import get_config
from scenarios.bread_economy.perception import make_bread_perception, tick_to_timestamp
from scenarios.bread_economy.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
    MemoryRecall,
)
from scenarios.bread_economy.processes.review import StrategicReview
from scenarios.bread_economy.systems import ConsumptionSystem, DecaySystem

log = logging.getLogger("conwai")


def setup_logging():
    log.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(h)


async def run(args):
    cfg = get_config()

    storage = SQLiteStorage(path=args.data_dir / "state.db")

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
    store.load_all()

    board = BulletinBoard(storage=storage)
    bus = MessageBus(storage=storage)
    events = EventLog(path=args.data_dir / "events.db")
    perception = make_bread_perception()

    repo = AgentRepository(storage=storage)
    pool = AgentPool(repo, store, bus=bus)

    client = LLMClient(
        base_url=args.base_url,
        model=args.model,
        max_tokens=2048,
    )

    embedder = FastEmbedder()

    registry = create_registry()

    handle = args.handle
    if repo.exists(handle):
        agent = pool.load_or_create(Agent(handle=handle))
    else:
        agent = Agent(handle=handle, born_tick=0)
        pool.load_or_create(
            agent,
            component_overrides=[AgentInfo(role="flour_forager", personality="skeptical, calculating")],
        )

    bus.register(handle)
    bus.register("WORLD")
    bus.register("HANDLER")

    # Register some fake agents for the agent to interact with
    for fake_name in ["Christopher", "Bridget", "Matthew", "Angel", "Debra"]:
        fake_agent = Agent(handle=fake_name)
        pool.load_or_create(
            fake_agent,
            component_overrides=[AgentInfo(role="water_forager", personality="blunt, detached")],
        )

    brain = BlackboardBrain(
        processes=[
            StrategicReview(client=client, store=store, interval=24),
            MemoryCompression(
                recent_ticks=16,
                timestamp_formatter=tick_to_timestamp,
                embedder=embedder,
                noise_actions={"update_journal", "wait"},
            ),
            MemoryRecall(recall_limit=5, embedder=embedder),
            ContextAssembly(
                context_window=cfg.context_window,
                system_prompt=perception.build_system_prompt(),
            ),
            InferenceProcess(client=client, tools=registry.tool_definitions()),
        ],
    )

    brains = {handle: brain}
    brain_phase = BrainPhase(actions=registry, brains=brains, perception=perception)

    engine = Engine(
        pool=pool, store=store, perception=perception,
        board=board, bus=bus, events=events,
    )
    engine.add_phase(DecaySystem())
    engine.add_phase(brain_phase)
    engine.add_phase(ConsumptionSystem())

    tick_data = storage.load_component("WORLD", "tick")
    tick = tick_data["value"] if tick_data else 0

    print(f"\n  Agent: @{handle}")
    print(f"  Model: {args.model}")
    print(f"  Tick:  {tick}")
    print(f"  Fake agents: Christopher, Bridget, Matthew, Angel, Debra")
    print(f"  Type anything to post to board, or !help for commands\n")

    while True:
        try:
            import readline  # noqa: F811 — enables line editing in input()
            line = await asyncio.get_event_loop().run_in_executor(None, lambda: input(f"[tick {tick}] > "))
        except (EOFError, KeyboardInterrupt):
            break

        line = line.strip()
        if not line:
            continue

        if line == "!quit":
            break
        elif line == "!help":
            print(__doc__)
            continue
        elif line.startswith("!set "):
            parts = line.split()
            if len(parts) >= 3:
                key, val = parts[1], int(parts[2])
                if key in ("flour", "water", "bread"):
                    inv = store.get(handle, Inventory)
                    setattr(inv, key, val)
                    store.set(handle, inv)
                elif key == "coins":
                    eco = store.get(handle, Economy)
                    eco.coins = val
                    store.set(handle, eco)
                elif key in ("hunger", "thirst"):
                    hun = store.get(handle, Hunger)
                    setattr(hun, key, val)
                    store.set(handle, hun)
                print(f"  {key} = {val}")
            continue
        elif line == "!rich":
            store.set(handle, Inventory(flour=80, water=80, bread=30))
            store.set(handle, Economy(coins=500))
            store.set(handle, Hunger(hunger=100, thirst=100))
            print("  set: 80 flour, 80 water, 30 bread, 500 coins, full hunger/thirst")
            continue
        elif line == "!inspect":
            eco = store.get(handle, Economy)
            inv = store.get(handle, Inventory)
            hun = store.get(handle, Hunger)
            mem = store.get(handle, AgentMemory)
            print(f"\n  @{handle}")
            print(f"  Coins: {int(eco.coins)}  Hunger: {hun.hunger}  Thirst: {hun.thirst}")
            print(f"  Flour: {inv.flour}  Water: {inv.water}  Bread: {inv.bread}")
            print(f"  Soul: {mem.soul or '(none)'}")
            print(f"  Journal: {mem.memory or '(none)'}")
            print(f"  Strategy: {mem.strategy or '(none)'}")
            print()
            continue
        elif line == "!memory":
            bs = store.get(handle, BrainState)
            summaries = [e for e in bs.working_memory if e.get("kind") == "tick_summary"]
            print(f"\n  === RECENT SUMMARIES ({len(summaries)}) ===")
            for s in summaries[-5:]:
                print(f"  {s['content'][:120]}")
            print(f"\n  === EPISODES ({len(bs.episodes)} entries) ===")
            for d in bs.episodes[-10:]:
                print(f"  {d['content'][:120]}")
                if d.get("embedding"):
                    print(f"    [embedded, {len(d['embedding'])} dims]")
            print()
            continue
        elif line == "!strategy":
            mem = store.get(handle, AgentMemory)
            print(f"\n  {mem.strategy or '(no strategy yet)'}\n")
            continue
        elif line == "!brain":
            bs = store.get(handle, BrainState)
            import json
            dumped = json.dumps(bs.to_dict(), indent=2)
            print(dumped[:3000])
            if len(dumped) > 3000:
                print("...")
            continue
        elif line.startswith("!tick"):
            parts = line.split()
            n = int(parts[1]) if len(parts) > 1 else 1
            for _ in range(n):
                tick += 1
                storage.save_component("WORLD", "tick", {"value": tick})
                await engine.tick(tick)
            print(f"  advanced to tick {tick}")
            continue
        elif line.startswith("@"):
            # DM from a fake agent to our agent
            parts = line.split(" ", 1)
            from_handle = parts[0][1:]
            msg = parts[1] if len(parts) > 1 else ""
            bus.send(from_handle, handle, msg)
            events.log(from_handle, "dm_sent", {"to": handle, "content": msg})
            print(f"  [{from_handle}] -> [@{handle}]: {msg}")
        else:
            # Post to board as WORLD
            board.post("WORLD", line)
            events.log("WORLD", "board_post", {"content": line})
            print(f"  [WORLD]: {line}")

        # Auto-tick after each input
        tick += 1
        storage.save_component("WORLD", "tick", {"value": tick})
        await engine.tick(tick)


def main():
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Single-agent test harness")
    parser.add_argument("--model", default="/mnt/models/Qwen3.5-9B-AWQ")
    parser.add_argument("--base-url", default="http://ai-lab.lan:8080/v1")
    parser.add_argument("--handle", default="TestAgent")
    parser.add_argument("--data-dir", default="data/harness", type=Path)
    args = parser.parse_args()

    args.data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
