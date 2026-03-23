"""Reusable process implementations for common cognitive patterns.

These are building blocks — not core framework. They operate on typed entries
in the Blackboard and read from the Percept. Mix them with scenario-specific
or rule-based processes in any pipeline.
"""

from conwai.processes.compression import MemoryCompression
from conwai.processes.context import ContextAssembly
from conwai.processes.inference import InferenceProcess
from conwai.processes.recall import MemoryRecall
from conwai.processes.types import (
    AgentHandle,
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

__all__ = [
    "AgentHandle",
    "ContextAssembly",
    "Episode",
    "Episodes",
    "Identity",
    "InferenceProcess",
    "LLMSnapshot",
    "MemoryCompression",
    "MemoryRecall",
    "Observations",
    "PerceptFeedback",
    "RecalledMemories",
    "PerceptTick",
    "WorkingMemory",
    "WorkingMemoryEntry",
]
