from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from openai import AsyncOpenAI


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    prompt_tokens: int
    completion_tokens: int


@dataclass
class LLMClient:
    model: str = "/mnt/models/Qwen3.5-9B-AWQ"
    base_url: str = "http://ai-lab.lan:8080/v1"
    api_key: str = "ollama"
    extra_body: dict = field(
        default_factory=lambda: {"chat_template_kwargs": {"enable_thinking": False}}
    )
    _client: AsyncOpenAI = field(default=None, repr=False)

    def __post_init__(self):
        self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    max_tokens: int | None = 2048

    async def call(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        all_messages = [{"role": "system", "content": system}, *messages]
        kwargs = {
            "model": self.model,
            "messages": all_messages,
            "temperature": 0.7,
            "extra_body": self.extra_body,
        }
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if tools:
            kwargs["tools"] = tools
        import logging
        _log = logging.getLogger("conwai")
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            _log.error(f"LLM call failed: {e} | model={self.model} base_url={self.base_url}")
            raise
        usage = response.usage
        msg = response.choices[0].message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))

        return LLMResponse(
            text=msg.content or "",
            tool_calls=tool_calls,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )


@dataclass
class AnthropicLLMClient:
    model: str = "claude-sonnet-4-20250514"
    api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    max_tokens: int = 600
    _client: object = field(default=None, repr=False)

    def __post_init__(self):
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=self.api_key)

    async def call(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "system": system,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.7,
        }
        if tools:
            anthropic_tools = []
            for t in tools:
                fn = t["function"]
                anthropic_tools.append(
                    {
                        "name": fn["name"],
                        "description": fn["description"],
                        "input_schema": fn["parameters"],
                    }
                )
            kwargs["tools"] = anthropic_tools

        response = await self._client.messages.create(**kwargs)

        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, args=block.input or {})
                )

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
