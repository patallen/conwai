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

    def __init__(self, save_fn=None):
        self._save_fn = save_fn

    async def tick(self, ctx: Context) -> None:
        tasks = []
        for agent in ctx.pool.alive():
            if not agent.brain:
                continue
            tasks.append(asyncio.create_task(self._tick_agent(agent, ctx)))
        await asyncio.gather(*tasks)

    async def _tick_agent(self, agent, ctx) -> None:
        agent._running = True
        agent._dm_sent_this_tick = 0
        agent._foraging = False
        agent._llm_failed = False
        try:
            if agent._pending_compaction and agent._pending_compaction.done():
                agent._pending_compaction = None
            if agent._pending_summary and agent._pending_summary.done():
                agent._pending_summary = None

            msg_count_before = len(agent.messages)
            start = time.monotonic()
            resp = await agent.brain.decide(agent, ctx)
            elapsed = time.monotonic() - start
            log.info(f"[{agent.handle}] tick {ctx.tick} took {elapsed:.1f}s")

            if self._save_fn:
                self._save_fn(agent.handle)

            if not resp:
                return

            if agent._compact_needed and not agent._pending_compaction:
                agent._pending_compaction = asyncio.create_task(
                    agent.brain.compact(agent, ctx, len(agent.messages))
                )
            if not agent._pending_summary and not agent._pending_compaction:
                agent._pending_summary = asyncio.create_task(
                    agent.brain.summarize(agent, ctx, msg_count_before)
                )
        except Exception as e:
            log.error(f"[{agent.handle}] ERROR: {e}")
        finally:
            agent._running = False
