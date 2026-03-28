"""
Single-agent test harness for memory research.

Spawns one agent with the full brain pipeline (compression, recall, context,
inference, strategic review). You interact by injecting board posts, DMs,
and world events, then ticking the simulation.

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
import json
import logging
import sys

from conwai.actions import ActionFeedback, ActionResult, PendingActions
from conwai.brain import Brain
from conwai.comm import BulletinBoard, MessageBus
from conwai.llm import FastEmbedder, LLMClient
from conwai.events import EventBus, EventLog
from conwai.scheduler import TickNumber
from conwai.processes.types import Episodes, WorkingMemory
from conwai.scheduler import Scheduler
from conwai.tick_loop import TickLoop
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

    # --- World ---
    event_bus = EventBus()
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
    board = BulletinBoard(storage=storage)
    bus = MessageBus(storage=storage)
    events = EventLog(path=args.data_dir / "events.db")
    perception = make_bread_perception()

    world.set_resource(board)
    world.set_resource(bus)
    world.set_resource(events)
    world.set_resource(perception)
    world.set_resource(TickNumber(value=0))

    # --- Load persisted state ---
    world.load_all()

    client = LLMClient(
        base_url=args.base_url,
        model=args.model,
        max_tokens=2048,
    )

    embedder = FastEmbedder()

    registry = create_registry()
    world.set_resource(registry)

    handle = args.handle

    # Load or create the test agent
    if handle not in set(world.entities()):
        world.spawn(
            handle,
            overrides=[
                AgentInfo(role="flour_forager", personality="skeptical, calculating")
            ],
        )

    bus.register(handle)
    bus.register("WORLD")
    bus.register("HANDLER")

    # Register some fake agents for the agent to interact with
    for fake_name in ["Christopher", "Bridget", "Matthew", "Angel", "Debra"]:
        if fake_name not in set(world.entities()):
            world.spawn(
                fake_name,
                overrides=[
                    AgentInfo(role="water_forager", personality="blunt, detached")
                ],
            )

    brain = Brain(
        processes=[
            StrategicReview(client=client, store=world, interval=24),
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
            InferenceProcess(client=client, tools=tool_definitions()),
        ],
        state_types=[WorkingMemory, Episodes],
    )

    scheduler = Scheduler(bus=event_bus)

    async def think_then_act_single(_handle: str):
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

    loop = TickLoop(scheduler=scheduler, event_bus=event_bus, world=world)
    loop.add_pre_system(DecaySystem())
    loop.add_post_system(ConsumptionSystem())

    def persist():
        world.flush()
        world.save_raw(handle, "brain_state", brain.save_state())

    loop.on_persist = persist

    # Load brain state
    data = world.load_raw(handle, "brain_state")
    if data:
        brain.load_state(data)
        log.info(f"[{handle}] loaded brain state")

    async def do_tick():
        tick_number.value += 1
        storage.save_component("_meta", "tick", {"value": tick_number.value})
        await loop.tick([handle], think_then_act_single)

    tick_number = world.get_resource(TickNumber)
    tick_data = storage.load_component("_meta", "tick")
    if tick_data:
        tick_number.value = tick_data["value"]

    print(f"\n  Agent: @{handle}")
    print(f"  Model: {args.model}")
    print(f"  Tick:  {tick_number.value}")
    print("  Fake agents: Christopher, Bridget, Matthew, Angel, Debra")
    print("  Type anything to post to board, or !help for commands\n")

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input(f"[tick {tick_number.value}] > ")
            )
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
                    inv = world.get(handle, Inventory)
                    setattr(inv, key, val)
                elif key == "coins":
                    eco = world.get(handle, Economy)
                    eco.coins = val
                elif key in ("hunger", "thirst"):
                    hun = world.get(handle, Hunger)
                    setattr(hun, key, val)
                print(f"  {key} = {val}")
            continue
        elif line == "!rich":
            world.set(handle, Inventory(flour=80, water=80, bread=30))
            world.set(handle, Economy(coins=500))
            world.set(handle, Hunger(hunger=100, thirst=100))
            print("  set: 80 flour, 80 water, 30 bread, 500 coins, full hunger/thirst")
            continue
        elif line == "!inspect":
            eco = world.get(handle, Economy)
            inv = world.get(handle, Inventory)
            hun = world.get(handle, Hunger)
            mem = world.get(handle, AgentMemory)
            print(f"\n  @{handle}")
            print(
                f"  Coins: {int(eco.coins)}  Hunger: {hun.hunger}  Thirst: {hun.thirst}"
            )
            print(f"  Flour: {inv.flour}  Water: {inv.water}  Bread: {inv.bread}")
            print(f"  Soul: {mem.soul or '(none)'}")
            print(f"  Journal: {mem.memory or '(none)'}")
            print(f"  Strategy: {mem.strategy or '(none)'}")
            print()
            continue
        elif line == "!memory":
            wm = brain.state.get(WorkingMemory)
            eps = brain.state.get(Episodes)
            if wm:
                summaries = [e for e in wm.entries if e.kind == "tick_summary"]
                print(f"\n  === RECENT SUMMARIES ({len(summaries)}) ===")
                for s in summaries[-5:]:
                    print(f"  {s.content[:120]}")
            if eps:
                print(f"\n  === EPISODES ({len(eps.entries)} entries) ===")
                for ep in eps.entries[-10:]:
                    print(f"  {ep.content[:120]}")
                    if ep.embedding:
                        print(f"    [embedded, {len(ep.embedding)} dims]")
            print()
            continue
        elif line == "!strategy":
            mem = world.get(handle, AgentMemory)
            print(f"\n  {mem.strategy or '(no strategy yet)'}\n")
            continue
        elif line == "!brain":
            dumped = json.dumps(brain.save_state(), indent=2)
            print(dumped[:3000])
            if len(dumped) > 3000:
                print("...")
            continue
        elif line.startswith("!tick"):
            parts = line.split()
            n = int(parts[1]) if len(parts) > 1 else 1
            for _ in range(n):
                await do_tick()
            print(f"  advanced to tick {tick_number.value}")
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
        await do_tick()


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
