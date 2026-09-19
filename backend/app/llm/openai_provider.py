"""OpenAI-compatible provider

Speaks the Chat Completions API, which OpenAI and most local model servers
(Ollama, vLLM, LM Studio, llama.cpp server) implement. Point ``base_url`` at a
local server to run the simulation against a local model.

Structured output uses ``response_format`` with a strict ``json_schema``.
Servers that do not support schema-constrained output can use
``json_mode=True`` instead, which only requests *some* JSON object; the
schema is then enforced by validation after parsing.
"""

import time
from typing import Any, Dict, Optional

from .base import (
    LLMConfigurationError,
    LLMError,
    LLMProvider,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMTruncatedError,
    TokenUsage,
)

DEFAULT_OPENAI_MODEL = "gpt-4o"


class OpenAICompatibleProvider(LLMProvider):
    """Any server that implements the OpenAI Chat Completions API"""

    name = "openai"

    def __init__(
        self,
        model: str = DEFAULT_OPENAI_MODEL,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        json_mode: bool = False,
        max_retries: int = 2,
        timeout: float = 600.0,
        client: Any = None,
        provider_name: str = "openai",
    ) -> None:
        super().__init__(model)
        self.json_mode = json_mode
        self.name = provider_name
        self._client = client or self._build_client(api_key, base_url, max_retries, timeout)

    @staticmethod
    def _build_client(
        api_key: Optional[str], base_url: Optional[str], max_retries: int, timeout: float
    ) -> Any:
        try:
            import openai
        except ImportError as exc:
            raise LLMConfigurationError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc

        kwargs: Dict[str, Any] = {"max_retries": max_retries, "timeout": timeout}
        if api_key:
            kwargs["api_key"] = api_key
        elif base_url:
            # Local servers usually ignore the key, but the SDK requires one.
            kwargs["api_key"] = "not-needed"
        if base_url:
            kwargs["base_url"] = base_url

        try:
            return openai.OpenAI(**kwargs)
        except Exception as exc:  # usually a missing API key
            raise LLMConfigurationError(
                f"Could not create the OpenAI client: {exc}. Set OPENAI_API_KEY in your "
                "environment or in .env, or point --provider local at a local server."
            ) from exc

    def build_params(self, request: LLMRequest) -> Dict[str, Any]:
        """Chat Completions parameters for a request (exposed for logging and tests)"""
        messages = [{"role": "system", "content": request.system}]
        messages += [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
        ]

        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": request.max_tokens,
        }

        if request.json_schema is not None:
            if self.json_mode:
                params["response_format"] = {"type": "json_object"}
            else:
                params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema_name,
                        "schema": request.json_schema,
                        "strict": True,
                    },
                }

        return params

    def generate(self, request: LLMRequest) -> LLMResponse:
        params = self.build_params(request)

        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**params)
        except LLMError:
            raise
        except Exception as exc:  # SDK errors are re-raised with provider context
            raise LLMError(f"{self.name} request failed: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1000

        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", "") or ""
        message = choice.message

        refusal = getattr(message, "refusal", None)
        if refusal or finish_reason == "content_filter":
            raise LLMRefusalError(f"Model declined the request: {refusal or finish_reason}")
        if finish_reason == "length":
            raise LLMTruncatedError(
                f"Output reached max_completion_tokens={request.max_tokens} before completing"
            )

        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=message.content or "",
            provider=self.name,
            model=getattr(response, "model", self.model) or self.model,
            stop_reason=finish_reason,
            usage=TokenUsage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            ),
            latency_ms=latency_ms,
            request_id=str(getattr(response, "id", "") or ""),
        )
