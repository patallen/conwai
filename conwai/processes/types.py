"""Types used by the stock processes.

Percept entry types are loaded onto a Percept by the scenario's perception
builder. Blackboard types are read/written by processes during a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conwai.actions import ActionFeedback


# -- Percept entries (read-only, loaded by scenario) -----------------------

@dataclass
class Identity:
    """Agent's identity text (role, personality, soul, etc.)."""
    text: str = ""


@dataclass
class Observations:
    """What happened since last cycle (board posts, DMs, notifications)."""
    text: str = ""


@dataclass
class AgentHandle:
    """The agent's handle/identifier."""
    value: str = ""


@dataclass
class PerceptTick:
    """Current tick as perceived by the agent."""
    value: int = 0


@dataclass
class PerceptFeedback:
    """Action results from the previous cycle."""
    entries: list[ActionFeedback] = field(default_factory=list)


# -- Blackboard types (mutable, process-to-process) ------------------------

@dataclass
class Episode:
    """A compressed record of what happened."""
    content: str
    tick: int = 0
    embedding: list[float] | None = None


@dataclass
class WorkingMemoryEntry:
    """A single entry in working memory."""
    content: str
    kind: str = "observation"


@dataclass
class WorkingMemory:
    """Short-term memory that persists across cycles."""
    entries: list[WorkingMemoryEntry] = field(default_factory=list)
    last_tick: int = 0
    tick_entry_start: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> WorkingMemory:
        return cls(
            entries=[WorkingMemoryEntry(**e) for e in data.get("entries", [])],
            last_tick=data.get("last_tick", 0),
            tick_entry_start=data.get("tick_entry_start"),
        )


@dataclass
class Episodes:
    """Long-term episodic memory."""
    entries: list[Episode] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Episodes:
        return cls(entries=[Episode(**e) for e in data.get("entries", [])])


@dataclass
class RecalledMemories:
    """Episodes surfaced for this cycle by recall."""
    entries: list[str] = field(default_factory=list)



@dataclass
class LLMSnapshot:
    """LLM-ready message list and system prompt, built by ContextAssembly."""
    messages: list[dict] = field(default_factory=list)
    system_prompt: str = ""
