"""Consolidation process: reflection-based episodic→semantic memory.

Adapted from Generative Agents (Park et al., 2023). On each cycle:
1. Gather recent diary entries
2. Ask a small LLM for the 3 most salient questions
3. For each question, retrieve relevant diary entries by embedding similarity
4. Ask the LLM for insights grounded in those entries
5. Store insights as new diary entries (with embeddings) — they participate
   in future retrieval and future reflections.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

log = logging.getLogger("conwai")

if TYPE_CHECKING:
    from conwai.embeddings import Embedder

# Minimum diary entries before reflection activates
_MIN_ENTRIES = 15
# Number of focal-point questions to generate
_N_QUESTIONS = 3
# Diary entries to retrieve per question
_RETRIEVE_K = 5


class ConsolidationProcess:
    """Generate reflections from diary entries via focal-point questions.

    Uses a small LLM (articulator) for reflection and the shared embedder
    for retrieval and storing insights. Runs every *interval* ticks.
    """

    def __init__(
        self,
        interval: int = 24,
        articulator: Any | None = None,
        embedder: Embedder | None = None,
        enabled: bool = True,
        first_person: bool = True,
        **_: Any,
    ):
        self.interval = interval
        self._articulator = articulator
        self._embedder = embedder
        self.enabled = enabled
        self.first_person = first_person

    async def run(self, board: dict[str, Any]) -> None:
        percept = board.get("percept")
        tick = getattr(percept, "tick", 0)
        agent_id = getattr(percept, "agent_id", "?")

        if not self.enabled or tick == 0 or tick % self.interval != 0:
            return

        if not self._articulator or not self._embedder:
            return

        state = board.setdefault("state", {})
        diary: list[dict] = state.get("diary", [])
        if len(diary) < _MIN_ENTRIES:
            log.debug(
                f"[@{agent_id}] reflection skipped: "
                f"{len(diary)} diary entries < {_MIN_ENTRIES}"
            )
            return

        entries_with_emb = [e for e in diary if "embedding" in e]
        if len(entries_with_emb) < _MIN_ENTRIES:
            return

        # Step 1: Build recent diary summary for the focal-point prompt
        recent = entries_with_emb[-50:]
        numbered = "\n".join(
            f"{i+1}. {e['content'][:200]}" for i, e in enumerate(recent)
        )

        # Step 2: Ask for focal-point questions
        questions = await self._generate_questions(numbered, agent_id)
        if not questions:
            return

        for q in questions:
            log.info(f"[@{agent_id}]   focal question: {q[:80]}")

        # Step 3-4: For each question, retrieve + generate insight
        from conwai.embeddings import cosine_topk

        vectors = [e["embedding"] for e in entries_with_emb]
        insights = []

        for question in questions:
            # Embed the question, retrieve top-k relevant diary entries
            q_vec = self._embedder.embed([question])[0]
            top_indices = cosine_topk(q_vec, vectors, k=_RETRIEVE_K)
            evidence = [entries_with_emb[i]["content"][:200] for i in top_indices]

            # Generate insight from evidence
            insight = await self._generate_insight(question, evidence, agent_id)
            if insight:
                insights.append(insight)

        # Step 5: Store insights as diary entries with embeddings
        # Skip duplicates of existing reflections
        existing_reflections = {
            e["content"] for e in diary if e.get("content", "").startswith("[Reflection]")
        }
        new_insights = [
            ins for ins in insights
            if f"[Reflection] {ins}" not in existing_reflections
        ]
        if new_insights:
            insight_vecs = self._embedder.embed(new_insights)
            for text, vec in zip(new_insights, insight_vecs):
                diary.append({
                    "content": f"[Reflection] {text}",
                    "embedding": vec,
                    "handles": [],
                })

            log.info(
                f"[@{agent_id}] reflection: {len(entries_with_emb)} entries → "
                f"{len(new_insights)} insights ({len(insights) - len(new_insights)} dupes skipped)"
            )
            for ins in new_insights:
                log.info(f"[@{agent_id}]   insight: {ins[:80]}")

    async def _generate_questions(
        self, diary_summary: str, agent_id: str
    ) -> list[str]:
        """Ask the LLM for focal-point questions about recent experience."""
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
                # Strip numbering: "1)", "1.", "- ", "* ", etc.
                line = re.sub(r"^[\d]+[.)]\s*", "", line)
                line = re.sub(r"^[-*]\s+", "", line)
                line = line.strip()
                if line and len(line) > 5:
                    questions.append(line)
            return questions[:_N_QUESTIONS]
        except Exception as e:
            log.warning(f"[@{agent_id}] focal-point generation failed: {e}")
            return []

    async def _generate_insight(
        self, question: str, evidence: list[str], agent_id: str
    ) -> str | None:
        """Generate an insight from a question and retrieved evidence."""
        numbered = "\n".join(f"{i+1}. {e}" for i, e in enumerate(evidence))
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
        try:
            resp = await self._articulator.call(
                system=i_system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.text.strip()
            # Strip any numbering or "Insight:" prefix
            for prefix in ["1.", "1)", "Insight:", "insight:"]:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
            return text if text else None
        except Exception as e:
            log.warning(f"[@{agent_id}] insight generation failed: {e}")
            return None
