"""LLM inference: call the model and convert tool calls to decisions."""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

from conwai.brain import BrainContext, Decision, Decisions
from conwai.processes.types import (
    AgentHandle,
    LLMSnapshot,
    WorkingMemory,
    WorkingMemoryEntry,
)

if TYPE_CHECKING:
    from conwai.llm import LLMProvider

log = structlog.get_logger()


class InferenceProcess:
    """Call an LLM with the assembled message snapshot and produce decisions."""

    def __init__(
        self,
        client: LLMProvider,
        tools: list[dict] | None = None,
    ):
        self.client = client
        self.tools = tools

    async def run(self, ctx: BrainContext) -> None:
        snap = ctx.bb.get(LLMSnapshot)
        if not snap or not snap.messages:
            return

        handle = ctx.percept.get(AgentHandle)
        agent_id = handle.value if handle else "?"

        try:
            resp = await self.client.call(
                snap.system_prompt, snap.messages, tools=self.tools
            )
        except Exception as e:
            log.error("llm_error", handle=agent_id, error=str(e))
            return

        if not resp.text and not resp.tool_calls:
            return

        if resp.text:
            wm = ctx.state.get(WorkingMemory) or WorkingMemory()
            wm.entries.append(WorkingMemoryEntry(content=resp.text, kind="reasoning"))
            ctx.state.set(wm)

        log.info("llm_response", handle=agent_id, prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens, text_preview=resp.text[:200] if resp.text else "")

        decisions = ctx.bb.get(Decisions) or Decisions()
        for tc in resp.tool_calls:
            decisions.entries.append(Decision(tc.name, tc.args))
        ctx.bb.set(decisions)
