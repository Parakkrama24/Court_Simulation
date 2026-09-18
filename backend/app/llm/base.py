"""Provider-agnostic LLM interface

Agents talk to language models only through ``LLMProvider``. A provider takes
an ``LLMRequest`` (system prompt, messages, optional JSON schema) and returns
an ``LLMResponse`` (text, parsed JSON, usage, latency). Nothing above this
layer knows which vendor - or which SDK - produced the answer.
"""

import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Conversation roles shared by every provider"""

    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(BaseModel):
    """One conversation turn"""

    role: MessageRole
    content: str


class LLMRequest(BaseModel):
    """A single generation request"""

    system: str = Field(..., description="System prompt: role, rules, and output contract")
    messages: List[LLMMessage] = Field(..., min_length=1, description="Conversation so far")
    json_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="If set, the response must be JSON matching this schema"
    )
    schema_name: str = Field(default="response", description="Name for the output schema")
    max_tokens: int = Field(default=16000, gt=0, description="Output token ceiling")


class TokenUsage(BaseModel):
    """Token accounting as reported by the provider"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMResponse(BaseModel):
    """A provider-neutral generation result"""

    text: str = Field(..., description="Final text output (never hidden reasoning)")
    provider: str = Field(..., description="Provider that served the request")
    model: str = Field(..., description="Model that served the request")
    stop_reason: str = Field(default="", description="Provider stop/finish reason")
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = Field(default=0.0, ge=0.0)
    request_id: str = Field(default="", description="Provider request ID, if any")

    def parse_json(self) -> Any:
        """Parse the text as JSON, raising LLMOutputError if it is not"""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:
            raise LLMOutputError(f"Model output is not valid JSON: {exc}") from exc


# ============================================================================
# Errors
# ============================================================================


class LLMError(Exception):
    """Base class for provider failures"""


class LLMConfigurationError(LLMError):
    """The provider is misconfigured or its SDK is not installed"""


class LLMRefusalError(LLMError):
    """The model declined to answer"""


class LLMTruncatedError(LLMError):
    """The model hit its output limit before finishing"""


class LLMOutputError(LLMError):
    """The model answered, but not in the required format"""


# ============================================================================
# Provider interface
# ============================================================================


class LLMProvider(ABC):
    """Interface every model provider implements"""

    #: Short provider name recorded in logs ("anthropic", "openai", ...)
    name: str = "unknown"

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Run one generation request"""
