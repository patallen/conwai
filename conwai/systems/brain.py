from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.app import Context

log = logging.getLogger("conwai")


class BrainSystem:
    name = "brain"

    async def tick(self, ctx: Context) -> None:
        tasks = []
        for agent in ctx.pool.alive():
            if not agent.brain:
                continue
            tasks.append(asyncio.create_task(self._tick_agent(agent, ctx)))
        await asyncio.gather(*tasks)

    async def _tick_agent(self, agent, ctx) -> None:
        start = time.monotonic()
        await agent.brain.tick(agent, ctx)
        ctx.pool.save(agent.handle)
        log.info(f"[{agent.handle}] tick {ctx.tick} took {time.monotonic() - start:.1f}s")
