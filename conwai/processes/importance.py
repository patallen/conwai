"""Importance scoring: rate unscored episodes via an LLM articulator."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from conwai.brain import BrainContext
from conwai.processes.types import AgentHandle, Episodes

if TYPE_CHECKING:
    from conwai.llm import LLMProvider

log = logging.getLogger("conwai")

_DEFAULT_PROMPT = """\
Rate each event's significance for an agent building a self-sufficient community.
1 = routine (foraging, waiting)
5 = notable (first trade with someone, running low on resources)
10 = critical (near-death, major strategy change, betrayal)

Events:
{events}

Respond with just the ratings, one per line (e.g., "1. 3"):"""

_SYSTEM = "You are rating the significance of events. Be concise."
_SCORE_RE = re.compile(r"(\d+)\.\s*(\d+)")


class ImportanceScoring:
    """Score unscored episodes for importance using an LLM."""

    def __init__(
        self,
        articulator: LLMProvider,
        prompt: str | None = None,
        batch_size: int = 30,
    ):
        self._articulator = articulator
        self._prompt = prompt or _DEFAULT_PROMPT
        self._batch_size = batch_size

    async def run(self, ctx: BrainContext) -> None:
        eps = ctx.state.get(Episodes)
        if not eps:
            return

        unscored = [
            (i, ep)
            for i, ep in enumerate(eps.entries)
            if ep.importance == 0 and not ep.content.startswith("[Reflection")
        ]
        if not unscored:
            return

        batch = unscored[: self._batch_size]
        event_lines = "\n".join(
            f"{n + 1}. {ep.content}" for n, (_, ep) in enumerate(batch)
        )
        user_msg = self._prompt.format(events=event_lines)

        try:
            resp = await self._articulator.call(
                _SYSTEM, [{"role": "user", "content": user_msg}]
            )
        except Exception:
            log.error("ImportanceScoring: articulator call failed", exc_info=True)
            return

        scores = self._parse(resp.text, len(batch))

        agent = ctx.percept.get(AgentHandle)
        agent_id = agent.value if agent else "?"

        for (idx, ep), score in zip(batch, scores):
            ep.importance = score
            preview = ep.content[:60]
            log.info(f'[@{agent_id}] importance: "{preview}" -> {score}')

    @staticmethod
    def _parse(text: str, count: int) -> list[int]:
        parsed: dict[int, int] = {}
        for line in text.splitlines():
            m = _SCORE_RE.search(line)
            if not m:
                if line.strip():
                    log.warning(f"ImportanceScoring: unparseable line: {line!r}")
                continue
            idx = int(m.group(1)) - 1  # 1-based -> 0-based
            raw = int(m.group(2))
            clamped = max(1, min(10, raw))
            if clamped != raw:
                log.warning(
                    f"ImportanceScoring: score {raw} out of range, clamped to {clamped}"
                )
            parsed[idx] = clamped

        result: list[int] = []
        for i in range(count):
            if i in parsed:
                result.append(parsed[i])
            else:
                log.warning(f"ImportanceScoring: no score for event {i + 1}, defaulting to 5")
                result.append(5)
        return result
