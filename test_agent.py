"""
Interactive test harness for a single agent.

Usage:
    uv run python test_agent.py [--model MODEL] [--base-url URL]

Spawns one agent, lets you feed it user messages and see what it does.
Type board messages directly, or use:
    !dm HANDLE message    - simulate a DM from HANDLE
    !world message        - simulate a WORLD DM
    !tick                 - tick with no new input
    !energy              - show current energy
    !scratchpad          - show scratchpad
    !soul                - show soul
    !strategy            - show strategy
    !prompt              - show full system prompt
    !quit                - exit
"""

import argparse
import asyncio
from uuid import uuid4

from conwai.agent import Agent
from conwai.brain import LLMBrain
from conwai.default_actions import create_registry
from conwai.engine import Engine
from conwai.app import Context
from conwai.llm import LLMClient
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.systems.brain import BrainSystem
from conwai.systems.consumption import ConsumptionSystem
from conwai.systems.decay import DecaySystem
from conwai.world import WorldEvents

repo = AgentRepository()


async def run(args):
    ctx = Context()
    registry = create_registry()

    client = LLMClient(
        base_url=args.base_url,
        model=args.model,
        extra_body=args.extra_body
        if args.extra_body is not None
        else {"chat_template_kwargs": {"enable_thinking": False}},
    )

    pool = AgentPool(repo, ctx.bus)
    ctx.pool = pool

    handle = args.handle or uuid4().hex[:3]
    agent = Agent(handle=handle)
    agent.brain = LLMBrain(core=client, actions=registry)
    repo.save(agent)
    pool._agents[handle] = agent
    pool._bus.register(handle)
    ctx.bus.register("HANDLER")
    ctx.bus.register("WORLD")

    world = WorldEvents()
    ctx.world = world

    engine = Engine()
    engine.register(DecaySystem())
    engine.register(BrainSystem(save_fn=lambda h: repo.save(pool.by_handle(h)) if pool.by_handle(h) else None))
    engine.register(ConsumptionSystem())

    for name in ["alice", "bob", "carol"]:
        fake = Agent(handle=name)
        fake.brain = LLMBrain(core=client, actions=registry)
        repo.save(fake)
        pool._agents[name] = fake
        pool._bus.register(name)

    print(f"Agent: {handle}")
    print(f"Personality: {agent.personality}")
    print(f"Model: {args.model}")
    print("Other agents: alice, bob, carol")
    print("---")
    print("Type a board message, or !help for commands\n")

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("> ")
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
        elif line == "!energy":
            print(f"Energy: {agent.energy}")
            continue
        elif line == "!scratchpad":
            print(f"Scratchpad:\n{agent.scratchpad or '(empty)'}")
            continue
        elif line == "!soul":
            print(f"Soul:\n{agent.soul or '(empty)'}")
            continue
        elif line == "!strategy":
            print(f"Strategy:\n{agent.strategy or '(empty)'}")
            continue
        elif line == "!prompt":
            print(agent._build_system_prompt())
            continue
        elif line == "!tick":
            pass
        elif line.startswith("!dm "):
            parts = line[4:].split(" ", 1)
            if len(parts) == 2:
                ctx.bus.send(parts[0], handle, parts[1])
                print(f"  [{parts[0]}] -> [{handle}]: {parts[1]}")
            else:
                print("Usage: !dm HANDLE message")
            continue
        elif line.startswith("!world "):
            msg = line[7:]
            ctx.bus.send("WORLD", handle, msg)
            print(f"  [WORLD] -> [{handle}]: {msg}")
            continue
        else:
            ctx.board.post("HANDLER", line)
            print(f"  [HANDLER posted]: {line}")

        ctx.tick += 1
        await engine.tick(ctx)
        print()


def main():
    parser = argparse.ArgumentParser(description="Test a single agent interactively")
    parser.add_argument(
        "--model",
        default="/mnt/models/Qwen3.5-9B-AWQ",
    )
    parser.add_argument(
        "--base-url",
        default="http://ai-lab.lan:8080/v1",
    )
    parser.add_argument("--handle", default=None)
    parser.add_argument("--extra-body", default=None)
    args = parser.parse_args()

    if args.extra_body:
        import json

        args.extra_body = json.loads(args.extra_body)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
