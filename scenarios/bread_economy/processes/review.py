"""Strategic review: periodic reflection that updates the agent's strategy."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from conwai.llm_protocol import LLMProvider

log = logging.getLogger("conwai")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class StrategicReview:
    """At the start of each day, ask the LLM to reflect and set strategy.

    Runs as a process in the blackboard pipeline. On non-review ticks,
    does nothing. On review ticks (every `interval` ticks), makes a
    separate LLM call with diary context and writes the strategy to
    the agent's memory component in the store.
    """

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

    async def run(self, board: dict[str, Any]) -> None:
        percept = board.get("percept")
        tick = getattr(percept, "tick", 0)

        # Only review at the start of each day
        if tick == 0 or tick % self.interval != 0:
            return

        agent_id = getattr(percept, "agent_id", "")
        state = board.setdefault("state", {})
        diary: list[dict] = state.get("diary", [])

        # Build diary text from recent entries (last 24 entries ≈ last day)
        recent = diary[-24:] if diary else []
        diary_text = "\n".join(e["content"] for e in recent) if recent else "(no diary entries yet)"

        # Get current strategy and resources
        mem = self.store.get(agent_id, "memory") if self.store.has(agent_id, "memory") else {}
        current_strategy = mem.get("strategy", "") or "(no strategy yet)"

        eco = self.store.get(agent_id, "economy") if self.store.has(agent_id, "economy") else {}
        inv = self.store.get(agent_id, "inventory") if self.store.has(agent_id, "inventory") else {}

        # Build the review prompt
        review_prompt = self._review_tpl.format(
            diary=diary_text,
            current_strategy=current_strategy,
            coins=int(eco.get("coins", 0)),
            flour=inv.get("flour", 0),
            water=inv.get("water", 0),
            bread=inv.get("bread", 0),
        )

        # Get the system prompt from the board (set by ContextAssembly or earlier)
        identity = getattr(percept, "identity", "")
        system = f"You are {agent_id}. Reflect on your experiences and set your strategy for the day ahead."

        try:
            resp = await self.client.call(
                system,
                [{"role": "user", "content": identity + "\n\n" + review_prompt}],
            )
        except Exception as e:
            log.error(f"[@{agent_id}] strategic review failed: {e}")
            return

        strategy = resp.text.strip()
        if not strategy:
            return

        # Cap at 500 chars
        strategy = strategy[:500]

        # Save to memory component
        mem = self.store.get(agent_id, "memory") if self.store.has(agent_id, "memory") else {}
        mem["strategy"] = strategy
        self.store.set(agent_id, "memory", mem)

        log.info(f"[@{agent_id}] morning review: {strategy[:100]}...")
