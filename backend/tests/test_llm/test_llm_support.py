"""Tests for schema generation, the scripted provider, logging, and the factory"""

import json
from types import SimpleNamespace
from typing import List, Optional

import pytest
from pydantic import BaseModel, Field

from app.llm import (
    AnthropicProvider,
    InteractionLog,
    LLMConfigurationError,
    LLMError,
    LLMMessage,
    LLMOutputError,
    LLMRequest,
    LLMResponse,
    MessageRole,
    OpenAICompatibleProvider,
    ScriptedProvider,
    TokenUsage,
    create_provider,
    hash_request,
    provider_from_settings,
    strict_json_schema,
)


def make_request(content: str = "Hello") -> LLMRequest:
    return LLMRequest(
        system="System",
        messages=[LLMMessage(role=MessageRole.USER, content=content)],
        json_schema={"type": "object"},
    )


# ============================================================================
# strict_json_schema
# ============================================================================


class Inner(BaseModel):
    title: str = Field(..., description="A field literally named title")
    score: float = Field(..., ge=0.0, le=1.0)


class Outer(BaseModel):
    name: str = Field(..., min_length=1)
    items: List[Inner]
    note: Optional[str] = None


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


class TestStrictJsonSchema:
    def test_references_are_inlined(self):
        schema = strict_json_schema(Outer)
        text = json.dumps(schema)
        assert "$ref" not in text
        assert "$defs" not in text

    def test_every_object_is_closed_and_fully_required(self):
        for node in _walk(strict_json_schema(Outer)):
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])

    def test_unsupported_keywords_are_stripped(self):
        text = json.dumps(strict_json_schema(Outer))
        for keyword in ('"minimum"', '"maximum"', '"minLength"', '"default"'):
            assert keyword not in text

    def test_property_names_matching_keywords_survive(self):
        schema = strict_json_schema(Outer)
        inner = schema["properties"]["items"]["items"]
        assert "title" in inner["properties"]
        assert inner["properties"]["title"]["description"] == "A field literally named title"


# ============================================================================
# LLMResponse
# ============================================================================


class TestLLMResponse:
    def test_parse_json(self):
        assert LLMResponse(text='{"a": 1}', provider="p", model="m").parse_json() == {"a": 1}

    def test_parse_json_rejects_invalid(self):
        with pytest.raises(LLMOutputError):
            LLMResponse(text="not json", provider="p", model="m").parse_json()

    def test_total_tokens(self):
        assert TokenUsage(input_tokens=3, output_tokens=4).total_tokens == 7


# ============================================================================
# ScriptedProvider
# ============================================================================


class TestScriptedProvider:
    def test_replays_steps_in_order(self):
        provider = ScriptedProvider(["first", {"second": True}, lambda r: r.system])
        assert provider.generate(make_request()).text == "first"
        assert json.loads(provider.generate(make_request()).text) == {"second": True}
        assert provider.generate(make_request()).text == "System"
        assert provider.remaining == 0

    def test_records_requests(self):
        provider = ScriptedProvider(["x"])
        provider.generate(make_request("recorded"))
        assert provider.requests[0].messages[0].content == "recorded"

    def test_raises_scripted_exceptions(self):
        provider = ScriptedProvider([LLMError("boom")])
        with pytest.raises(LLMError, match="boom"):
            provider.generate(make_request())

    def test_errors_when_exhausted(self):
        with pytest.raises(LLMError, match="no responses left"):
            ScriptedProvider([]).generate(make_request())


# ============================================================================
# InteractionLog
# ============================================================================


class TestInteractionLog:
    def test_records_every_required_field(self):
        log = InteractionLog()
        request = make_request()
        response = LLMResponse(
            text="{}",
            provider="scripted",
            model="m1",
            usage=TokenUsage(input_tokens=10, output_tokens=2),
            latency_ms=12.5,
            request_id="r1",
        )
        record = log.record(
            agent_id="judge_agent",
            prompt_version="judge.v1",
            request=request,
            response=response,
            case_id="CASE_001",
            attempt=2,
            validation_passed=False,
            validation_errors=["bad id"],
        )
        assert record.agent_id == "judge_agent"
        assert record.prompt_version == "judge.v1"
        assert record.model == "m1"
        assert record.timestamp
        assert record.input_state["system"] == "System"
        assert record.output == "{}"
        assert record.usage.input_tokens == 10
        assert record.latency_ms == 12.5
        assert record.validation_passed is False
        assert record.validation_errors == ["bad id"]
        assert record.attempt == 2

    def test_input_hash_is_stable(self):
        assert hash_request(make_request()) == hash_request(make_request())
        assert hash_request(make_request("a")) != hash_request(make_request("b"))

    def test_failed_calls_are_logged(self):
        log = InteractionLog()
        record = log.record(
            agent_id="judge_agent",
            prompt_version="judge.v1",
            request=make_request(),
            error="LLMRefusalError: declined",
        )
        assert record.validation_passed is None
        assert record.error.startswith("LLMRefusalError")

    def test_writes_json_lines(self, tmp_path):
        path = tmp_path / "logs" / "interactions.jsonl"
        log = InteractionLog(path)
        for _ in range(2):
            log.record(agent_id="a", prompt_version="v", request=make_request())
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["agent_id"] == "a"

    def test_totals_and_filtering(self):
        log = InteractionLog()
        usage_response = LLMResponse(
            text="", provider="p", model="m", usage=TokenUsage(input_tokens=5, output_tokens=1)
        )
        for agent_id in ("a", "b"):
            log.record(
                agent_id=agent_id,
                prompt_version="v",
                request=make_request(),
                response=usage_response,
            )
        assert log.total_usage.input_tokens == 10
        assert len(log.for_agent("a")) == 1


# ============================================================================
# Factory
# ============================================================================


class TestFactory:
    def test_anthropic(self):
        provider = create_provider("anthropic", client=SimpleNamespace())
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-opus-5"

    def test_openai(self):
        provider = create_provider("OpenAI", client=SimpleNamespace())
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.model == "gpt-4o"
        assert provider.name == "openai"

    def test_local(self):
        provider = create_provider("local", model="llama3.1", client=SimpleNamespace())
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.name == "local"

    def test_local_requires_model(self):
        with pytest.raises(LLMConfigurationError):
            create_provider("local")

    def test_unknown_provider(self):
        with pytest.raises(LLMConfigurationError, match="Unknown LLM provider"):
            create_provider("mystery")

    def test_from_settings(self, monkeypatch):
        captured = {}

        def fake_create(name, **kwargs):
            captured["name"] = name
            captured.update(kwargs)
            return "provider"

        monkeypatch.setattr("app.llm.factory.create_provider", fake_create)
        settings = SimpleNamespace(
            llm_provider="anthropic",
            anthropic_model="claude-opus-5",
            anthropic_api_key="",
            anthropic_effort="xhigh",
            anthropic_refusal_fallback=False,
        )
        assert provider_from_settings(settings) == "provider"
        assert captured == {
            "name": "anthropic",
            "model": "claude-opus-5",
            "api_key": None,
            "effort": "xhigh",
            "use_refusal_fallback": False,
        }
