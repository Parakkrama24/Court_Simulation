"""Scripted provider for tests and offline runs

Returns pre-written responses in order and records every request it saw.
It makes the agent layer testable without network access or API cost, and
lets tests stage exact failure sequences (fabricated IDs, malformed JSON,
refusals) to prove the validation loop handles them.
"""

import json
from typing import Any, Callable, List, Sequence, Union

from .base import LLMError, LLMProvider, LLMRequest, LLMResponse, TokenUsage

# A scripted step is literal text, a JSON-serialisable object, an exception to
# raise, or a callable that builds text from the request.
ScriptedStep = Union[str, dict, list, Exception, Callable[[LLMRequest], str]]


class ScriptedProvider(LLMProvider):
    """Replays a fixed sequence of responses"""

    name = "scripted"

    def __init__(self, steps: Sequence[ScriptedStep], model: str = "scripted-model") -> None:
        super().__init__(model)
        self._steps: List[ScriptedStep] = list(steps)
        self.requests: List[LLMRequest] = []

    @property
    def remaining(self) -> int:
        """Steps not yet consumed"""
        return len(self._steps)

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._steps:
            raise LLMError("ScriptedProvider has no responses left")

        step: Any = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            text = step(request)
        elif isinstance(step, (dict, list)):
            text = json.dumps(step)
        else:
            text = str(step)

        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            stop_reason="end_turn",
            usage=TokenUsage(
                input_tokens=sum(len(m.content) for m in request.messages) // 4,
                output_tokens=len(text) // 4,
            ),
            latency_ms=0.0,
            request_id=f"scripted-{len(self.requests)}",
        )
