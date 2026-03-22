"""Tests for brain process implementations: memory, context, and inference."""

from __future__ import annotations

import asyncio

from conwai.cognition import Decision
from conwai.cognition.percept import ActionFeedback
from conwai.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
    MemoryRecall,
)
from conwai.processes.types import (
    AgentHandle,
    Decisions,
    Episode,
    Episodes,
    Identity,
    LLMSnapshot,
    Observations,
    PerceptFeedback,
    RecalledMemories,
    PerceptTick,
    WorkingMemory,
    WorkingMemoryEntry,
)
from conwai.llm import LLMResponse, ToolCall
from conwai.typemap import Blackboard, Percept


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FakeLLMClient:
    def __init__(self, text="", tool_calls=None):
        self.text = text
        self.tool_calls = tool_calls or []
        self.last_call = None

    async def call(self, system, messages, tools=None):
        self.last_call = {"system": system, "messages": messages, "tools": tools}
        return LLMResponse(
            text=self.text,
            tool_calls=self.tool_calls,
            prompt_tokens=100,
            completion_tokens=50,
        )


class ErrorLLMClient:
    async def call(self, system, messages, tools=None):
        raise ConnectionError("LLM unreachable")


def _make_percept(
    agent_id="A1", tick=1, identity="", observations="tick 1 perception",
    feedback=None,
) -> Percept:
    p = Percept()
    p.set(AgentHandle(value=agent_id))
    p.set(PerceptTick(value=tick))
    p.set(Identity(text=identity))
    p.set(Observations(text=observations))
    if feedback:
        p.set(PerceptFeedback(entries=feedback))
    return p


def _make_bb(
    working_memory=None,
    episodes=None,
    tick_entry_start=None,
    last_tick=0,
) -> Blackboard:
    bb = Blackboard()
    bb.set(WorkingMemory(
        entries=working_memory if working_memory is not None else [],
        last_tick=last_tick,
        tick_entry_start=tick_entry_start,
    ))
    bb.set(Episodes(entries=episodes if episodes is not None else []))
    return bb


# ===========================================================================
# MemoryCompression tests
# ===========================================================================


class TestMemoryCompression:
    def test_collapse_creates_tick_summary(self):
        wm = [
            WorkingMemoryEntry(content="perception text", kind="observation"),
            WorkingMemoryEntry(content="I will gather wheat", kind="reasoning"),
        ]
        bb = _make_bb(working_memory=wm, tick_entry_start=0, last_tick=5)
        percept = _make_percept()
        mc = MemoryCompression(timestamp_formatter=lambda t: f"T{t}")

        asyncio.run(mc.run(percept, bb))

        entries = bb.get(WorkingMemory).entries
        summaries = [e for e in entries if e.kind == "tick_summary"]
        assert len(summaries) == 1
        assert summaries[0].content.startswith("[T5]")
        assert "I will gather wheat" in summaries[0].content

    def test_collapse_includes_action_feedback(self):
        feedback = [
            ActionFeedback(action="harvest", args={"field": "north"}, result="3 wheat"),
            ActionFeedback(action="eat", args={}, result="hunger restored"),
        ]
        wm = [
            WorkingMemoryEntry(content="perception", kind="observation"),
            WorkingMemoryEntry(content="thinking", kind="reasoning"),
        ]
        bb = _make_bb(working_memory=wm, tick_entry_start=0, last_tick=2)
        percept = _make_percept(tick=2, feedback=feedback)
        mc = MemoryCompression()

        asyncio.run(mc.run(percept, bb))

        entries = bb.get(WorkingMemory).entries
        summaries = [e for e in entries if e.kind == "tick_summary"]
        assert len(summaries) == 1
        content = summaries[0].content
        assert "harvest" in content and "3 wheat" in content
        assert "eat" in content and "hunger restored" in content

    def test_archive_moves_old_summaries_to_episodes(self):
        wm = [
            WorkingMemoryEntry(content=f"[T{i}] summary {i}", kind="tick_summary")
            for i in range(5)
        ]
        bb = _make_bb(working_memory=wm, last_tick=5)
        percept = _make_percept()
        mc = MemoryCompression(recent_ticks=3)

        asyncio.run(mc.run(percept, bb))

        entries = bb.get(WorkingMemory).entries
        summaries = [e for e in entries if e.kind == "tick_summary"]
        assert len(summaries) == 3
        eps = bb.get(Episodes).entries
        assert len(eps) == 2

    def test_episode_cap(self):
        episodes = [Episode(content=f"old entry {i}") for i in range(10)]
        wm = [
            WorkingMemoryEntry(content=f"[T{i}] summary {i}", kind="tick_summary")
            for i in range(5)
        ]
        bb = _make_bb(working_memory=wm, episodes=episodes, last_tick=10)
        percept = _make_percept()
        mc = MemoryCompression(recent_ticks=2, diary_max=11)

        asyncio.run(mc.run(percept, bb))

        assert len(bb.get(Episodes).entries) <= 11

    def test_first_tick_no_collapse(self):
        wm = [WorkingMemoryEntry(content="some old message", kind="observation")]
        bb = _make_bb(working_memory=wm, tick_entry_start=None, last_tick=0)
        percept = _make_percept()
        mc = MemoryCompression()

        asyncio.run(mc.run(percept, bb))

        entries = bb.get(WorkingMemory).entries
        assert len(entries) == 1
        assert not any(e.kind == "tick_summary" for e in entries)

    def test_collapse_truncates_reasoning(self):
        long_reasoning = "x" * 400
        wm = [
            WorkingMemoryEntry(content="perception", kind="observation"),
            WorkingMemoryEntry(content=long_reasoning, kind="reasoning"),
        ]
        bb = _make_bb(working_memory=wm, tick_entry_start=0, last_tick=1)
        percept = _make_percept()
        mc = MemoryCompression()

        asyncio.run(mc.run(percept, bb))

        entries = bb.get(WorkingMemory).entries
        summaries = [e for e in entries if e.kind == "tick_summary"]
        content = summaries[0].content
        assert content.endswith("...")
        assert "x" * 300 in content
        assert "x" * 301 not in content


# ===========================================================================
# MemoryRecall tests
# ===========================================================================


class TestMemoryRecall:
    def test_recall_finds_matching_handles(self):
        episodes = [
            Episode(content="traded with @Ag1 successfully"),
            Episode(content="saw @Bk2 at the market"),
            Episode(content="nothing relevant here @Cx3"),
        ]
        bb = _make_bb(episodes=episodes)
        percept = _make_percept(observations="@Ag1 is nearby and @Bk2 wants to trade")

        recall = MemoryRecall(recall_limit=10)
        asyncio.run(recall.run(percept, bb))

        recalled = bb.get(RecalledMemories)
        assert recalled is not None
        assert len(recalled.entries) == 2

    def test_recall_no_match_returns_nothing(self):
        episodes = [Episode(content="traded with Ag1")]
        bb = _make_bb(episodes=episodes)
        percept = _make_percept(observations="the sky is blue")

        recall = MemoryRecall()
        asyncio.run(recall.run(percept, bb))

        assert bb.get(RecalledMemories) is None

    def test_recall_respects_limit(self):
        episodes = [Episode(content=f"entry {i} about @Ag1") for i in range(10)]
        bb = _make_bb(episodes=episodes)
        percept = _make_percept(observations="@Ag1 is here")

        recall = MemoryRecall(recall_limit=3)
        asyncio.run(recall.run(percept, bb))

        assert len(bb.get(RecalledMemories).entries) == 3

    def test_vector_recall_finds_semantically_similar(self):
        class FakeEmbedder:
            def embed(self, texts):
                return [[1.0, 0.0, 0.0] if ("trade" in t or "flour" in t)
                        else [0.0, 1.0, 0.0] if ("election" in t or "vote" in t)
                        else [0.0, 0.0, 1.0] for t in texts]

        episodes = [
            Episode(content="traded flour with @A1", embedding=[1.0, 0.0, 0.0]),
            Episode(content="voted in the election", embedding=[0.0, 1.0, 0.0]),
            Episode(content="watched the sunset", embedding=[0.0, 0.0, 1.0]),
        ]
        bb = _make_bb(episodes=episodes)
        percept = _make_percept(observations="I need to trade flour for water")

        recall = MemoryRecall(recall_limit=1, embedder=FakeEmbedder())
        asyncio.run(recall.run(percept, bb))

        recalled = bb.get(RecalledMemories)
        assert len(recalled.entries) == 1
        assert "traded flour" in recalled.entries[0]

    def test_vector_recall_falls_back_without_embeddings(self):
        class FakeEmbedder:
            def embed(self, texts):
                return [[1.0, 0.0] for _ in texts]

        episodes = [Episode(content="met @A1 at market")]
        bb = _make_bb(episodes=episodes)
        percept = _make_percept(observations="@A1 wants to trade")

        recall = MemoryRecall(recall_limit=5, embedder=FakeEmbedder())
        asyncio.run(recall.run(percept, bb))

        recalled = bb.get(RecalledMemories)
        assert len(recalled.entries) == 1

    def test_compression_embeds_on_archive(self):
        class FakeEmbedder:
            def embed(self, texts):
                return [[0.1, 0.2, 0.3] for _ in texts]

        wm = [
            WorkingMemoryEntry(content=f"summary {i}", kind="tick_summary")
            for i in range(5)
        ]
        bb = _make_bb(working_memory=wm)
        percept = _make_percept()

        mc = MemoryCompression(recent_ticks=2, embedder=FakeEmbedder())
        asyncio.run(mc.run(percept, bb))

        eps = bb.get(Episodes).entries
        assert len(eps) == 3
        for ep in eps:
            assert ep.embedding == [0.1, 0.2, 0.3]


# ===========================================================================
# ContextAssembly tests
# ===========================================================================


class TestContextAssembly:
    def test_snapshot_includes_identity_and_perception(self):
        bb = _make_bb()
        percept = _make_percept(identity="You are A1", observations="tick 1")

        ca = ContextAssembly(system_prompt="be helpful")
        asyncio.run(ca.run(percept, bb))

        snap = bb.get(LLMSnapshot)
        assert snap.messages[0]["content"] == "You are A1"
        assert snap.messages[-1]["content"] == "tick 1"
        assert snap.system_prompt == "be helpful"

    def test_context_trimming(self):
        wm = [WorkingMemoryEntry(content="a" * 100, kind="observation") for _ in range(10)]
        bb = _make_bb(working_memory=wm)
        percept = _make_percept(observations="short")

        ca = ContextAssembly(context_window=300)
        asyncio.run(ca.run(percept, bb))

        total = sum(len(e.content) for e in bb.get(WorkingMemory).entries)
        assert total <= 300 + len("short")

    def test_identity_slot_updated(self):
        wm = [
            WorkingMemoryEntry(content="old identity", kind="identity"),
            WorkingMemoryEntry(content="summary", kind="tick_summary"),
        ]
        bb = _make_bb(working_memory=wm)
        percept = _make_percept(identity="new identity", observations="tick 2")

        ca = ContextAssembly()
        asyncio.run(ca.run(percept, bb))

        entries = bb.get(WorkingMemory).entries
        identity_entries = [e for e in entries if e.kind == "identity"]
        assert len(identity_entries) == 1
        assert identity_entries[0].content == "new identity"

    def test_recalled_memories_in_snapshot_only(self):
        bb = _make_bb()
        bb.set(RecalledMemories(entries=["old memory about Ag1"]))
        percept = _make_percept(identity="You are A1", observations="tick 1")

        ca = ContextAssembly()
        asyncio.run(ca.run(percept, bb))

        snap = bb.get(LLMSnapshot)
        recall_msgs = [m for m in snap.messages if "RECALLED MEMORIES" in m.get("content", "")]
        assert len(recall_msgs) == 1

        for e in bb.get(WorkingMemory).entries:
            assert "RECALLED MEMORIES" not in e.content

    def test_tick_entry_start_set(self):
        bb = _make_bb()
        percept = _make_percept(observations="tick 1 perception")

        ca = ContextAssembly()
        asyncio.run(ca.run(percept, bb))

        wm = bb.get(WorkingMemory)
        assert wm.tick_entry_start is not None
        assert wm.entries[wm.tick_entry_start].content == "tick 1 perception"


# ===========================================================================
# InferenceProcess tests
# ===========================================================================


class TestInferenceProcess:
    def test_inference_appends_decisions(self):
        tool_calls = [
            ToolCall(id="tc1", name="bake", args={"amount": 1}),
            ToolCall(id="tc2", name="sell", args={"to": "Bk2", "price": 5}),
        ]
        client = FakeLLMClient(text="I'll bake and sell", tool_calls=tool_calls)
        proc = InferenceProcess(client=client, tools=[{"function": {"name": "bake"}}])

        bb = _make_bb()
        bb.set(LLMSnapshot(messages=[{"role": "user", "content": "tick 1"}], system_prompt="be helpful"))
        percept = _make_percept()

        asyncio.run(proc.run(percept, bb))

        decisions = bb.get(Decisions)
        assert len(decisions.entries) == 2
        assert decisions.entries[0] == Decision("bake", {"amount": 1})

    def test_inference_handles_empty_response(self):
        client = FakeLLMClient(text="", tool_calls=[])
        proc = InferenceProcess(client=client)

        bb = _make_bb()
        bb.set(LLMSnapshot(messages=[{"role": "user", "content": "tick 1"}]))
        percept = _make_percept()

        asyncio.run(proc.run(percept, bb))

        assert bb.get(Decisions) is None

    def test_inference_handles_error(self):
        client = ErrorLLMClient()
        proc = InferenceProcess(client=client)

        bb = _make_bb()
        bb.set(LLMSnapshot(messages=[{"role": "user", "content": "tick 1"}]))
        percept = _make_percept()

        asyncio.run(proc.run(percept, bb))

        assert bb.get(Decisions) is None

    def test_inference_stores_reasoning_in_working_memory(self):
        tool_calls = [ToolCall(id="tc1", name="bake", args={})]
        client = FakeLLMClient(text="thinking out loud", tool_calls=tool_calls)
        proc = InferenceProcess(client=client)

        bb = _make_bb()
        bb.set(LLMSnapshot(messages=[{"role": "user", "content": "tick 1"}]))
        percept = _make_percept()

        asyncio.run(proc.run(percept, bb))

        wm = bb.get(WorkingMemory)
        reasoning = [e for e in wm.entries if e.kind == "reasoning"]
        assert len(reasoning) == 1
        assert reasoning[0].content == "thinking out loud"


# ===========================================================================
# Integration test
# ===========================================================================


class TestFullPipeline:
    def test_full_pipeline_two_ticks(self):
        tick1_calls = [ToolCall(id="tc1", name="harvest", args={"field": "north"})]
        llm = FakeLLMClient(text="I should harvest", tool_calls=tick1_calls)

        compression = MemoryCompression(timestamp_formatter=lambda t: f"T{t}")
        recall = MemoryRecall()
        context = ContextAssembly(system_prompt="system")
        inference = InferenceProcess(client=llm)

        bb = _make_bb()
        percept1 = _make_percept(agent_id="A1", tick=1, identity="You are A1", observations="tick 1 world")

        async def run_tick(p, b):
            await compression.run(p, b)
            await recall.run(p, b)
            await context.run(p, b)
            await inference.run(p, b)

        asyncio.run(run_tick(percept1, bb))

        decisions = bb.get(Decisions)
        assert len(decisions.entries) == 1
        assert decisions.entries[0] == Decision("harvest", {"field": "north"})

        # --- Tick 2 ---
        feedback = [ActionFeedback(action="harvest", args={"field": "north"}, result="3 wheat")]
        percept2 = _make_percept(
            agent_id="A1", tick=2, identity="You are A1",
            observations="tick 2 world", feedback=feedback,
        )
        bb.remove(Decisions)
        bb.remove(RecalledMemories)
        bb.remove(LLMSnapshot)

        tick2_calls = [ToolCall(id="tc2", name="bake", args={})]
        llm2 = FakeLLMClient(text="Now I bake", tool_calls=tick2_calls)
        inference2 = InferenceProcess(client=llm2)

        async def run_tick2(p, b):
            await compression.run(p, b)
            await recall.run(p, b)
            await context.run(p, b)
            await inference2.run(p, b)

        asyncio.run(run_tick2(percept2, bb))

        wm = bb.get(WorkingMemory)
        summaries = [e for e in wm.entries if e.kind == "tick_summary"]
        assert len(summaries) == 1
        assert "[T1]" in summaries[0].content
        assert "harvest" in summaries[0].content

        decisions = bb.get(Decisions)
        assert decisions.entries[0] == Decision("bake", {})

        snapshot2 = llm2.last_call["messages"]
        assert any("tick 2 world" in m.get("content", "") for m in snapshot2)
        assert any("[T1]" in m.get("content", "") for m in snapshot2)
