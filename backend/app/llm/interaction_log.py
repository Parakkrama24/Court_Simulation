"""LLM interaction logging

Every model call is recorded: which agent made it, under which prompt
version, against which model, with what input, what came back, how many
tokens it used, how long it took, and whether the output passed validation.

Only final outputs are stored. Hidden chain-of-thought is never requested or
logged; agents are asked for concise structured rationales instead.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.domain import utc_now

from .base import LLMRequest, LLMResponse, TokenUsage


class InteractionRecord(BaseModel):
    """One logged model call"""

    agent_id: str = Field(..., description="Agent that made the call")
    case_id: str = Field(default="", description="Case being simulated")
    prompt_version: str = Field(..., description="Version tag of the prompt template")
    attempt: int = Field(default=1, ge=1, description="Attempt number within one agent task")
    provider: str = Field(default="", description="Provider that served the call")
    model: str = Field(default="", description="Model that served the call")
    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())
    input_hash: str = Field(..., description="SHA-256 of the full request, for reproducibility")
    input_state: Dict[str, Any] = Field(
        default_factory=dict, description="The request as sent (system prompt and messages)"
    )
    output: str = Field(default="", description="Raw model output")
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = Field(default=0.0, ge=0.0)
    request_id: str = Field(default="")
    validation_passed: Optional[bool] = Field(
        default=None, description="None when the call failed before validation"
    )
    validation_errors: List[str] = Field(default_factory=list)
    error: str = Field(default="", description="Provider error, if the call failed")


def hash_request(request: LLMRequest) -> str:
    """Stable fingerprint of a request"""
    payload = json.dumps(request.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class InteractionLog:
    """In-memory interaction log with an optional JSON Lines file sink"""

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self.records: List[InteractionRecord] = []
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        agent_id: str,
        prompt_version: str,
        request: LLMRequest,
        response: Optional[LLMResponse] = None,
        case_id: str = "",
        attempt: int = 1,
        validation_passed: Optional[bool] = None,
        validation_errors: Optional[List[str]] = None,
        error: str = "",
    ) -> InteractionRecord:
        """Append one interaction and return it"""
        record = InteractionRecord(
            agent_id=agent_id,
            case_id=case_id,
            prompt_version=prompt_version,
            attempt=attempt,
            provider=response.provider if response else "",
            model=response.model if response else "",
            input_hash=hash_request(request),
            input_state=request.model_dump(mode="json", exclude={"json_schema"}),
            output=response.text if response else "",
            usage=response.usage if response else TokenUsage(),
            latency_ms=response.latency_ms if response else 0.0,
            request_id=response.request_id if response else "",
            validation_passed=validation_passed,
            validation_errors=list(validation_errors or []),
            error=error,
        )
        self.records.append(record)
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
        return record

    def for_agent(self, agent_id: str) -> List[InteractionRecord]:
        """Records made by one agent"""
        return [r for r in self.records if r.agent_id == agent_id]

    @property
    def total_usage(self) -> TokenUsage:
        """Token usage summed across every logged call"""
        return TokenUsage(
            input_tokens=sum(r.usage.input_tokens for r in self.records),
            output_tokens=sum(r.usage.output_tokens for r in self.records),
            cache_read_input_tokens=sum(r.usage.cache_read_input_tokens for r in self.records),
        )
