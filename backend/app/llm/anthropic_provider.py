"""Anthropic provider (Claude, via the official Anthropic SDK)

Structured output uses ``output_config.format`` with a strict JSON schema, so
the first text block of a successful response is guaranteed to be JSON.
Refusals and truncation are surfaced as typed errors rather than returned as
if they were answers.

Server-side refusal fallback (``fallbacks: "default"``) is enabled by default:
if the model's safety classifiers decline a request, the API re-runs it on
Anthropic's recommended fallback model inside the same call. Disable it with
``use_refusal_fallback=False``.
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

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    """Claude models through the Anthropic Messages API"""

    name = "anthropic"

    def __init__(
        self,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        api_key: Optional[str] = None,
        effort: Optional[str] = "high",
        use_refusal_fallback: bool = True,
        max_retries: int = 2,
        timeout: float = 600.0,
        client: Any = None,
    ) -> None:
        super().__init__(model)
        self.effort = effort
        self.use_refusal_fallback = use_refusal_fallback
        self._client = client or self._build_client(api_key, max_retries, timeout)

    @staticmethod
    def _build_client(api_key: Optional[str], max_retries: int, timeout: float) -> Any:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMConfigurationError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc

        # With no explicit key the SDK resolves credentials from the
        # environment (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or a profile).
        kwargs: Dict[str, Any] = {"max_retries": max_retries, "timeout": timeout}
        if api_key:
            kwargs["api_key"] = api_key
        return anthropic.Anthropic(**kwargs)

    def build_params(self, request: LLMRequest) -> Dict[str, Any]:
        """Messages API parameters for a request (exposed for logging and tests)"""
        params: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }

        output_config: Dict[str, Any] = {}
        if self.effort:
            output_config["effort"] = self.effort
        if request.json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
        if output_config:
            params["output_config"] = output_config

        if self.use_refusal_fallback:
            params["betas"] = [REFUSAL_FALLBACK_BETA]
            params["fallbacks"] = "default"

        return params

    def generate(self, request: LLMRequest) -> LLMResponse:
        params = self.build_params(request)
        messages_api = (
            self._client.beta.messages if self.use_refusal_fallback else self._client.messages
        )

        started = time.perf_counter()
        try:
            response = messages_api.create(**params)
        except LLMError:
            raise
        except Exception as exc:  # SDK errors are re-raised with provider context
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1000

        # Check why generation stopped before reading content.
        stop_reason = getattr(response, "stop_reason", "") or ""
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMRefusalError(f"Model declined the request (category: {category})")
        if stop_reason == "max_tokens":
            raise LLMTruncatedError(
                f"Output reached max_tokens={request.max_tokens} before completing"
            )

        # Only text blocks are returned; thinking blocks are never exposed.
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=getattr(response, "model", self.model) or self.model,
            stop_reason=stop_reason,
            usage=TokenUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            ),
            latency_ms=latency_ms,
            request_id=str(getattr(response, "_request_id", "") or ""),
        )
