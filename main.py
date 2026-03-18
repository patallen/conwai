import asyncio
import logging
import os
import random
import sys
import time
from pathlib import Path
from uuid import uuid4

from conwai.agent import Agent
from conwai.config import ENERGY_GAIN, ENERGY_MAX, STARTING_BREAD
import conwai.config as config
from conwai.default_actions import create_registry
from conwai.app import Context

from conwai.llm import LLMClient
from conwai.repository import AgentRepository
from conwai.world import WorldEvents

log = logging.getLogger("conwai")


def setup_logging():
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    log.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)

    Path("data").mkdir(exist_ok=True)
    fh = logging.FileHandler("data/sim.log")
    fh.setFormatter(fmt)
    log.addHandler(fh)

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
                        ctx.agent_map[handle].coins = max(
                            0, ctx.agent_map[handle].coins - amount
                        )
                        ctx.log(
                            "HANDLER",
                            "drain",
                            {
                                "handle": handle,
                                "amount": amount,
                                "remaining": ctx.agent_map[handle].coins,
                            },
                        )
                        log.info(f"[HANDLER] drained {handle} by {amount}, now {ctx.agent_map[handle].coins}")
                elif line.startswith("!set_energy "):
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] in ctx.agent_map:
                        handle, amount = parts[1], int(parts[2])
                        ctx.agent_map[handle].coins = min(ENERGY_MAX, max(0, amount))
                        ctx.log(
                            "HANDLER",
                            "set_energy",
                            {"handle": handle, "energy": ctx.agent_map[handle].coins},
                        )
                        log.info(f"[HANDLER] set {handle} energy to {ctx.agent_map[handle].coins}")
                elif line.startswith("!secret "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3 and parts[1] in ctx.agent_map:
                        handle, content = parts[1], parts[2]
                        ctx.bus.send("WORLD", handle, content)
                        ctx.log("WORLD", "secret_dropped", {"to": handle, "content": content})
                        log.info(f"[HANDLER] dropped secret to {handle}: {content}")
                elif line.startswith("@"):
                    parts = line.split(" ", 1)
                    handle = parts[0][1:]
                    msg = parts[1] if len(parts) > 1 else ""
                    ctx.bus.send("HANDLER", handle, msg)
                    ctx.log("HANDLER", "dm_sent", {"to": handle, "content": msg})
                    log.info(f"[HANDLER] -> [{handle}]: {msg}")
                    if handle in ctx.agent_map:
                        ctx.agent_map[handle].gain_coins(
                            "HANDLER attention", ENERGY_GAIN["dm_received"]
                        )
                else:
                    ctx.board.post("HANDLER", line)
                    ctx.log("HANDLER", "board_post", {"content": line})
                    log.info(f"[HANDLER]: {line}")
            last_size = current_size
        await asyncio.sleep(0.5)


async def main():
    setup_logging()
    ctx = Context()
    tick_path = Path("data/tick")
    if tick_path.exists():
        ctx.tick = int(tick_path.read_text().strip())

    registry = create_registry()
    qwen4b0 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8080/v1", model="/mnt/models/Qwen3.5-4B-AWQ"
    )
    qwen4b1 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8081/v1", model="/mnt/models/Qwen3.5-4B-AWQ"
    )
    qwen9b0 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8080/v1", model="/mnt/models/Qwen3.5-9B-AWQ", max_tokens=2048
    )
    qwen9b1 = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8081/v1", model="/mnt/models/Qwen3.5-9B-AWQ", max_tokens=2048
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
    qwen27b = LLMClient(  # noqa: F841
        base_url="http://ai-lab.lan:8081/v1", model="/mnt/models/Qwen3.5-27B-GPTQ-Int4", max_tokens=2048
    )
    b200 = LLMClient(
        base_url="https://cq2qdgtb5xh2ap-8000.proxy.runpod.net/v1",
        model="Qwen/Qwen3.5-122B-A10B-GPTQ-Int4", max_tokens=512,
        api_key="none",
    )
    h200 = LLMClient(
        base_url="https://ykwnq4rjufjojf-8000.proxy.runpod.net/v1",
        model="QuantTrio/Qwen3.5-9B-AWQ", max_tokens=512,
        api_key="none",
    )
    repo = AgentRepository()

    def make_agent(core: LLMClient, prefix: str, role: str = "") -> Agent:
        while True:
            handle = f"{prefix}{uuid4().hex[:3]}"
            if not repo.exists(handle):
                break
        if not role:
            role = random.choice(["flour_forager", "water_forager", "baker"])
        compactor = h200
        agent = repo.create(
            Agent(core=b200, compactor=compactor, context_window=10_000,
                  actions=registry, handle=handle, role=role, bread=STARTING_BREAD, born_tick=ctx.tick)
        )
        ctx.register_agent(agent)
        return agent

    agents = []
    roles = (
        ["flour_forager"] * 6 +
        ["water_forager"] * 6 +
        ["baker"] * 4
    )
    for i in range(1, 17):
        handle = f"A{i}"
        role = roles[i - 1]
        compactor = h200
        if repo.exists(handle):
            agent = repo.load(handle=handle)
            if not agent.alive:
                # Dead agent — will be replaced by the runtime loop
                agent.role = role  # preserve role for replacement
                agents.append(agent)
                continue
            agent.core = b200
            agent.compactor = compactor
            agent.actions = registry
            agent.context_window = 10_000
        else:
            agent = repo.create(
                Agent(
                    core=b200, compactor=compactor, context_window=10_000,
                    actions=registry, handle=handle, role=role, bread=STARTING_BREAD, born_tick=ctx.tick,
                )
            )
        agents.append(agent)
        ctx.register_agent(agent)

    ctx.bus.register("HANDLER")
    ctx.bus.register("WORLD")
    world = WorldEvents()
    ctx.world = world

    asyncio.create_task(watch_handler_file(ctx))

    async def wait_for_llm():
        """Block until the inference endpoint is reachable."""
        import httpx
        while True:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"{b200.base_url}/models")
                    if resp.status_code == 200:
                        return
            except Exception:
                pass
            log.warning("[WORLD] LLM unreachable, waiting 10s...")
            await asyncio.sleep(10)

    while True:
        config.reload()
        await wait_for_llm()
        ctx.tick += 1
        tick_start = time.monotonic()
        Path("data/tick").write_text(str(ctx.tick))
        world.tick(ctx)

        # Daily tax: 1% of coins every 24 ticks
        if ctx.tick % 24 == 0:
            for agent in agents:
                if agent.alive and agent.coins > 0:
                    tax = max(1, int(agent.coins * 0.01))
                    agent.coins -= tax
                    agent._energy_log.append(f"coins -{tax} (daily tax)")
            ctx.log("WORLD", "tax", {"tick": ctx.tick})
            log.info(f"[WORLD] daily tax collected (tick {ctx.tick})")

        # Bread spoilage
        if config.BREAD_SPOIL_INTERVAL > 0 and ctx.tick % config.BREAD_SPOIL_INTERVAL == 0:
            for agent in agents:
                if agent.alive and agent.bread > 0:
                    spoiled = min(agent.bread, config.BREAD_SPOIL_AMOUNT)
                    agent.bread -= spoiled
                    agent._energy_log.append(f"{spoiled} bread spoiled (bread left: {agent.bread})")

        for i, agent in enumerate(agents):
            if not agent.alive:
                ctx.bus.unregister(agent.handle)
                if agent.handle in ctx.agent_map:
                    del ctx.agent_map[agent.handle]
                ctx.board.post(
                    "WORLD",
                    f"{agent.handle} has died. A new member is joining.",
                )
                log.info(f"[WORLD] {agent.handle} DIED")
                replacement = make_agent(agent.core, agent.handle[0], role=agent.role)
                agents[i] = replacement
                ctx.board.post("WORLD", f"New member {replacement.handle} has joined.")
                ctx.log(
                    "WORLD",
                    "agent_spawned",
                    {"handle": replacement.handle, "replaced": agent.handle},
                )
                log.info(f"[WORLD] {replacement.handle} spawned (replacing {agent.handle})")

        tasks = []
        for agent in agents:
            if not agent.alive:
                continue

            async def tick_and_save(a=agent, t=ctx.tick):
                start = time.monotonic()
                await a.tick(ctx)
                repo.save(a)
                elapsed = time.monotonic() - start
                log.info(f"[{a.handle}] tick {t} took {elapsed:.1f}s")

            tasks.append(asyncio.create_task(tick_and_save()))

        await asyncio.gather(*tasks)
        log.info(f"[WORLD] tick {ctx.tick} completed in {time.monotonic() - tick_start:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
