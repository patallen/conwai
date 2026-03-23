"""
Cognitive workbench: minimal scenario for testing cognitive pipeline changes.

Usage:
    uv run python -m scenarios.workbench.runner [--model MODEL] [--base-url URL] [--agents N]

Commands:
    (any text)          — broadcast as WORLD, then tick
    @HANDLE message     — send DM to HANDLE from WORLD, then tick
    !tick [N]           — advance N ticks silently
    !inspect [HANDLE]   — show agent state (defaults to first agent)
    !memory [HANDLE]    — show diary + recent summaries
    !brain [HANDLE]     — dump raw brain state
    !agents             — list all agents
    !quit               — exit
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from faker import Faker

from conwai.actions import PendingActions, ActionFeedback
from conwai.bulletin_board import BulletinBoard
from conwai.brain import Brain
from conwai.embeddings import FastEmbedder
from conwai.engine import ActionSystem, BrainSystem, Engine, TickNumber
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.storage import SQLiteStorage
from conwai.world import World
from scenarios.bread_economy.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
    MemoryRecall,
)
from conwai.processes.types import Episodes, WorkingMemory
from scenarios.workbench.actions import create_registry
from scenarios.workbench.components import AgentInfo
from scenarios.workbench.perception import WorkbenchPerceptionBuilder

log = logging.getLogger("conwai")


def setup_logging():
    log.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(h)


async def run(args):
    data_dir = args.data_dir
    storage = SQLiteStorage(path=data_dir / "state.db")

    # --- World ---
    world = World(storage=storage)
    world.register(AgentInfo)
    world.register(PendingActions)
    world.register(ActionFeedback)

    # --- Infrastructure ---
    board = BulletinBoard(storage=storage)
    bus = MessageBus(storage=storage)
    events = EventLog(path=data_dir / "events.db")
    perception = WorkbenchPerceptionBuilder()

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

    system_prompt = (Path(__file__).parent / "prompts" / "system.md").read_text()

    def make_brain() -> Brain:
        return Brain(
            processes=[
                MemoryCompression(
                    recent_ticks=16,
                    embedder=embedder,
                ),
                MemoryRecall(recall_limit=5, embedder=embedder),
                ContextAssembly(
                    context_window=10_000,
                    system_prompt=system_prompt,
                ),
                InferenceProcess(client=client, tools=registry.tool_definitions()),
            ],
            state_types=[WorkingMemory, Episodes],
        )

    # Load or create agents
    fake = Faker()

    brains: dict[str, Brain] = {}
    loaded_handles = list(storage.list_entities())
    for handle in loaded_handles:
        if handle in set(world.entities()):
            brains[handle] = make_brain()

    existing_handles = set(world.entities())
    for _ in range(len(brains), args.agents):
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        world.spawn(handle, overrides=[AgentInfo(role="", personality="observant, adaptive")])
        brains[handle] = make_brain()

    bus.register("WORLD")

    brain_system = BrainSystem(brains=brains, perception=perception.build)
    brain_system.load_brain_states(world)
    action_system = ActionSystem(actions=registry)

    engine = Engine(world, systems=[brain_system, action_system])

    tick_number = world.get_resource(TickNumber)
    tick_data = storage.load_component("_meta", "tick")
    if tick_data:
        tick_number.value = tick_data["value"]

    agent_names = sorted(brains.keys())
    print(f"\n  Agents: {', '.join(f'@{h}' for h in agent_names)}")
    print(f"  Model:  {args.model}")
    print(f"  Tick:   {tick_number.value}")
    print("  Type anything to broadcast, @HANDLE for DM, !help for commands\n")

    while True:
        try:
            import readline  # noqa: F401 — enables line editing
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
        elif line == "!agents":
            for eid in world.entities():
                info = world.get(eid, AgentInfo)
                print(f"  @{eid} — {info.personality}")
            continue
        elif line.startswith("!inspect"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if not world.has(handle, AgentInfo):
                print(f"  unknown agent: {handle}")
                continue
            info = world.get(handle, AgentInfo)
            print(f"\n  @{handle}")
            print(f"  Role: {info.role or '(none)'}")
            print(f"  Personality: {info.personality or '(none)'}")
            print()
            continue
        elif line.startswith("!memory"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if handle not in brains:
                print(f"  unknown agent: {handle}")
                continue
            brain = brains[handle]
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
        elif line.startswith("!brain"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if handle not in brains:
                print(f"  unknown agent: {handle}")
                continue
            dumped = json.dumps(brains[handle].save_state(), indent=2)
            print(dumped[:3000])
            if len(dumped) > 3000:
                print("...")
            continue
        elif line.startswith("!tick"):
            parts = line.split()
            n = int(parts[1]) if len(parts) > 1 else 1
            for _ in range(n):
                storage.save_component("_meta", "tick", {"value": tick_number.value + 1})
                await engine.tick()
            print(f"  advanced to tick {tick_number.value}")
            continue
        elif line.startswith("@"):
            # DM to a specific agent from WORLD
            parts = line.split(" ", 1)
            to_handle = parts[0][1:]
            msg = parts[1] if len(parts) > 1 else ""
            err = bus.send("WORLD", to_handle, msg)
            if err:
                print(f"  DM failed: {err}")
            else:
                events.log("WORLD", "dm_sent", {"to": to_handle, "content": msg})
                print(f"  [WORLD] -> [@{to_handle}]: {msg}")
        else:
            board.post("WORLD", line)
            events.log("WORLD", "broadcast", {"content": line})
            print(f"  [WORLD]: {line}")

        # Auto-tick after input
        storage.save_component("_meta", "tick", {"value": tick_number.value + 1})
        await engine.tick()


def main():
    parser = argparse.ArgumentParser(description="Cognitive workbench")
    parser.add_argument("--model", default="/mnt/models/Qwen3.5-27B-GPTQ-Int4")
    parser.add_argument("--base-url", default="http://ai-lab.lan:8081/v1")
    parser.add_argument("--agents", type=int, default=1)
    parser.add_argument("--data-dir", default="data/workbench", type=Path)
    args = parser.parse_args()

    args.data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
