"""Importance scoring: rate unscored episodes via an LLM articulator."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from conwai.brain import BrainContext
from conwai.processes.types import AgentHandle, Episodes

if TYPE_CHECKING:
    from conwai.llm import LLMProvider

log = structlog.get_logger()

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
            f"{n + 1}. {ep.content.split(chr(10))[0]}"
            for n, (_, ep) in enumerate(batch)
        )
        user_msg = self._prompt.format(events=event_lines)

        try:
            resp = await self._articulator.call(
                _SYSTEM, [{"role": "user", "content": user_msg}]
            )
        except Exception:
            log.error("importance_scoring_error", exc_info=True)
            return

        scores = self._parse(resp.text, len(batch))

        agent = ctx.percept.get(AgentHandle)
        agent_id = agent.value if agent else "?"

        for (idx, ep), score in zip(batch, scores):
            ep.importance = score
            preview = ep.content[:60]
            log.info("importance_scored", handle=agent_id, preview=preview, score=score)

    @staticmethod
    def _parse(text: str, count: int) -> list[int]:
        _BARE_SCORE = re.compile(r"^\s*(\d+)\s*$")
        parsed: dict[int, int] = {}
        bare_scores: list[int] = []
        for line in text.splitlines():
            m = _SCORE_RE.search(line)
            if m:
                idx = int(m.group(1)) - 1  # 1-based -> 0-based
                raw = int(m.group(2))
                parsed[idx] = max(1, min(10, raw))
                continue
            bare = _BARE_SCORE.match(line)
            if bare:
                bare_scores.append(max(1, min(10, int(bare.group(1)))))
                continue
            if line.strip():
                log.warning("importance_unparseable_line", line=line)

        # Prefer indexed format; fall back to bare scores in order
        if parsed:
            return [parsed.get(i, 5) for i in range(count)]
        if bare_scores:
            return [bare_scores[i] if i < len(bare_scores) else 5 for i in range(count)]
        return [5] * count
