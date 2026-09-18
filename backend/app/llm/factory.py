"""Provider selection

Maps a provider name from configuration to a concrete provider. This is the
only place that knows the full set of providers; everything else depends on
``LLMProvider``.
"""

from typing import Any, Optional

from .anthropic_provider import DEFAULT_ANTHROPIC_MODEL, AnthropicProvider
from .base import LLMConfigurationError, LLMProvider
from .openai_provider import DEFAULT_OPENAI_MODEL, OpenAICompatibleProvider

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible endpoint

SUPPORTED_PROVIDERS = ("anthropic", "openai", "local")


def create_provider(
    provider: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **options: Any,
) -> LLMProvider:
    """Build a provider by name

    - ``anthropic``: Claude via the Anthropic SDK
    - ``openai``: OpenAI via the OpenAI SDK
    - ``local``: any OpenAI-compatible local server (Ollama by default)
    """
    name = provider.strip().lower()

    if name == "anthropic":
        return AnthropicProvider(model=model or DEFAULT_ANTHROPIC_MODEL, api_key=api_key, **options)

    if name == "openai":
        return OpenAICompatibleProvider(
            model=model or DEFAULT_OPENAI_MODEL, api_key=api_key, base_url=base_url, **options
        )

    if name == "local":
        if not model:
            raise LLMConfigurationError("The 'local' provider requires a model name")
        options.setdefault("provider_name", "local")
        return OpenAICompatibleProvider(
            model=model,
            api_key=api_key,
            base_url=base_url or DEFAULT_LOCAL_BASE_URL,
            **options,
        )

    raise LLMConfigurationError(
        f"Unknown LLM provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
    )


def provider_from_settings(settings: Any) -> LLMProvider:
    """Build the provider described by application settings"""
    name = settings.llm_provider.strip().lower()

    if name == "anthropic":
        return create_provider(
            "anthropic",
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key or None,
            effort=settings.anthropic_effort or None,
            use_refusal_fallback=settings.anthropic_refusal_fallback,
        )
    if name == "openai":
        return create_provider(
            "openai",
            model=settings.openai_model,
            api_key=settings.openai_api_key or None,
            base_url=settings.openai_base_url or None,
        )
    if name == "local":
        return create_provider(
            "local",
            model=settings.local_model,
            base_url=settings.local_base_url,
            json_mode=settings.local_json_mode,
        )

    return create_provider(name)
