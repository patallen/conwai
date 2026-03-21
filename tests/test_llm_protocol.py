from conwai.llm import LLMClient, AnthropicLLMClient
from conwai.llm_protocol import LLMProvider


def test_openai_client_satisfies_protocol():
    assert issubclass(LLMClient, LLMProvider) or isinstance(LLMClient.__new__(LLMClient), LLMProvider)


def test_anthropic_client_satisfies_protocol():
    assert issubclass(AnthropicLLMClient, LLMProvider) or isinstance(
        AnthropicLLMClient.__new__(AnthropicLLMClient), LLMProvider
    )


def test_protocol_exists():
    from conwai.llm_protocol import LLMProvider
    assert hasattr(LLMProvider, "call")
