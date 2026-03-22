"""Context assembly: builds the LLM message snapshot from cognitive state.

This is the LLM adapter — it converts domain objects into the chat message
format that LLM clients expect.
"""

from __future__ import annotations

from conwai.processes.types import (
    Identity,
    LLMSnapshot,
    Observations,
    RecalledMemories,
    PerceptTick,
    WorkingMemory,
    WorkingMemoryEntry,
)
from conwai.typemap import Blackboard, Percept


class ContextAssembly:
    """Build an LLM-ready message snapshot from percept and blackboard state."""

    def __init__(self, context_window: int = 10_000, system_prompt: str = ""):
        self.context_window = context_window
        self.system_prompt = system_prompt

    async def run(self, percept: Percept, bb: Blackboard) -> None:
        wm = bb.get(WorkingMemory) or WorkingMemory()
        recalled = bb.get(RecalledMemories)
        identity = percept.get(Identity)
        obs = percept.get(Observations)
        tick_num = percept.get(PerceptTick)

        entries = wm.entries

        # Trim working memory to fit context window
        ctx_chars = sum(len(e.content) for e in entries)
        while ctx_chars > self.context_window and len(entries) > 1:
            removed = entries.pop(0)
            ctx_chars -= len(removed.content)

        # Identity slot (first entry, updated each cycle)
        if identity and identity.text:
            if entries and entries[0].kind == "identity":
                entries[0] = WorkingMemoryEntry(content=identity.text, kind="identity")
            else:
                entries.insert(0, WorkingMemoryEntry(content=identity.text, kind="identity"))

        # Convert working memory to LLM message format
        messages = []
        for entry in entries:
            if entry.kind == "reasoning":
                messages.append({"role": "assistant", "content": entry.content})
            else:
                messages.append({"role": "user", "content": entry.content})

        # Recalled memories (ephemeral — in snapshot only)
        if recalled and recalled.entries:
            recall_text = "=== RECALLED MEMORIES ===\n" + "\n".join(recalled.entries) + "\n=== END ==="
            messages.append({"role": "user", "content": recall_text})

        # Observations as perception prompt
        prompt_text = obs.text if obs else ""
        if prompt_text:
            messages.append({"role": "user", "content": prompt_text})
            entries.append(WorkingMemoryEntry(content=prompt_text, kind="observation"))

        wm.tick_entry_start = len(entries) - 1 if entries else None
        wm.last_tick = tick_num.value if tick_num else 0

        bb.set(wm)
        bb.set(LLMSnapshot(messages=messages, system_prompt=self.system_prompt))
