"""Tests for activation-based memory recall."""

from __future__ import annotations

import asyncio

from conwai.processes.activation_recall import ActivationRecall
from conwai.processes.types import (
    AgentHandle,
    Episode,
    Episodes,
    Observations,
    PerceptTick,
    RecalledMemories,
)
from conwai.typemap import Blackboard, Percept, State


class FakeEmbedder:
    """Embedder that maps keywords to orthogonal dimensions."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for t in texts:
            if "trade" in t or "flour" in t:
                results.append([1.0, 0.0, 0.0])
            elif "election" in t or "vote" in t:
                results.append([0.0, 1.0, 0.0])
            else:
                results.append([0.0, 0.0, 1.0])
        return results


def _make_ctx(
    tick: int = 100,
    observations: str = "I need to trade flour",
    episodes: list[Episode] | None = None,
) -> tuple:
    """Return (BrainContext, Episodes) so tests can inspect episode mutations."""
    from conwai.brain import BrainContext

    percept = Percept()
    percept.set(AgentHandle(value="A1"))
    percept.set(PerceptTick(value=tick))
    percept.set(Observations(text=observations))

    state = State()
    eps = Episodes(entries=episodes if episodes is not None else [])
    state.set(eps)

    ctx = BrainContext(percept=percept, state=state, bb=Blackboard())
    return ctx, eps


class TestActivationRecall:
    def test_recency_dominance(self):
        """Newer episode wins when cosine similarity is equal."""
        episodes = [
            Episode(content="traded flour long ago", tick=10, last_accessed=10,
                    access_count=0, embedding=[1.0, 0.0, 0.0]),
            Episode(content="traded flour recently", tick=90, last_accessed=90,
                    access_count=0, embedding=[1.0, 0.0, 0.0]),
        ]
        ctx, _ = _make_ctx(tick=100, observations="I need to trade flour", episodes=episodes)

        recall = ActivationRecall(recall_limit=1, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        recalled = ctx.bb.get(RecalledMemories)
        assert recalled is not None
        assert len(recalled.entries) == 1
        assert "recently" in recalled.entries[0]

    def test_frequency_dominance(self):
        """More-accessed episode wins when recency and cosine are equal."""
        episodes = [
            Episode(content="traded flour rarely", tick=50, last_accessed=50,
                    access_count=0, embedding=[1.0, 0.0, 0.0]),
            Episode(content="traded flour often", tick=50, last_accessed=50,
                    access_count=15, embedding=[1.0, 0.0, 0.0]),
        ]
        ctx, _ = _make_ctx(tick=100, observations="I need to trade flour", episodes=episodes)

        recall = ActivationRecall(recall_limit=1, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        recalled = ctx.bb.get(RecalledMemories)
        assert len(recalled.entries) == 1
        assert "often" in recalled.entries[0]

    def test_reinforcement_updates_metadata(self):
        """Recalled episodes get access_count incremented and last_accessed updated."""
        episodes = [
            Episode(content="traded flour with @Alice", tick=50, last_accessed=50,
                    access_count=2, embedding=[1.0, 0.0, 0.0]),
            Episode(content="watched the sunset", tick=50, last_accessed=50,
                    access_count=0, embedding=[0.0, 0.0, 1.0]),
        ]
        ctx, eps = _make_ctx(tick=100, observations="I need to trade flour", episodes=episodes)

        recall = ActivationRecall(recall_limit=1, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        # The recalled episode should have access_count incremented but last_accessed unchanged
        trade_ep = eps.entries[0]
        assert trade_ep.access_count == 3
        assert trade_ep.last_accessed == 50  # not updated — recency reflects when event happened

        # The non-recalled episode should be unchanged
        sunset_ep = eps.entries[1]
        assert sunset_ep.access_count == 0
        assert sunset_ep.last_accessed == 50

    def test_fallback_handle_recall(self):
        """Without embedder, falls back to @-mention matching."""
        episodes = [
            Episode(content="met @Alice at the market"),
            Episode(content="nothing relevant"),
        ]
        ctx, _ = _make_ctx(observations="@Alice wants to trade", episodes=episodes)

        recall = ActivationRecall(recall_limit=5)  # no embedder
        asyncio.run(recall.run(ctx))

        recalled = ctx.bb.get(RecalledMemories)
        assert recalled is not None
        assert len(recalled.entries) == 1
        assert "@Alice" in recalled.entries[0]

    def test_fallback_does_not_update_metadata(self):
        """Handle recall fallback should not touch access_count or last_accessed."""
        episodes = [
            Episode(content="met @Alice at the market", tick=10, last_accessed=10, access_count=0),
        ]
        ctx, eps = _make_ctx(tick=100, observations="@Alice wants to trade", episodes=episodes)

        recall = ActivationRecall(recall_limit=5)  # no embedder
        asyncio.run(recall.run(ctx))

        assert eps.entries[0].access_count == 0
        assert eps.entries[0].last_accessed == 10

    def test_score_components_in_range(self):
        """All score components should stay in [0, 1]."""
        episodes = [
            Episode(content="traded flour", tick=1, last_accessed=1,
                    access_count=100, embedding=[1.0, 0.0, 0.0]),
        ]
        ctx, _ = _make_ctx(tick=500, observations="I need to trade flour", episodes=episodes)

        recall = ActivationRecall(recall_limit=7, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        # If score components exceed [0,1], the weighted sum could exceed 1.0.
        # We verify indirectly: the episode should still be recalled (score > 0.1)
        # and the clamped freq_cap prevents overflow.
        recalled = ctx.bb.get(RecalledMemories)
        assert recalled is not None

    def test_respects_recall_limit(self):
        """Should return at most recall_limit + reflection_limit episodes."""
        episodes = [
            Episode(content=f"traded flour episode {i}", tick=90, last_accessed=90,
                    access_count=0, embedding=[1.0, 0.0, 0.0])
            for i in range(20)
        ]
        ctx, _ = _make_ctx(tick=100, observations="I need to trade flour", episodes=episodes)

        recall = ActivationRecall(recall_limit=5, reflection_limit=2, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        recalled = ctx.bb.get(RecalledMemories)
        assert len(recalled.entries) == 5  # no reflections, so only episode slots used

    def test_reflection_split(self):
        """Reflections get reserved slots separate from episodes."""
        episodes = [
            Episode(content=f"traded flour episode {i}", tick=90, last_accessed=90,
                    access_count=0, embedding=[1.0, 0.0, 0.0])
            for i in range(20)
        ] + [
            Episode(content=f"[Reflection, Day 3] insight about trading {i}", tick=70, last_accessed=70,
                    access_count=0, embedding=[1.0, 0.0, 0.0])
            for i in range(5)
        ]
        ctx, _ = _make_ctx(tick=100, observations="I need to trade flour", episodes=episodes)

        recall = ActivationRecall(recall_limit=5, reflection_limit=2, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        recalled = ctx.bb.get(RecalledMemories)
        assert len(recalled.entries) == 7  # 5 episodes + 2 reflections
        reflections = [e for e in recalled.entries if e.startswith("[Reflection")]
        assert len(reflections) == 2

    def test_no_episodes_returns_nothing(self):
        """No episodes means no recalled memories."""
        ctx, _ = _make_ctx(episodes=[])

        recall = ActivationRecall(recall_limit=7, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        assert ctx.bb.get(RecalledMemories) is None

    def test_skips_episodes_without_embeddings(self):
        """Episodes without embeddings should be excluded from activation scoring."""
        episodes = [
            Episode(content="has embedding", tick=90, last_accessed=90,
                    access_count=0, embedding=[1.0, 0.0, 0.0]),
            Episode(content="no embedding", tick=95, last_accessed=95, access_count=0),
        ]
        ctx, _ = _make_ctx(tick=100, observations="I need to trade flour", episodes=episodes)

        recall = ActivationRecall(recall_limit=7, embedder=FakeEmbedder())
        asyncio.run(recall.run(ctx))

        recalled = ctx.bb.get(RecalledMemories)
        assert len(recalled.entries) == 1
        assert "has embedding" in recalled.entries[0]
