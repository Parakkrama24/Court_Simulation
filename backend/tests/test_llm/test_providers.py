"""Tests for the Anthropic and OpenAI-compatible providers

The SDK clients are replaced with fakes that record the call and return
canned responses, so these tests check request shape and response handling
without network access, API keys, or the SDKs being installed.
"""

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from app.llm import (
    AnthropicProvider,
    LLMError,
    LLMMessage,
    LLMRefusalError,
    LLMRequest,
    LLMTruncatedError,
    MessageRole,
    OpenAICompatibleProvider,
)

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def make_request(json_schema: Any = SCHEMA) -> LLMRequest:
    return LLMRequest(
        system="You are a test.",
        messages=[
            LLMMessage(role=MessageRole.USER, content="First"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Reply"),
            LLMMessage(role=MessageRole.USER, content="Second"),
        ],
        json_schema=json_schema,
        schema_name="test_output",
        max_tokens=1234,
    )


class FakeCreate:
    """Callable that records kwargs and returns (or raises) a canned value"""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


# ============================================================================
# Anthropic
# ============================================================================


def anthropic_message(
    text: str = '{"answer": "yes"}', stop_reason: str = "end_turn", **extra: Any
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=5),
        model="claude-opus-5",
        _request_id="req_123",
        **extra,
    )


def anthropic_client(result: Any) -> SimpleNamespace:
    return SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(create=FakeCreate(result))),
        messages=SimpleNamespace(create=FakeCreate(result)),
    )


class TestAnthropicProvider:
    def test_request_shape(self):
        client = anthropic_client(anthropic_message())
        AnthropicProvider(client=client).generate(make_request())

        params = client.beta.messages.create.calls[0]
        assert params["model"] == "claude-opus-5"
        assert params["max_tokens"] == 1234
        assert params["system"] == "You are a test."
        assert [m["role"] for m in params["messages"]] == ["user", "assistant", "user"]
        assert params["output_config"] == {
            "effort": "high",
            "format": {"type": "json_schema", "schema": SCHEMA},
        }

    def test_refusal_fallback_enabled_by_default(self):
        client = anthropic_client(anthropic_message())
        AnthropicProvider(client=client).generate(make_request())

        params = client.beta.messages.create.calls[0]
        assert params["betas"] == ["server-side-fallback-2026-07-01"]
        assert params["fallbacks"] == "default"
        assert client.messages.create.calls == []

    def test_fallback_can_be_disabled(self):
        client = anthropic_client(anthropic_message())
        AnthropicProvider(client=client, use_refusal_fallback=False).generate(make_request())

        params = client.messages.create.calls[0]
        assert "betas" not in params
        assert "fallbacks" not in params
        assert client.beta.messages.create.calls == []

    def test_no_schema_means_no_format(self):
        client = anthropic_client(anthropic_message("plain"))
        AnthropicProvider(client=client, effort=None).generate(make_request(json_schema=None))
        assert "output_config" not in client.beta.messages.create.calls[0]

    def test_response_parsing_returns_text_only(self):
        client = anthropic_client(anthropic_message())
        response = AnthropicProvider(client=client).generate(make_request())

        assert response.text == '{"answer": "yes"}'
        assert response.parse_json() == {"answer": "yes"}
        assert response.provider == "anthropic"
        assert response.model == "claude-opus-5"
        assert response.request_id == "req_123"
        assert response.usage.input_tokens == 100
        assert response.usage.output_tokens == 20
        assert response.usage.cache_read_input_tokens == 5
        assert response.latency_ms >= 0

    def test_refusal_raises(self):
        message = anthropic_message(
            text="",
            stop_reason="refusal",
            stop_details=SimpleNamespace(category="cyber", explanation=""),
        )
        with pytest.raises(LLMRefusalError, match="cyber"):
            AnthropicProvider(client=anthropic_client(message)).generate(make_request())

    def test_truncation_raises(self):
        message = anthropic_message(text='{"answer": "y', stop_reason="max_tokens")
        with pytest.raises(LLMTruncatedError):
            AnthropicProvider(client=anthropic_client(message)).generate(make_request())

    def test_sdk_errors_are_wrapped(self):
        client = anthropic_client(RuntimeError("connection reset"))
        with pytest.raises(LLMError, match="connection reset"):
            AnthropicProvider(client=client).generate(make_request())


# ============================================================================
# OpenAI-compatible
# ============================================================================


def openai_completion(
    content: str = '{"answer": "yes"}', finish_reason: str = "stop", refusal: Any = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id="chatcmpl-1",
        model="gpt-4o",
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, refusal=refusal),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=80, completion_tokens=15),
    )


def openai_client(result: Any) -> SimpleNamespace:
    completions = SimpleNamespace(create=FakeCreate(result))
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class TestOpenAICompatibleProvider:
    def test_request_shape(self):
        client = openai_client(openai_completion())
        OpenAICompatibleProvider(client=client).generate(make_request())

        params = client.chat.completions.create.calls[0]
        assert params["model"] == "gpt-4o"
        assert params["max_completion_tokens"] == 1234
        assert params["messages"][0] == {"role": "system", "content": "You are a test."}
        assert [m["role"] for m in params["messages"][1:]] == ["user", "assistant", "user"]
        assert params["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "test_output", "schema": SCHEMA, "strict": True},
        }

    def test_json_mode_for_servers_without_schema_support(self):
        client = openai_client(openai_completion())
        OpenAICompatibleProvider(client=client, json_mode=True).generate(make_request())
        assert client.chat.completions.create.calls[0]["response_format"] == {
            "type": "json_object"
        }

    def test_response_parsing(self):
        response = OpenAICompatibleProvider(client=openai_client(openai_completion())).generate(
            make_request()
        )
        assert response.parse_json() == {"answer": "yes"}
        assert response.usage.input_tokens == 80
        assert response.usage.output_tokens == 15
        assert response.request_id == "chatcmpl-1"

    def test_provider_name_is_configurable(self):
        provider = OpenAICompatibleProvider(
            model="llama3.1", client=openai_client(openai_completion()), provider_name="local"
        )
        assert provider.generate(make_request()).provider == "local"

    def test_refusal_raises(self):
        client = openai_client(openai_completion(content="", refusal="I can't help with that"))
        with pytest.raises(LLMRefusalError):
            OpenAICompatibleProvider(client=client).generate(make_request())

    def test_content_filter_raises_refusal(self):
        client = openai_client(openai_completion(finish_reason="content_filter"))
        with pytest.raises(LLMRefusalError):
            OpenAICompatibleProvider(client=client).generate(make_request())

    def test_length_raises_truncation(self):
        client = openai_client(openai_completion(finish_reason="length"))
        with pytest.raises(LLMTruncatedError):
            OpenAICompatibleProvider(client=client).generate(make_request())

    def test_sdk_errors_are_wrapped(self):
        client = openai_client(RuntimeError("timeout"))
        with pytest.raises(LLMError, match="timeout"):
            OpenAICompatibleProvider(client=client).generate(make_request())
