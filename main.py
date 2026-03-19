import asyncio
import logging
import os
import time
from pathlib import Path

from conwai.config import ENERGY_GAIN, ENERGY_MAX
import conwai.config as config
from conwai.default_actions import create_registry
from conwai.app import Context

from conwai.brain import LLMBrain
from conwai.engine import Engine
from conwai.llm import LLMClient
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.systems.brain import BrainSystem
from conwai.systems.consumption import ConsumptionSystem
from conwai.systems.death import DeathSystem
from conwai.systems.decay import DecaySystem
from conwai.systems.spoilage import SpoilageSystem
from conwai.systems.tax import TaxSystem
from conwai.world import WorldEvents
from conwai.infra.logging import setup_logging

log = logging.getLogger("conwai")

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
                    agent = ctx.pool.by_handle(parts[1]) if len(parts) >= 3 else None
                    if agent:
                        handle, amount = parts[1], int(parts[2])
                        agent.coins = max(0, agent.coins - amount)
                        ctx.log(
                            "HANDLER",
                            "drain",
                            {
                                "handle": handle,
                                "amount": amount,
                                "remaining": agent.coins,
                            },
                        )
                        log.info(f"[HANDLER] drained {handle} by {amount}, now {agent.coins}")
                elif line.startswith("!set_energy "):
                    parts = line.split()
                    agent = ctx.pool.by_handle(parts[1]) if len(parts) >= 3 else None
                    if agent:
                        handle, amount = parts[1], int(parts[2])
                        agent.coins = min(ENERGY_MAX, max(0, amount))
                        ctx.log(
                            "HANDLER",
                            "set_energy",
                            {"handle": handle, "energy": agent.coins},
                        )
                        log.info(f"[HANDLER] set {handle} energy to {agent.coins}")
                elif line.startswith("!secret "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3 and ctx.pool.by_handle(parts[1]):
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
                    agent = ctx.pool.by_handle(handle)
                    if agent:
                        agent.gain_coins("HANDLER attention", ENERGY_GAIN["dm_received"])
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
    pool = AgentPool(repo, ctx.bus)
    ctx.pool = pool

    def wire_agent(agent, core=qwen9b0):
        agent.brain = LLMBrain(core=core, compactor=qwen9b1, actions=registry)

    roles = (
        ["flour_forager"] * 3 +
        ["water_forager"] * 3 +
        ["baker"] * 2
    )
    cores = [qwen9b0] * 6
    for i, (role, core) in enumerate(zip(roles, cores), 1):
        agent = pool.load_or_create(f"A{i}", role, ctx.tick)
        if agent.alive:
            wire_agent(agent, core=core)

    ctx.bus.register("HANDLER")
    ctx.bus.register("WORLD")
    world = WorldEvents()
    ctx.world = world

    engine = Engine()
    engine.register(DecaySystem())
    engine.register(TaxSystem())
    engine.register(SpoilageSystem())
    engine.register(DeathSystem(on_spawn=wire_agent))
    engine.register(BrainSystem(save_fn=pool.save))
    engine.register(ConsumptionSystem())

    asyncio.create_task(watch_handler_file(ctx))

    async def wait_for_llm():
        """Block until the inference endpoint is reachable."""
        import httpx
        while True:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"{qwen9b0.base_url}/models")
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
        await engine.tick(ctx)
        log.info(f"[WORLD] tick {ctx.tick} completed in {time.monotonic() - tick_start:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
