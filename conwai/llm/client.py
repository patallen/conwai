from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class LLMProvider(Protocol):
    async def call(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse: ...


@dataclass
class LLMClient:
    model: str = ""
    base_url: str = ""
    api_key: str = "ollama"
    extra_body: dict = field(
        default_factory=lambda: {"chat_template_kwargs": {"enable_thinking": False}}
    )
    _client: AsyncOpenAI | None = field(default=None, repr=False)

    def __post_init__(self):
        if not self.model:
            self.model = os.environ.get("CONWAI_LLM_MODEL", "")
        if not self.base_url:
            self.base_url = os.environ.get(
                "CONWAI_LLM_BASE_URL", "http://localhost:8080/v1"
            )
        self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    max_tokens: int | None = 2048
    temperature: float = 0.7

    async def call(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        all_messages = [{"role": "system", "content": system}, *messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
            "temperature": self.temperature,
            "extra_body": self.extra_body,
        }
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if tools:
            kwargs["tools"] = tools
        import structlog

        _log = structlog.get_logger()
        assert self._client is not None
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            _log.error(
                "llm_call_failed",
                error=str(e),
                model=self.model,
                base_url=self.base_url,
            )
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
    _client: Any = field(default=None, repr=False)

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


def tool_schema(name: str, description: str, parameters: dict | None = None) -> dict:
    """Build an OpenAI-compatible function tool schema."""
    params = parameters or {}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": list(params.keys()),
            },
        },
    }
