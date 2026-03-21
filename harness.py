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
from conwai.cognition import BlackboardBrain, Brain
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
from scenarios.bread_economy.config import get_config, register_components
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
    store.register_component("economy", {"coins": cfg.starting_coins})
    store.register_component(
        "inventory",
        {"flour": cfg.starting_flour, "water": cfg.starting_water, "bread": cfg.starting_bread},
    )
    store.register_component("hunger", {"hunger": cfg.starting_hunger, "thirst": cfg.starting_thirst})
    store.register_component("memory", {"memory": "", "code_fragment": None, "soul": "", "strategy": ""})
    store.register_component("brain", {"messages": [], "diary": []})
    register_components(store)
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
            component_overrides={
                "agent_info": {"role": "flour_forager", "personality": "skeptical, calculating"}
            },
        )

    bus.register(handle)
    bus.register("WORLD")
    bus.register("HANDLER")

    # Register some fake agents for the agent to interact with
    for fake_name in ["Christopher", "Bridget", "Matthew", "Angel", "Debra"]:
        fake_agent = Agent(handle=fake_name)
        pool.load_or_create(
            fake_agent,
            component_overrides={"agent_info": {"role": "water_forager", "personality": "blunt, detached"}},
        )

    brain = BlackboardBrain(
        processes=[
            StrategicReview(client=client, store=store, interval=24),
            MemoryCompression(
                recent_ticks=16,
                timestamp_formatter=tick_to_timestamp,
                embedder=embedder,
            ),
            MemoryRecall(recall_limit=5, embedder=embedder),
            ContextAssembly(
                context_window=cfg.context_window,
                system_prompt=perception.build_system_prompt(),
            ),
            InferenceProcess(client=client, tools=registry.tool_definitions()),
        ],
        store=store,
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
            # !set flour 80  or  !set coins 500  or  !set hunger 90
            parts = line.split()
            if len(parts) >= 3:
                key, val = parts[1], int(parts[2])
                if key in ("flour", "water", "bread"):
                    inv = store.get(handle, "inventory")
                    inv[key] = val
                    store.set(handle, "inventory", inv)
                elif key == "coins":
                    eco = store.get(handle, "economy")
                    eco["coins"] = val
                    store.set(handle, "economy", eco)
                elif key in ("hunger", "thirst"):
                    hun = store.get(handle, "hunger")
                    hun[key] = val
                    store.set(handle, "hunger", hun)
                print(f"  {key} = {val}")
            continue
        elif line == "!rich":
            # Quick shortcut: give the agent plenty of everything
            store.set(handle, "inventory", {"flour": 80, "water": 80, "bread": 30})
            store.set(handle, "economy", {"coins": 500})
            store.set(handle, "hunger", {"hunger": 100, "thirst": 100})
            print("  set: 80 flour, 80 water, 30 bread, 500 coins, full hunger/thirst")
            continue
        elif line == "!inspect":
            eco = store.get(handle, "economy")
            inv = store.get(handle, "inventory")
            hun = store.get(handle, "hunger")
            mem = store.get(handle, "memory")
            print(f"\n  @{handle}")
            print(f"  Coins: {int(eco['coins'])}  Hunger: {hun['hunger']}  Thirst: {hun['thirst']}")
            print(f"  Flour: {inv['flour']}  Water: {inv['water']}  Bread: {inv['bread']}")
            print(f"  Soul: {mem.get('soul', '(none)')}")
            print(f"  Journal: {mem.get('memory', '(none)')}")
            print(f"  Strategy: {mem.get('strategy', '(none)')}")
            print()
            continue
        elif line == "!memory":
            brain_state = store.get(handle, "brain")
            diary = brain_state.get("diary", [])
            messages = brain_state.get("messages", [])
            summaries = [m for m in messages if m.get("_tick_summary")]
            print(f"\n  === RECENT SUMMARIES ({len(summaries)}) ===")
            for s in summaries[-5:]:
                print(f"  {s['content'][:120]}")
            print(f"\n  === DIARY ({len(diary)} entries) ===")
            for d in diary[-10:]:
                print(f"  {d['content'][:120]}")
                if d.get("embedding"):
                    print(f"    [embedded, {len(d['embedding'])} dims]")
            print()
            continue
        elif line == "!strategy":
            mem = store.get(handle, "memory")
            print(f"\n  {mem.get('strategy', '(no strategy yet)')}\n")
            continue
        elif line == "!brain":
            brain_state = store.get(handle, "brain")
            import json
            print(json.dumps(brain_state, indent=2)[:3000])
            print("..." if len(json.dumps(brain_state)) > 3000 else "")
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
