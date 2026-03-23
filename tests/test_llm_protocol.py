from conwai.llm import AnthropicLLMClient, LLMClient, LLMProvider


def test_openai_client_satisfies_protocol():
    assert issubclass(LLMClient, LLMProvider) or isinstance(
        LLMClient.__new__(LLMClient), LLMProvider
    )


def test_anthropic_client_satisfies_protocol():
    assert issubclass(AnthropicLLMClient, LLMProvider) or isinstance(
        AnthropicLLMClient.__new__(AnthropicLLMClient), LLMProvider
    )


def test_protocol_exists():
    from conwai.llm import LLMProvider

    assert hasattr(LLMProvider, "call")
