from __future__ import annotations

from typing import Protocol, runtime_checkable

from conwai.llm import LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    async def call(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse: ...
