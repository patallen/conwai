"""Consolidation process: reflection-based episodic -> semantic memory.

Adapted from Generative Agents (Park et al., 2023). On each cycle:
1. Gather recent episodes
2. Ask a small LLM for the 3 most salient questions
3. For each question, retrieve relevant episodes by embedding similarity
4. Ask the LLM for insights grounded in those episodes
5. Store insights as new episodes (with embeddings) — they participate
   in future retrieval and future reflections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from conwai.brain import BrainContext
from conwai.processes.types import AgentHandle, Episode, Episodes, PerceptTick

log = structlog.get_logger()

if TYPE_CHECKING:
    from conwai.llm import Embedder

_MIN_ENTRIES = 15
_N_QUESTIONS = 3
_RETRIEVE_K = 5
_DECAY_RATE = 0.01


def _top_by_importance(
    episodes: list[Episode], current_tick: int, n: int = 50
) -> list[Episode]:
    """Select top N episodes by importance * recency."""
    scored = []
    for ep in episodes:
        imp = ep.importance / 10.0 if ep.importance > 0 else 0.5
        age = max(0, current_tick - ep.tick)
        recency = 1.0 / (1.0 + _DECAY_RATE * age)
        scored.append((imp * recency, ep))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ep for _, ep in scored[:n]]


def _importance_weighted_topk(
    query_vec: list[float],
    candidate_vecs: list[list[float]],
    episodes: list[Episode],
    k: int = 5,
) -> list[int]:
    """Top-k by cosine similarity weighted by importance."""
    import numpy as np

    qv = np.array(query_vec)
    cv = np.array(candidate_vecs)
    sims = cv @ qv / (np.linalg.norm(cv, axis=1) * np.linalg.norm(qv) + 1e-10)
    for i, ep in enumerate(episodes):
        imp = ep.importance / 10.0 if ep.importance > 0 else 0.5
        sims[i] *= 0.5 + 0.5 * imp
    top = list(np.argsort(sims)[-k:][::-1])
    return [int(i) for i in top if sims[i] > 0]


class ConsolidationProcess:
    """Generate reflections from episodes via focal-point questions."""

    def __init__(
        self,
        interval: int = 24,
        articulator: Any | None = None,
        embedder: Embedder | None = None,
        enabled: bool = True,
        first_person: bool = True,
        timestamp_formatter: Any | None = None,
        **_: Any,
    ):
        self.interval = interval
        self._articulator = articulator
        self._embedder = embedder
        self.enabled = enabled
        self.first_person = first_person
        self._fmt = timestamp_formatter or str

    async def run(self, ctx: BrainContext) -> None:
        tick_num = ctx.percept.get(PerceptTick)
        tick = tick_num.value if tick_num else 0
        handle = ctx.percept.get(AgentHandle)
        agent_id = handle.value if handle else "?"

        if not self.enabled or tick == 0 or tick % self.interval != 0:
            return

        if not self._articulator or not self._embedder:
            return

        eps = ctx.state.get(Episodes)
        if not eps or len(eps.entries) < _MIN_ENTRIES:
            log.debug(
                "reflection_skipped", handle=agent_id, reason="not enough episodes"
            )
            return

        entries_with_emb = [e for e in eps.entries if e.embedding is not None]
        if len(entries_with_emb) < _MIN_ENTRIES:
            return

        # Select top 50 by importance * recency (not just most recent)
        recent = _top_by_importance(entries_with_emb, tick, n=50)
        numbered = "\n".join(
            f"{i + 1}. {e.content[:200]}" for i, e in enumerate(recent)
        )

        questions = await self._generate_questions(numbered, agent_id)
        if not questions:
            return

        for q in questions:
            log.info("focal_question", handle=agent_id, question=q[:80])

        vectors: list[list[float]] = [
            e.embedding for e in entries_with_emb if e.embedding is not None
        ]
        insights = []
        consumed: set[int] = set()  # indices into entries_with_emb

        for question in questions:
            q_vec = self._embedder.embed([question])[0]
            top_indices = _importance_weighted_topk(
                q_vec, vectors, entries_with_emb, k=_RETRIEVE_K
            )
            evidence = [entries_with_emb[i].content[:200] for i in top_indices]

            insight = await self._generate_insight(question, evidence, agent_id)
            if insight:
                insights.append(insight)
                consumed.update(top_indices)

        existing_reflections = set()
        for e in eps.entries:
            if e.content.startswith("[Reflection"):
                body = e.content.split("] ", 1)[1] if "] " in e.content else e.content
                existing_reflections.add(body)

        new_insights = [ins for ins in insights if ins not in existing_reflections]
        if new_insights:
            # Remove episodes that were consumed by reflections
            consumed_episodes = {id(entries_with_emb[i]) for i in consumed}
            eps.entries = [e for e in eps.entries if id(e) not in consumed_episodes]

            insight_vecs = self._embedder.embed(new_insights)
            for text, vec in zip(new_insights, insight_vecs):
                eps.entries.append(
                    Episode(
                        content=f"[Reflection, {self._fmt(tick)}] {text}",
                        tick=tick,
                        embedding=vec,
                        last_accessed=tick,
                    )
                )
            ctx.state.set(eps)

            log.info(
                "reflection_consolidated",
                handle=agent_id,
                consumed=len(consumed),
                insights=len(new_insights),
                dupes_skipped=len(insights) - len(new_insights),
            )
            for ins in new_insights:
                log.info("reflection_insight", handle=agent_id, insight=ins[:80])

    async def _generate_questions(self, diary_summary: str, agent_id: str) -> list[str]:
        if self.first_person:
            q_framing = "I can answer about my"
            q_system = "You generate questions about your experience. Short questions only. No preamble."
        else:
            q_framing = "we can answer about this agent's"
            q_system = "You generate questions about an agent's experience. Short questions only. No preamble."

        prompt = (
            f"{diary_summary}\n\n"
            f"Given only the information above, what are {_N_QUESTIONS} most "
            f"salient high-level questions {q_framing} "
            f"recent experience?\n"
            f"1)"
        )
        assert self._articulator is not None
        try:
            resp = await self._articulator.call(
                system=q_system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "1)" + resp.text
            questions = []
            import re

            for line in text.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                line = re.sub(r"^[\d]+[.)]\s*", "", line)
                line = re.sub(r"^[-*]\s+", "", line)
                line = line.strip()
                if line and len(line) > 5:
                    questions.append(line)
            return questions[:_N_QUESTIONS]
        except Exception as e:
            log.warning("focal_point_generation_failed", handle=agent_id, error=str(e))
            return []

    async def _generate_insight(
        self, question: str, evidence: list[str], agent_id: str
    ) -> str | None:
        numbered = "\n".join(f"{i + 1}. {e}" for i, e in enumerate(evidence))
        if self.first_person:
            i_framing = "can I infer"
            i_system = "You generate insights about your behavior. One sentence only. No preamble."
        else:
            i_framing = "can we infer about this agent"
            i_system = "You generate insights about an agent's behavior. One sentence only. No preamble."

        prompt = (
            f"Question: {question}\n\n"
            f"Relevant memories:\n{numbered}\n\n"
            f"What high-level insight {i_framing} from the above? "
            f"One sentence. Ground it in the evidence."
        )
        assert self._articulator is not None
        try:
            resp = await self._articulator.call(
                system=i_system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.text.strip()
            for prefix in ["1.", "1)", "Insight:", "insight:"]:
                if text.startswith(prefix):
                    text = text[len(prefix) :].strip()
            return text if text else None
        except Exception as e:
            log.warning("insight_generation_failed", handle=agent_id, error=str(e))
            return None
