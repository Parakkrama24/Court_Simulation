"""Provider-agnostic LLM layer

Agents depend only on ``LLMProvider``; concrete providers are selected by
configuration through ``create_provider``. Vendor SDKs are imported lazily,
so a provider's SDK only needs to be installed if that provider is used.
"""

from .anthropic_provider import DEFAULT_ANTHROPIC_MODEL, AnthropicProvider
from .base import (
    LLMConfigurationError,
    LLMError,
    LLMMessage,
    LLMOutputError,
    LLMProvider,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMTruncatedError,
    MessageRole,
    TokenUsage,
)
from .factory import SUPPORTED_PROVIDERS, create_provider, provider_from_settings
from .interaction_log import InteractionLog, InteractionRecord, hash_request
from .openai_provider import DEFAULT_OPENAI_MODEL, OpenAICompatibleProvider
from .schema import strict_json_schema
from .scripted import ScriptedProvider

__all__ = [
    "DEFAULT_ANTHROPIC_MODEL",
    "AnthropicProvider",
    "LLMConfigurationError",
    "LLMError",
    "LLMMessage",
    "LLMOutputError",
    "LLMProvider",
    "LLMRefusalError",
    "LLMRequest",
    "LLMResponse",
    "LLMTruncatedError",
    "MessageRole",
    "TokenUsage",
    "SUPPORTED_PROVIDERS",
    "create_provider",
    "provider_from_settings",
    "InteractionLog",
    "InteractionRecord",
    "hash_request",
    "DEFAULT_OPENAI_MODEL",
    "OpenAICompatibleProvider",
    "strict_json_schema",
    "ScriptedProvider",
]
