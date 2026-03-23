"""Tests for importance scoring process."""

from __future__ import annotations

import asyncio

from conwai.processes.importance import ImportanceScoring
from conwai.processes.types import AgentHandle, Episode, Episodes, PerceptTick
from conwai.typemap import Blackboard, Percept, State
from conwai.brain import BrainContext


class FakeArticulator:
    """Returns predictable importance scores."""
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = []

    async def call(self, system, messages, tools=None):
        from conwai.llm import LLMResponse
        self.calls.append({"system": system, "messages": messages})
        return LLMResponse(text=self.response_text, tool_calls=[], prompt_tokens=0, completion_tokens=0)


class ErrorArticulator:
    async def call(self, system, messages, tools=None):
        raise ConnectionError("LLM unreachable")


def _make_ctx(episodes=None, tick=100):
    percept = Percept()
    percept.set(AgentHandle(value="A1"))
    percept.set(PerceptTick(value=tick))
    state = State()
    eps = Episodes(entries=episodes if episodes is not None else [])
    state.set(eps)
    return BrainContext(percept=percept, state=state, bb=Blackboard()), eps


class TestImportanceScoring:
    def test_scores_unscored_episodes(self):
        episodes = [
            Episode(content="foraged 3 flour", tick=10),
            Episode(content="traded 10 water with Jill", tick=20),
        ]
        art = FakeArticulator("1. 2\n2. 8")
        ctx, eps = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=art).run(ctx))

        assert eps.entries[0].importance == 2
        assert eps.entries[1].importance == 8

    def test_skips_already_scored(self):
        episodes = [
            Episode(content="already scored", tick=10, importance=7),
            Episode(content="needs scoring", tick=20),
        ]
        art = FakeArticulator("1. 4")
        ctx, eps = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=art).run(ctx))

        assert eps.entries[0].importance == 7  # unchanged
        assert eps.entries[1].importance == 4

    def test_skips_reflections(self):
        episodes = [
            Episode(content="[Reflection, 48] some insight", tick=48),
            Episode(content="foraged 3 flour", tick=50),
        ]
        art = FakeArticulator("1. 3")
        ctx, eps = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=art).run(ctx))

        assert eps.entries[0].importance == 0  # reflection, untouched
        assert eps.entries[1].importance == 3

    def test_parse_failure_defaults_to_5(self):
        episodes = [
            Episode(content="something happened", tick=10),
        ]
        art = FakeArticulator("garbage response")
        ctx, eps = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=art).run(ctx))

        assert eps.entries[0].importance == 5

    def test_empty_episodes_returns_immediately(self):
        art = FakeArticulator("")
        ctx, _ = _make_ctx(episodes=[])

        asyncio.run(ImportanceScoring(articulator=art).run(ctx))

        assert len(art.calls) == 0

    def test_all_scored_returns_immediately(self):
        episodes = [Episode(content="scored", tick=10, importance=5)]
        art = FakeArticulator("")
        ctx, _ = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=art).run(ctx))

        assert len(art.calls) == 0

    def test_articulator_error_leaves_unscored(self):
        episodes = [Episode(content="something", tick=10)]
        ctx, eps = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=ErrorArticulator()).run(ctx))

        assert eps.entries[0].importance == 0  # still unscored

    def test_batch_size_caps_processing(self):
        episodes = [Episode(content=f"event {i}", tick=i) for i in range(10)]
        art = FakeArticulator("\n".join(f"{i+1}. 3" for i in range(5)))
        ctx, eps = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=art, batch_size=5).run(ctx))

        scored = [e for e in eps.entries if e.importance > 0]
        unscored = [e for e in eps.entries if e.importance == 0]
        assert len(scored) == 5
        assert len(unscored) == 5

    def test_clamps_out_of_range_scores(self):
        episodes = [
            Episode(content="event 1", tick=10),
            Episode(content="event 2", tick=20),
        ]
        art = FakeArticulator("1. 0\n2. 15")
        ctx, eps = _make_ctx(episodes=episodes)

        asyncio.run(ImportanceScoring(articulator=art).run(ctx))

        assert eps.entries[0].importance == 1  # clamped from 0
        assert eps.entries[1].importance == 10  # clamped from 15
