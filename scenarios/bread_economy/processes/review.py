"""Strategic review: periodic reflection that updates the agent's strategy."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from conwai.brain import BrainContext
from conwai.processes.types import AgentHandle, Episodes, Identity, PerceptTick

if TYPE_CHECKING:
    from conwai.llm import LLMProvider

from scenarios.bread_economy.components import AgentMemory, Economy, Inventory

log = logging.getLogger("conwai.strategic_review")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class StrategicReview:
    """At the start of each day, ask the LLM to reflect and set strategy."""

    def __init__(
        self,
        client: LLMProvider,
        store: Any,
        interval: int = 24,
        prompts_dir: Path | None = None,
    ):
        self.client = client
        self.store = store
        self.interval = interval
        d = prompts_dir or _PROMPTS_DIR
        self._review_tpl = (d / "morning_review.md").read_text()

    async def run(self, ctx: BrainContext) -> None:
        tick_num = ctx.percept.get(PerceptTick)
        tick = tick_num.value if tick_num else 0
        if tick == 0 or tick % self.interval != 0:
            return

        handle = ctx.percept.get(AgentHandle)
        agent_id = handle.value if handle else ""
        identity = ctx.percept.get(Identity)
        identity_text = identity.text if identity else ""

        eps = ctx.state.get(Episodes)
        recent = eps.entries[-24:] if eps and eps.entries else []
        diary_text = (
            "\n".join(e.content for e in recent) if recent else "(no diary entries yet)"
        )

        if self.store.has(agent_id, AgentMemory):
            mem = self.store.get(agent_id, AgentMemory)
        else:
            mem = AgentMemory()
        current_strategy = mem.strategy or "(no strategy yet)"

        if self.store.has(agent_id, Economy):
            eco = self.store.get(agent_id, Economy)
        else:
            eco = Economy(coins=0)
        if self.store.has(agent_id, Inventory):
            inv = self.store.get(agent_id, Inventory)
        else:
            inv = Inventory()

        review_prompt = self._review_tpl.format(
            diary=diary_text,
            current_strategy=current_strategy,
            coins=int(eco.coins),
            flour=inv.flour,
            water=inv.water,
            bread=inv.bread,
        )

        system = f"You are {agent_id}. Reflect on your experiences and set your strategy for the day ahead."

        try:
            resp = await self.client.call(
                system,
                [{"role": "user", "content": identity_text + "\n\n" + review_prompt}],
            )
        except Exception as e:
            log.error(f"[@{agent_id}] strategic review failed: {e}")
            return

        strategy = resp.text.strip()
        if not strategy:
            log.error(f"[@{agent_id}] strategic review failed: no strategy returned")
            return

        log.info(f"[@{agent_id}] morning ({len(strategy)}):\n{strategy}...")

        strategy = strategy[:700]

        if self.store.has(agent_id, AgentMemory):
            mem = self.store.get(agent_id, AgentMemory)
        else:
            mem = AgentMemory()
        mem.strategy = strategy
        self.store.set(agent_id, mem)

        log.info(f"[@{agent_id}] morning review (len: {len(strategy)})")
