import asyncio
import os
from pathlib import Path

from conwai.agent import Agent
from conwai.config import ENERGY_GAIN, ENERGY_MAX, HEARTBEAT_INTERVAL
from conwai.default_actions import create_registry
from conwai.app import Context

from conwai.llm import LLMClient
from conwai.repository import AgentRepository
from conwai.world import WorldEvents

HANDLER_FILE = Path("handler_input.txt")


async def watch_handler_file(ctx: Context):
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
                    if len(parts) >= 3 and parts[1] in ctx.agent_map:
                        handle, amount = parts[1], int(parts[2])
                        ctx.agent_map[handle].energy = max(
                            0, ctx.agent_map[handle].energy - amount
                        )
                        ctx.log(
                            "HANDLER",
                            "drain",
                            {
                                "handle": handle,
                                "amount": amount,
                                "remaining": ctx.agent_map[handle].energy,
                            },
                        )
                        print(
                            f"[HANDLER] drained {handle} by {amount}, now {ctx.agent_map[handle].energy}",
                            flush=True,
                        )
                elif line.startswith("!set_energy "):
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] in ctx.agent_map:
                        handle, amount = parts[1], int(parts[2])
                        ctx.agent_map[handle].energy = min(ENERGY_MAX, max(0, amount))
                        ctx.log(
                            "HANDLER",
                            "set_energy",
                            {"handle": handle, "energy": ctx.agent_map[handle].energy},
                        )
                        print(
                            f"[HANDLER] set {handle} energy to {ctx.agent_map[handle].energy}",
                            flush=True,
                        )
                elif line.startswith("!secret "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3 and parts[1] in ctx.agent_map:
                        handle, content = parts[1], parts[2]
                        ctx.bus.send("WORLD", handle, content)
                        ctx.log("WORLD", "secret_dropped", {"to": handle, "content": content})
                        print(f"[HANDLER] dropped secret to {handle}: {content}", flush=True)
                elif line.startswith("@"):
                    parts = line.split(" ", 1)
                    handle = parts[0][1:]
                    msg = parts[1] if len(parts) > 1 else ""
                    ctx.bus.send("HANDLER", handle, msg)
                    ctx.log("HANDLER", "dm_sent", {"to": handle, "content": msg})
                    print(f"[HANDLER] -> [{handle}]: {msg}", flush=True)
                    if handle in ctx.agent_map:
                        ctx.agent_map[handle].gain_energy(
                            "HANDLER attention", ENERGY_GAIN["dm_received"]
                        )
                else:
                    ctx.board.post("HANDLER", line)
                    ctx.log("HANDLER", "board_post", {"content": line})
                    print(f"[HANDLER]: {line}", flush=True)
            last_size = current_size
        await asyncio.sleep(0.5)


async def main():
    ctx = Context()

    registry = create_registry()
    qwen4b0 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8080/v1", model="/mnt/models/Qwen3.5-4B-AWQ"
    )
    qwen4b1 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8081/v1", model="/mnt/models/Qwen3.5-4B-AWQ"
    )
    qwen9b0 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8080/v1", model="/mnt/models/Qwen3.5-9B-AWQ"
    )
    qwen9b1 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8081/v1", model="/mnt/models/Qwen3.5-9B-AWQ"
    )
    qwen14b = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8081/v1", model="/mnt/models/Qwen3-14B-AWQ"
    )
    qwen14b_think = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8081/v1",
        model="/mnt/models/Qwen3-14B-AWQ",
    )
    flash = LLMClient(  # noqa: F841
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-2.5-flash-lite",
        api_key=os.environ.get("GOOGLE_AI_API_KEY", ""),
        extra_body={},
    )
    repo = AgentRepository()
    agents = []
    for i in range(8):
        agents.append(
            repo.create(
                Agent(
                    core=qwen4b0, context_window=10, actions=registry, handle=f"Q0.{i}"
                )
            )
        )

    for i in range(8):
        agents.append(
            repo.create(
                Agent(
                    core=qwen4b1, context_window=10, actions=registry, handle=f"Q1.{i}"
                )
            )
        )

    for agent in agents:
        ctx.register_agent(agent)

    ctx.bus.register("HANDLER")
    ctx.bus.register("WORLD")
    world = WorldEvents()
    ctx.world = world

    active: dict[str, asyncio.Task] = {}
    asyncio.create_task(watch_handler_file(ctx))

    def make_agent(core: LLMClient, prefix: str) -> Agent:
        agent = repo.create(
            Agent(core=core, context_window=10, actions=registry, handle=f"{prefix}0")
        )
        ctx.register_agent(agent)
        return agent

    while True:
        ctx.tick += 1
        Path("data/tick").write_text(str(ctx.tick))
        world.tick(ctx)

        for i, agent in enumerate(agents):
            if not agent.alive:
                ctx.bus.unregister(agent.handle)
                if agent.handle in ctx.agent_map:
                    del ctx.agent_map[agent.handle]
                ctx.board.post(
                    "WORLD",
                    f"{agent.handle} has died. A new member is joining.",
                )
                print(f"[WORLD] {agent.handle} DIED", flush=True)
                replacement = make_agent(agent.core, agent.handle[0])
                agents[i] = replacement
                ctx.board.post("WORLD", f"New member {replacement.handle} has joined.")
                ctx.log(
                    "WORLD",
                    "agent_spawned",
                    {"handle": replacement.handle, "replaced": agent.handle},
                )
                print(
                    f"[WORLD] {replacement.handle} spawned (replacing {agent.handle})",
                    flush=True,
                )
                continue

            task = active.get(agent.handle)
            if task is None or task.done():

                async def tick_and_save(a=agent):
                    await a.tick(ctx)
                    repo.save(a)

                active[agent.handle] = asyncio.create_task(tick_and_save())

        await asyncio.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
