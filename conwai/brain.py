from __future__ import annotations

import asyncio
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

_compact_semaphore = asyncio.Semaphore(5)


@runtime_checkable
class Brain(Protocol):
    async def tick(self, agent: Agent, ctx: Context) -> None: ...


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
        context_window: int = 10_000,
    ):
        self.core = core
        self.compactor = compactor
        self.actions = actions
        self.context_window = context_window
        self._pending_compaction: asyncio.Task | None = None
        self._pending_summary: asyncio.Task | None = None

    async def tick(self, agent: Agent, ctx: Context) -> None:
        agent._dm_sent_this_tick = 0
        agent._foraging = False
        try:
            if self._pending_compaction and self._pending_compaction.done():
                self._pending_compaction = None
            if self._pending_summary and self._pending_summary.done():
                self._pending_summary = None

            msg_count_before = len(agent.messages)
            self._rebuild_context(agent, ctx)
            resp = await self._get_response(agent)
            if not resp:
                return
            self._process_tool_calls(agent, resp, ctx)

            compact_needed = self._context_chars(agent) >= int(self.context_window * 0.60)
            if compact_needed and not self._pending_compaction:
                self._pending_compaction = asyncio.create_task(
                    self._compact(agent, ctx, len(agent.messages))
                )
            if not self._pending_summary and not self._pending_compaction:
                self._pending_summary = asyncio.create_task(
                    self._summarize(agent, ctx, msg_count_before)
                )
        except Exception as e:
            log.error(f"[{agent.handle}] ERROR: {e}")

    # --- Perception ---

    def _rebuild_context(self, agent: Agent, ctx: Context) -> None:
        from conwai.agent import tick_to_timestamp

        while self._context_chars(agent) > self.context_window and len(agent.messages) > 1:
            agent.messages.pop(0)
        agent.system_prompt = agent._build_system_prompt()

        identity = agent._build_identity_message()
        if agent.messages and agent.messages[0].get("content", "").startswith("Your handle is"):
            agent.messages[0] = {"role": "user", "content": identity}
        else:
            agent.messages.insert(0, {"role": "user", "content": identity})

        new_posts = ctx.board.read_new(agent.handle)
        for p in new_posts:
            agent.record_board(ctx.tick, f"{p.handle}: {p.content}")
        new_dms = ctx.bus.receive(agent.handle)
        for dm in new_dms:
            agent.record_dm(ctx.tick, f"{dm.from_handle}: {dm.content}")

        if agent._inbox:
            for from_handle, resource, amount in agent._inbox:
                if resource == "flour":
                    agent.flour += amount
                elif resource == "water":
                    agent.water += amount
                elif resource == "bread":
                    agent.bread += amount
                agent.record_ledger(ctx.tick, f"received {amount} {resource} from {from_handle}")
            agent._inbox.clear()

        if new_posts:
            parts = ["New on the board:\n" + "\n".join(f"{p.handle}: {p.content}" for p in new_posts)]
        else:
            parts = ["No new activity on the board."]
        if new_dms:
            parts.append("\n".join(f"DM from {dm.from_handle}: {dm.content}" for dm in new_dms))
        if agent._energy_log:
            parts.append("Coin changes: " + ". ".join(agent._energy_log))
            agent._energy_log.clear()
        if agent.code_fragment:
            parts.append(f"YOUR CODE FRAGMENT: {agent.code_fragment}")
        if agent.hunger <= 30:
            parts.append(f"WARNING: You are hungry (hunger: {agent.hunger}/100, bread: {agent.bread}). Eat bread or raw flour to restore hunger.")
        if agent.thirst <= 30:
            parts.append(f"WARNING: You are thirsty (thirst: {agent.thirst}/100, water: {agent.water}). Drink water to restore thirst.")

        state = agent._format_state_sections()
        if state:
            parts.append(state)

        from conwai.config import HUNGER_MAX
        tick_content = agent._TICK_TEMPLATE.format(
            timestamp=tick_to_timestamp(ctx.tick),
            coins=int(agent.coins),
            hunger=agent.hunger,
            thirst=agent.thirst,
            flour=agent.flour,
            water=agent.water,
            bread=agent.bread,
            content="\n\n".join(parts),
        )
        agent.messages.append({"role": "user", "content": tick_content})
        chars = self._context_chars(agent)
        compact_pct = int(chars / self.context_window * 100)
        log.info(f"[{agent.handle}] context: {len(agent.messages)} msgs ({chars} chars, {compact_pct}%), coins: {agent.coins}")

    @staticmethod
    def _context_chars(agent: Agent) -> int:
        return sum(len(m.get("content", "")) for m in agent.messages)

    # --- Decision ---

    async def _get_response(self, agent: Agent) -> LLMResponse | None:
        try:
            resp = await self.core.call(
                agent.system_prompt,
                agent.messages,
                tools=self.actions.tool_definitions() if self.actions else None,
            )
        except Exception as e:
            log.error(f"[{agent.handle}] LLM call failed: {e}")
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

    # --- Action ---

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

    # --- Context management ---

    async def _compact(self, agent: Agent, ctx: Context, snapshot_idx: int) -> None:
        async with _compact_semaphore:
            await self._compact_inner(agent, snapshot_idx)

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
            compact_system, snapshot_messages, tools=None,
        )
        if compact_response and compact_response.text:
            summary = compact_response.text.strip()
            new_messages = agent.messages[snapshot_idx:]
            agent.messages = [
                {"role": "user", "content": f"=== YOUR COMPACTED MEMORY ===\n{summary}\n=== END COMPACTED MEMORY ==="}
            ] + new_messages
            log.info(f"[{agent.handle}] compacted ({len(summary)} chars, kept {len(new_messages)} newer msgs)")

    async def _summarize(self, agent: Agent, ctx: Context, msg_count_before: int) -> None:
        from conwai.agent import tick_to_timestamp

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
            agent.messages.append({"role": "user", "content": f"[{tick_to_timestamp(ctx.tick)}] {summary}"})
