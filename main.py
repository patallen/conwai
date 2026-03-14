import asyncio
from pathlib import Path

from conwai.agent import Agent
from conwai.config import ENERGY_GAIN, ENERGY_MAX, HEARTBEAT_INTERVAL
from conwai.default_actions import create_registry
from conwai.environment import Context
from conwai.llm import LLMClient

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
    server_a = LLMClient(base_url="http://ai-lab.lan:8080/v1")
    server_b = LLMClient(base_url="http://ai-lab.lan:8081/v1")
    agents = [
        Agent(core=server_a, actions=registry),
        Agent(core=server_a, actions=registry),
        Agent(core=server_a, actions=registry),
        Agent(core=server_b, actions=registry),
        Agent(core=server_b, actions=registry),
        Agent(core=server_b, actions=registry),
    ]

    for agent in agents:
        ctx.register_agent(agent)
    ctx.bus.register("HANDLER")

    active: dict[str, asyncio.Task] = {}
    asyncio.create_task(watch_handler_file(ctx))

    while True:
        for agent in agents:
            task = active.get(agent.handle)
            if task is None or task.done():
                active[agent.handle] = asyncio.create_task(agent.tick(ctx))
        await asyncio.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
