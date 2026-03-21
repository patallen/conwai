"""Tests for brain process implementations: memory, context, and inference."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from conwai.cognition import Decision
from conwai.cognition.percept import ActionFeedback
from conwai.llm import LLMResponse, ToolCall

from scenarios.bread_economy.processes.context import ContextAssembly
from scenarios.bread_economy.processes.inference import InferenceProcess
from scenarios.bread_economy.processes.memory import MemoryCompression, MemoryRecall


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class FakePercept:
    agent_id: str = "A1"
    tick: int = 1
    identity: str = "You are A1"
    prompt_text: str = "tick 1 perception"
    action_feedback: list = field(default_factory=list)

    def to_prompt(self) -> str:
        return self.prompt_text


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


def _make_board(
    messages=None,
    diary=None,
    tick_msg_start=None,
    last_tick=0,
    percept=None,
) -> dict[str, Any]:
    """Build a board dict with sensible defaults."""
    return {
        "percept": percept or FakePercept(),
        "decisions": [],
        "state": {
            "messages": messages if messages is not None else [],
            "diary": diary if diary is not None else [],
            "tick_msg_start": tick_msg_start,
            "last_tick": last_tick,
        },
    }


# ===========================================================================
# MemoryCompression tests
# ===========================================================================


class TestMemoryCompression:
    def test_collapse_creates_tick_summary(self):
        """After a tick with perception + assistant messages, collapse creates
        a _tick_summary message with timestamp and reasoning."""
        messages = [
            {"role": "user", "content": "perception text"},
            {"role": "assistant", "content": "I will gather wheat"},
        ]
        board = _make_board(messages=messages, tick_msg_start=0, last_tick=5)
        mc = MemoryCompression(timestamp_formatter=lambda t: f"T{t}")

        asyncio.run(mc.run(board))

        msgs = board["state"]["messages"]
        summaries = [m for m in msgs if m.get("_tick_summary")]
        assert len(summaries) == 1
        assert summaries[0]["content"].startswith("[T5]")
        assert "I will gather wheat" in summaries[0]["content"]

    def test_collapse_includes_action_feedback(self):
        """ActionFeedback from the percept is included in the collapsed summary."""
        feedback = [
            ActionFeedback(action="harvest", args={"field": "north"}, result="3 wheat"),
            ActionFeedback(action="eat", args={}, result="hunger restored"),
        ]
        messages = [
            {"role": "user", "content": "perception"},
            {"role": "assistant", "content": "thinking"},
        ]
        percept = FakePercept(action_feedback=feedback)
        board = _make_board(
            messages=messages, tick_msg_start=0, last_tick=2, percept=percept
        )
        mc = MemoryCompression()

        asyncio.run(mc.run(board))

        summaries = [
            m for m in board["state"]["messages"] if m.get("_tick_summary")
        ]
        assert len(summaries) == 1
        content = summaries[0]["content"]
        assert "harvest" in content and "3 wheat" in content
        assert "eat" in content and "hunger restored" in content

    def test_collapse_includes_tool_messages(self):
        """For backward compat, tool messages in the tick range appear as
        action->result entries."""
        messages = [
            {"role": "user", "content": "perception"},
            {"role": "assistant", "content": "thinking"},
            {"role": "tool", "name": "bake", "content": "bread +1"},
        ]
        board = _make_board(messages=messages, tick_msg_start=0, last_tick=3)
        mc = MemoryCompression()

        asyncio.run(mc.run(board))

        summaries = [
            m for m in board["state"]["messages"] if m.get("_tick_summary")
        ]
        assert len(summaries) == 1
        content = summaries[0]["content"]
        assert "bake" in content and "bread +1" in content

    def test_archive_moves_old_summaries_to_diary(self):
        """With more than recent_ticks summaries, old ones move to diary."""
        messages = [
            {"role": "user", "content": f"[T{i}] summary {i}", "_tick_summary": True}
            for i in range(5)
        ]
        board = _make_board(messages=messages, last_tick=5)
        mc = MemoryCompression(recent_ticks=3)

        asyncio.run(mc.run(board))

        msgs = board["state"]["messages"]
        diary = board["state"]["diary"]
        summaries = [m for m in msgs if m.get("_tick_summary")]
        assert len(summaries) == 3
        assert len(diary) == 2
        # Archived entries are the oldest two (reversed pop order)
        archived_contents = {d["content"] for d in diary}
        assert any("summary 0" in c for c in archived_contents)
        assert any("summary 1" in c for c in archived_contents)

    def test_diary_cap(self):
        """Diary doesn't exceed diary_max."""
        diary = [
            {"content": f"old entry {i}", "handles": []} for i in range(10)
        ]
        messages = [
            {"role": "user", "content": f"[T{i}] summary Ag1 {i}", "_tick_summary": True}
            for i in range(5)
        ]
        board = _make_board(messages=messages, diary=diary, last_tick=10)
        mc = MemoryCompression(recent_ticks=2, diary_max=11)

        asyncio.run(mc.run(board))

        assert len(board["state"]["diary"]) <= 11

    def test_first_tick_no_collapse(self):
        """When tick_msg_start is None, nothing is collapsed."""
        messages = [
            {"role": "user", "content": "some old message"},
        ]
        board = _make_board(messages=messages, tick_msg_start=None, last_tick=0)
        mc = MemoryCompression()

        asyncio.run(mc.run(board))

        msgs = board["state"]["messages"]
        assert len(msgs) == 1
        assert msgs[0]["content"] == "some old message"
        assert not any(m.get("_tick_summary") for m in msgs)

    def test_collapse_truncates_reasoning(self):
        """Reasoning over 150 chars is truncated with '...'."""
        long_reasoning = "x" * 200
        messages = [
            {"role": "user", "content": "perception"},
            {"role": "assistant", "content": long_reasoning},
        ]
        board = _make_board(messages=messages, tick_msg_start=0, last_tick=1)
        mc = MemoryCompression()

        asyncio.run(mc.run(board))

        summaries = [
            m for m in board["state"]["messages"] if m.get("_tick_summary")
        ]
        content = summaries[0]["content"]
        # The reasoning portion should be exactly 150 chars + "..."
        assert content.endswith("...")
        assert "x" * 150 in content
        assert "x" * 151 not in content


# ===========================================================================
# MemoryRecall tests
# ===========================================================================


class TestMemoryRecall:
    def test_recall_finds_matching_handles(self):
        """Diary entries with handles mentioned in perception are recalled."""
        diary = [
            {"content": "traded with Ag1 successfully", "handles": ["Ag1"]},
            {"content": "saw Bk2 at the market", "handles": ["Bk2"]},
            {"content": "nothing relevant here", "handles": ["Cx3"]},
        ]
        percept = FakePercept(prompt_text="Ag1 is nearby and Bk2 wants to trade")
        board = _make_board(diary=diary, percept=percept)

        recall = MemoryRecall(recall_limit=10)
        asyncio.run(recall.run(board))

        recalled = board.get("recalled", [])
        assert len(recalled) == 2
        assert any("Ag1" in r for r in recalled)
        assert any("Bk2" in r for r in recalled)

    def test_recall_no_match_returns_nothing(self):
        """When perception mentions no handles, recall is empty."""
        diary = [
            {"content": "traded with Ag1", "handles": ["Ag1"]},
        ]
        percept = FakePercept(prompt_text="the sky is blue and nothing happens")
        board = _make_board(diary=diary, percept=percept)

        recall = MemoryRecall()
        asyncio.run(recall.run(board))

        assert board.get("recalled") is None

    def test_recall_respects_limit(self):
        """Only recall_limit entries are returned."""
        diary = [
            {"content": f"entry {i} about Ag1", "handles": ["Ag1"]}
            for i in range(10)
        ]
        percept = FakePercept(prompt_text="Ag1 is here")
        board = _make_board(diary=diary, percept=percept)

        recall = MemoryRecall(recall_limit=3)
        asyncio.run(recall.run(board))

        assert len(board["recalled"]) == 3

    def test_recall_skips_common_words(self):
        """Words like 'Day', 'New', 'The' do NOT trigger recall because
        the handle regex requires a digit."""
        diary = [
            {"content": "Day 1 was peaceful", "handles": ["Day"]},
            {"content": "The new era", "handles": ["The"]},
        ]
        percept = FakePercept(prompt_text="Day 5 is starting, The morning is new")
        board = _make_board(diary=diary, percept=percept)

        recall = MemoryRecall()
        asyncio.run(recall.run(board))

        # "Day" / "The" don't match _HANDLE_RE (need a digit in the match)
        assert board.get("recalled") is None


# ===========================================================================
# ContextAssembly tests
# ===========================================================================


class TestContextAssembly:
    def test_snapshot_includes_identity_and_perception(self):
        """Snapshot has identity as first message and perception as last."""
        percept = FakePercept(identity="You are A1", prompt_text="tick 1")
        board = _make_board(percept=percept)

        ctx = ContextAssembly(system_prompt="be helpful")
        asyncio.run(ctx.run(board))

        snapshot = board["messages_snapshot"]
        assert snapshot[0]["content"] == "You are A1"
        assert snapshot[-1]["content"] == "tick 1"
        assert board["system_prompt"] == "be helpful"

    def test_context_trimming(self):
        """When messages exceed context_window, oldest are removed."""
        messages = [
            {"role": "user", "content": "a" * 100}
            for _ in range(10)
        ]
        percept = FakePercept(identity="", prompt_text="short")
        board = _make_board(messages=messages, percept=percept)

        ctx = ContextAssembly(context_window=300)
        asyncio.run(ctx.run(board))

        # Messages should have been trimmed so total content <= 300
        total = sum(len(m.get("content", "")) for m in board["state"]["messages"])
        # The trimming happens before perception is added, so persistent
        # messages (minus the appended perception) should be within budget
        # (some may exceed slightly due to perception append)
        assert total <= 300 + len("short")

    def test_identity_slot_updated(self):
        """Identity message is updated in place, not duplicated."""
        messages = [
            {"role": "user", "content": "old identity", "_identity": True},
            {"role": "user", "content": "summary", "_tick_summary": True},
        ]
        percept = FakePercept(identity="new identity", prompt_text="tick 2")
        board = _make_board(messages=messages, percept=percept)

        ctx = ContextAssembly()
        asyncio.run(ctx.run(board))

        msgs = board["state"]["messages"]
        identity_msgs = [m for m in msgs if m.get("_identity")]
        assert len(identity_msgs) == 1
        assert identity_msgs[0]["content"] == "new identity"

    def test_recalled_memories_in_snapshot_only(self):
        """Recalled memories appear in snapshot but NOT in persistent messages."""
        percept = FakePercept(identity="You are A1", prompt_text="tick 1")
        board = _make_board(percept=percept)
        board["recalled"] = ["old memory about Ag1"]

        ctx = ContextAssembly()
        asyncio.run(ctx.run(board))

        snapshot = board["messages_snapshot"]
        recall_msgs = [m for m in snapshot if "RECALLED MEMORIES" in m.get("content", "")]
        assert len(recall_msgs) == 1
        assert "old memory about Ag1" in recall_msgs[0]["content"]

        persistent = board["state"]["messages"]
        for m in persistent:
            assert "RECALLED MEMORIES" not in m.get("content", "")

    def test_metadata_stripped_from_snapshot(self):
        """Keys starting with '_' are stripped from snapshot messages."""
        messages = [
            {"role": "user", "content": "identity", "_identity": True},
            {"role": "user", "content": "summary", "_tick_summary": True},
        ]
        percept = FakePercept(identity="identity", prompt_text="tick 1")
        board = _make_board(messages=messages, percept=percept)

        ctx = ContextAssembly()
        asyncio.run(ctx.run(board))

        snapshot = board["messages_snapshot"]
        for msg in snapshot:
            for key in msg:
                assert not key.startswith("_"), f"metadata key {key!r} leaked into snapshot"

    def test_tick_msg_start_set(self):
        """After run, state has tick_msg_start pointing to the perception message."""
        percept = FakePercept(identity="You are A1", prompt_text="tick 1 perception")
        board = _make_board(percept=percept)

        ctx = ContextAssembly()
        asyncio.run(ctx.run(board))

        state = board["state"]
        idx = state["tick_msg_start"]
        assert idx is not None
        assert state["messages"][idx]["content"] == "tick 1 perception"


# ===========================================================================
# InferenceProcess tests
# ===========================================================================


class TestInferenceProcess:
    def test_inference_appends_decisions(self):
        """Mock LLM returning tool calls produces decisions on the board."""
        tool_calls = [
            ToolCall(id="tc1", name="bake", args={"amount": 1}),
            ToolCall(id="tc2", name="sell", args={"to": "Bk2", "price": 5}),
        ]
        client = FakeLLMClient(text="I'll bake and sell", tool_calls=tool_calls)
        proc = InferenceProcess(client=client, tools=[{"function": {"name": "bake"}}])

        percept = FakePercept()
        board = _make_board(percept=percept)
        board["messages_snapshot"] = [{"role": "user", "content": "tick 1"}]
        board["system_prompt"] = "be helpful"

        asyncio.run(proc.run(board))

        decisions = board["decisions"]
        assert len(decisions) == 2
        assert decisions[0] == Decision("bake", {"amount": 1})
        assert decisions[1] == Decision("sell", {"to": "Bk2", "price": 5})

    def test_inference_handles_empty_response(self):
        """LLM returns no text and no tool calls: no decisions, no message."""
        client = FakeLLMClient(text="", tool_calls=[])
        proc = InferenceProcess(client=client)

        board = _make_board()
        board["messages_snapshot"] = [{"role": "user", "content": "tick 1"}]
        board["system_prompt"] = ""

        asyncio.run(proc.run(board))

        assert board["decisions"] == []
        assert board["state"]["messages"] == []

    def test_inference_handles_error(self):
        """LLM raises exception: no crash, no decisions."""
        client = ErrorLLMClient()
        proc = InferenceProcess(client=client)

        board = _make_board()
        board["messages_snapshot"] = [{"role": "user", "content": "tick 1"}]
        board["system_prompt"] = ""

        asyncio.run(proc.run(board))

        assert board["decisions"] == []

    def test_inference_appends_assistant_message(self):
        """The assistant message is appended to persistent messages."""
        tool_calls = [ToolCall(id="tc1", name="bake", args={})]
        client = FakeLLMClient(text="thinking out loud", tool_calls=tool_calls)
        proc = InferenceProcess(client=client)

        board = _make_board()
        board["messages_snapshot"] = [{"role": "user", "content": "tick 1"}]
        board["system_prompt"] = ""

        asyncio.run(proc.run(board))

        msgs = board["state"]["messages"]
        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"] == "thinking out loud"
        assert "tool_calls" in msgs[0]


# ===========================================================================
# Integration test
# ===========================================================================


class TestFullPipeline:
    def test_full_pipeline_two_ticks(self):
        """Run the full pipeline for two ticks with a mock LLM.

        Tick 1: LLM gets perception, returns a tool call, decision recorded.
        Tick 2: Previous tick compressed into summary with action results,
                LLM gets new perception with summary in history.
        """
        # --- Tick 1 ---
        tick1_calls = [ToolCall(id="tc1", name="harvest", args={"field": "north"})]
        llm = FakeLLMClient(text="I should harvest", tool_calls=tick1_calls)

        compression = MemoryCompression(timestamp_formatter=lambda t: f"T{t}")
        recall = MemoryRecall()
        context = ContextAssembly(system_prompt="system")
        inference = InferenceProcess(client=llm)

        percept1 = FakePercept(
            agent_id="A1", tick=1, identity="You are A1", prompt_text="tick 1 world"
        )

        board: dict[str, Any] = {
            "percept": percept1,
            "decisions": [],
            "state": {
                "messages": [],
                "diary": [],
                "tick_msg_start": None,
                "last_tick": 0,
            },
        }

        async def run_tick(b):
            await compression.run(b)
            await recall.run(b)
            await context.run(b)
            await inference.run(b)

        asyncio.run(run_tick(board))

        # Verify tick 1 results
        assert len(board["decisions"]) == 1
        assert board["decisions"][0] == Decision("harvest", {"field": "north"})

        # LLM received the perception
        assert llm.last_call is not None
        snapshot1 = llm.last_call["messages"]
        assert any("tick 1 world" in m.get("content", "") for m in snapshot1)

        # State now has the perception message and the assistant reply
        state = board["state"]
        assert state["tick_msg_start"] is not None

        # --- Tick 2 ---
        feedback = [
            ActionFeedback(action="harvest", args={"field": "north"}, result="3 wheat"),
        ]
        percept2 = FakePercept(
            agent_id="A1",
            tick=2,
            identity="You are A1",
            prompt_text="tick 2 world",
            action_feedback=feedback,
        )

        tick2_calls = [ToolCall(id="tc2", name="bake", args={})]
        llm2 = FakeLLMClient(text="Now I bake", tool_calls=tick2_calls)
        inference2 = InferenceProcess(client=llm2)

        board["percept"] = percept2
        board["decisions"] = []

        async def run_tick2(b):
            await compression.run(b)
            await recall.run(b)
            await context.run(b)
            await inference2.run(b)

        asyncio.run(run_tick2(board))

        # Tick 1's messages should have been compressed into a summary
        msgs = board["state"]["messages"]
        summaries = [m for m in msgs if m.get("_tick_summary")]
        assert len(summaries) == 1
        summary_content = summaries[0]["content"]
        assert "[T1]" in summary_content
        # Action feedback included in summary
        assert "harvest" in summary_content
        assert "3 wheat" in summary_content

        # Tick 2 decisions
        assert len(board["decisions"]) == 1
        assert board["decisions"][0] == Decision("bake", {})

        # LLM received tick 2 perception
        snapshot2 = llm2.last_call["messages"]
        assert any("tick 2 world" in m.get("content", "") for m in snapshot2)
        # Summary from tick 1 should be visible in the snapshot
        assert any("[T1]" in m.get("content", "") for m in snapshot2)
