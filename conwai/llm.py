from dataclasses import dataclass, field

from openai import AsyncOpenAI


@dataclass
class LLMClient:
    model: str = "/mnt/models/Qwen3.5-9B-AWQ"
    base_url: str = "http://ai-lab.lan:8080/v1"
    api_key: str = "ollama"
    extra_body: dict = field(default_factory=lambda: {"chat_template_kwargs": {"enable_thinking": False}})
    _client: AsyncOpenAI = field(default=None, repr=False)

    def __post_init__(self):
        self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    async def call(self, messages: list[dict]) -> tuple[str, int, int]:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            extra_body=self.extra_body,
        )
        usage = response.usage
        return response.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens
