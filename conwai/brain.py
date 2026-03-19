from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from conwai.actions import ActionRegistry
from conwai.llm import LLMClient, LLMResponse

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.app import Context

log = logging.getLogger("conwai")


@runtime_checkable
class Brain(Protocol):
    async def decide(self, agent: Agent, ctx: Context) -> LLMResponse | None: ...
    async def compact(self, agent: Agent, ctx: Context, snapshot_idx: int) -> None: ...
    async def summarize(self, agent: Agent, ctx: Context, msg_count_before: int) -> None: ...


_COMPACTION_PERSONA = (
    "You are a meticulous archivist. Your job is to preserve important information "
    "with thoroughness and precision. You never rush. You never skip details that matter. "
    "You write clearly and concisely but never sacrifice completeness for brevity."
)


class LLMBrain:
    def __init__(
        self,
        core: LLMClient,
        compactor: LLMClient | None = None,
        actions: ActionRegistry | None = None,
    ):
        self.core = core
        self.compactor = compactor
        self.actions = actions

    async def decide(self, agent: Agent, ctx: Context) -> LLMResponse | None:
        agent._rebuild_context(ctx)
        resp = await self._get_response(agent)
        if not resp:
            return None
        self._process_tool_calls(agent, resp, ctx)
        return resp

    async def compact(self, agent: Agent, ctx: Context, snapshot_idx: int) -> None:
        async with ctx.compact_semaphore:
            await self._compact_inner(agent, snapshot_idx)

    async def summarize(self, agent: Agent, ctx: Context, msg_count_before: int) -> None:
        compactor = self.compactor
        if not compactor:
            return
        tick_messages = agent.messages[msg_count_before - 1:]
        if len(tick_messages) <= 1:
            return
        text = "\n".join(
            m.get("content", "") or ""
            for m in tick_messages
            if m.get("content")
        )
        start = time.monotonic()
        resp = await compactor.call(
            "Summarize what you did this tick as a short memory. Write in first person. 1-3 sentences. Include actions, results, and anything important you learned.",
            [{"role": "user", "content": text}],
            tools=None,
        )
        if resp and resp.text:
            summary = resp.text.strip()
            log.info(f"[{agent.handle}] tick summarized ({len(summary)} chars, {time.monotonic() - start:.1f}s)")
            del agent.messages[msg_count_before - 1:]
            agent.messages.append({"role": "user", "content": f"[{agent._tick_to_timestamp(ctx.tick)}] {summary}"})

    # --- Internal ---

    async def _get_response(self, agent: Agent) -> LLMResponse | None:
        try:
            resp = await self.core.call(
                agent.system_prompt,
                agent.messages,
                tools=self.actions.tool_definitions() if self.actions else None,
            )
        except Exception as e:
            log.error(f"[{agent.handle}] LLM call failed: {e}")
            agent._llm_failed = True
            return None
        if not resp.text and not resp.tool_calls:
            log.info(f"[{agent.handle}] empty response, skipping")
            return None

        assistant_msg: dict = {"role": "assistant"}
        if resp.text:
            assistant_msg["content"] = resp.text
        if resp.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                }
                for tc in resp.tool_calls
            ]
        agent.messages.append(assistant_msg)

        log.info(f"[{agent.handle}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): {resp.text[:200] if resp.text else '(no text)'}")
        if resp.completion_tokens >= 2000:
            log.warning(f"[{agent.handle}] RUNAWAY ({resp.completion_tokens} tok): {resp.text[:500]}")
        if resp.tool_calls:
            names = [tc.name for tc in resp.tool_calls]
            log.info(f"[{agent.handle}] tools: {names}")
        return resp

    def _process_tool_calls(self, agent: Agent, resp: LLMResponse, ctx: Context) -> None:
        for tc in resp.tool_calls:
            if agent._foraging and tc.name != "compact":
                agent.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": "You are foraging this tick and cannot take other actions.",
                    }
                )
                continue
            self.actions.execute(agent, ctx, tc.name, tc.args)
            result = ". ".join(agent._action_log) if agent._action_log else "ok"
            agent.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                }
            )
            agent._action_log.clear()

    async def _compact_inner(self, agent: Agent, snapshot_idx: int) -> None:
        log.info(f"[{agent.handle}] compacting (snapshot at {snapshot_idx} msgs)...")

        compact_system = _COMPACTION_PERSONA + "\n\n" + agent.system_prompt
        snapshot_messages = agent.messages[:snapshot_idx]

        snapshot_messages.append({
            "role": "user",
            "content": (
                "COMPACTION REQUIRED. Write your compressed memory now. Target: 500-1500 characters. "
                "The system already provides your coins, inventory, hunger, thirst, recent transactions, board posts, and DMs each tick — do NOT repeat any of that. "
                "Write ONLY: AGENTS (who you trust/distrust and why, 1 sentence each), "
                "DEALS (active promises or debts), LESSONS (hard-won knowledge), GOALS (current plans). "
                "Anything you don't write here will be lost forever. Be concise but complete."
            ),
        })
        compact_response = await (self.compactor or self.core).call(
            compact_system,
            snapshot_messages,
            tools=None,
        )
        if compact_response and compact_response.text:
            summary = compact_response.text.strip()
            new_messages = agent.messages[snapshot_idx:]
            agent.messages = [
                {"role": "user", "content": f"=== YOUR COMPACTED MEMORY ===\n{summary}\n=== END COMPACTED MEMORY ==="}
            ] + new_messages
            agent._compact_needed = False
            log.info(f"[{agent.handle}] compacted ({len(summary)} chars, kept {len(new_messages)} newer msgs)")
