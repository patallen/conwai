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

from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition import BlackboardBrain
from conwai.embeddings import FastEmbedder
from conwai.engine import BrainPhase, Engine
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.bread_economy.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
    MemoryRecall,
)
from scenarios.workbench.actions import create_registry
from scenarios.workbench.components import AgentInfo, BrainState
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

    store = ComponentStore(storage=storage)
    store.register(AgentInfo)
    store.register(BrainState)
    store.load_all()

    board = BulletinBoard(storage=storage)
    bus = MessageBus(storage=storage)
    events = EventLog(path=data_dir / "events.db")
    perception = WorkbenchPerceptionBuilder()

    repo = AgentRepository(storage=storage)
    pool = AgentPool(repo, store, bus=bus)

    client = LLMClient(
        base_url=args.base_url,
        model=args.model,
        max_tokens=2048,
    )

    embedder = FastEmbedder()

    registry = create_registry()

    system_prompt = (Path(__file__).parent / "prompts" / "system.md").read_text()

    def make_brain() -> BlackboardBrain:
        return BlackboardBrain(
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
        )

    # Load or create agents
    fake = Faker()

    brains: dict[str, BlackboardBrain] = {}
    loaded_handles = list(repo.list_handles())
    for handle in loaded_handles:
        agent = pool.load_or_create(Agent(handle=handle))
        if agent.alive:
            brains[agent.handle] = make_brain()

    existing_handles = {a.handle for a in pool.all()}
    for _ in range(len(brains), args.agents):
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        agent = pool.load_or_create(
            Agent(handle=handle, born_tick=0),
            component_overrides=[AgentInfo(role="", personality="observant, adaptive")],
        )
        brains[agent.handle] = make_brain()

    bus.register("WORLD")

    brain_phase = BrainPhase(actions=registry, brains=brains, perception=perception)

    engine = Engine(
        pool=pool, store=store, perception=perception,
        board=board, bus=bus, events=events,
    )
    engine.add_phase(brain_phase)

    tick_data = storage.load_component("WORLD", "tick")
    tick = tick_data["value"] if tick_data else 0

    agent_names = sorted(brains.keys())
    print(f"\n  Agents: {', '.join(f'@{h}' for h in agent_names)}")
    print(f"  Model:  {args.model}")
    print(f"  Tick:   {tick}")
    print(f"  Type anything to broadcast, @HANDLE for DM, !help for commands\n")

    while True:
        try:
            import readline  # noqa: F401 — enables line editing
            line = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input(f"[tick {tick}] > ")
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
            for a in pool.alive():
                info = store.get(a.handle, AgentInfo)
                print(f"  @{a.handle} — {info.personality}")
            continue
        elif line.startswith("!inspect"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if not store.has(handle, AgentInfo):
                print(f"  unknown agent: {handle}")
                continue
            info = store.get(handle, AgentInfo)
            print(f"\n  @{handle}")
            print(f"  Role: {info.role or '(none)'}")
            print(f"  Personality: {info.personality or '(none)'}")
            print()
            continue
        elif line.startswith("!memory"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if not store.has(handle, BrainState):
                print(f"  unknown agent: {handle}")
                continue
            brain_state = store.get(handle, BrainState)
            summaries = [e for e in brain_state.working_memory if e.get("kind") == "tick_summary"]
            print(f"\n  === RECENT SUMMARIES ({len(summaries)}) ===")
            for s in summaries[-5:]:
                print(f"  {s['content'][:120]}")
            print(f"\n  === EPISODES ({len(brain_state.episodes)} entries) ===")
            for d in brain_state.episodes[-10:]:
                print(f"  {d['content'][:120]}")
                if d.get("embedding"):
                    print(f"    [embedded, {len(d['embedding'])} dims]")
            print()
            continue
        elif line.startswith("!brain"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if not store.has(handle, BrainState):
                print(f"  unknown agent: {handle}")
                continue
            brain_state = store.get(handle, BrainState)
            dumped = json.dumps(brain_state.to_dict(), indent=2)
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
        tick += 1
        storage.save_component("WORLD", "tick", {"value": tick})
        await engine.tick(tick)


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
