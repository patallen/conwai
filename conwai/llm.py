import os
from dataclasses import dataclass, field

from openai import AsyncOpenAI


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

    async def call(self, messages: list[dict]) -> tuple[str, int, int]:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            extra_body=self.extra_body,
        )
        usage = response.usage
        return (
            response.choices[0].message.content,
            usage.prompt_tokens,
            usage.completion_tokens,
        )


@dataclass
class AnthropicLLMClient:
    model: str = "claude-sonnet-4-20250514"
    api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    max_tokens: int = 300
    _client: object = field(default=None, repr=False)

    def __post_init__(self):
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=self.api_key)

    async def call(self, messages: list[dict]) -> tuple[str, int, int]:
        system = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        response = await self._client.messages.create(
            model=self.model,
            system=system,
            messages=chat_messages,
            max_tokens=self.max_tokens,
            temperature=0.7,
        )
        text = response.content[0].text
        return (
            text,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
