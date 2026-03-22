"""LLM inference: call the model and convert tool calls to decisions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.processes.types import Decision
from conwai.processes.types import AgentHandle, Decisions, LLMSnapshot, WorkingMemory, WorkingMemoryEntry
from conwai.typemap import Blackboard, Percept

if TYPE_CHECKING:
    from conwai.llm import LLMProvider

log = logging.getLogger("conwai")


class InferenceProcess:
    """Call an LLM with the assembled message snapshot and produce decisions."""

    def __init__(
        self,
        client: LLMProvider,
        tools: list[dict] | None = None,
    ):
        self.client = client
        self.tools = tools

    async def run(self, percept: Percept, bb: Blackboard) -> None:
        snap = bb.get(LLMSnapshot)
        if not snap or not snap.messages:
            return

        handle = percept.get(AgentHandle)
        agent_id = handle.value if handle else "?"

        try:
            resp = await self.client.call(snap.system_prompt, snap.messages, tools=self.tools)
        except Exception as e:
            log.error(f"[{agent_id}] LLM call failed: {e}")
            return

        if not resp.text and not resp.tool_calls:
            return

        if resp.text:
            wm = bb.get(WorkingMemory) or WorkingMemory()
            wm.entries.append(WorkingMemoryEntry(content=resp.text, kind="reasoning"))
            bb.set(wm)

        log.info(
            f"[{agent_id}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): "
            f"{resp.text[:200] if resp.text else '(no text)'}"
        )

        decisions = bb.get(Decisions) or Decisions()
        for tc in resp.tool_calls:
            decisions.entries.append(Decision(tc.name, tc.args))
        bb.set(decisions)
