"""LLM inference process: calls the model and parses tool calls into decisions."""

from __future__ import annotations

import json
import logging
from typing import Any

from conwai.cognition import Decision
from conwai.llm_protocol import LLMProvider

log = logging.getLogger("conwai")


class InferenceProcess:
    """Call an LLM with the assembled message snapshot and write decisions to the board."""

    def __init__(
        self,
        client: LLMProvider,
        tools: list[dict] | None = None,
    ):
        self.client = client
        self.tools = tools

    async def run(self, board: dict[str, Any]) -> None:
        snapshot: list[dict] = board.get("messages_snapshot", [])
        system_prompt: str = board.get("system_prompt", "")
        state = board.setdefault("state", {})
        messages: list[dict] = state.setdefault("messages", [])
        percept = board.get("percept")
        agent_id = getattr(percept, "agent_id", "?")

        try:
            resp = await self.client.call(system_prompt, snapshot, tools=self.tools)
        except Exception as e:
            log.error(f"[{agent_id}] LLM call failed: {e}")
            return

        if not resp.text and not resp.tool_calls:
            return

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

        messages.append(assistant_msg)
        log.info(
            f"[{agent_id}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): "
            f"{resp.text[:200] if resp.text else '(no text)'}"
        )

        decisions: list[Decision] = board.setdefault("decisions", [])
        for tc in resp.tool_calls:
            decisions.append(Decision(tc.name, tc.args))
