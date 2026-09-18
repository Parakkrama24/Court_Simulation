"""Shared machinery for LLM-backed agents

Every agent follows the same contract: ask the model for structured output,
parse it, validate it against the case record, and - if it fails - show the
model its own output with the exact rejection reasons and ask again. After
``max_attempts`` rejections the agent fails loudly. No agent ever returns
output that did not pass validation.
"""

import json
from typing import Callable, Generic, List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from app.llm import (
    InteractionLog,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    MessageRole,
    TokenUsage,
)

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


class AgentAttempt(BaseModel):
    """One generation attempt and why it was accepted or rejected"""

    attempt: int
    accepted: bool
    errors: List[str] = Field(default_factory=list)
    output: str = ""


class AgentError(Exception):
    """An agent could not produce valid output"""

    def __init__(self, message: str, attempts: Optional[List[AgentAttempt]] = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []


class ValidatedGeneration(Generic[T]):
    """The accepted output of a validated generation, with its history"""

    def __init__(
        self,
        output: T,
        attempts: List[AgentAttempt],
        usage: TokenUsage,
        response: LLMResponse,
    ) -> None:
        self.output = output
        self.attempts = attempts
        self.usage = usage
        self.response = response


# A parser turns model text into (output, rejection reasons). Output may be
# present alongside reasons when the text parsed but failed validation.
Parser = Callable[[str], Tuple[Optional[T], List[str]]]


def parse_model_output(text: str, model: Type[M]) -> Tuple[Optional[M], List[str]]:
    """Parse JSON text into a Pydantic model, describing any failure"""
    try:
        return model.model_validate(json.loads(text)), []
    except json.JSONDecodeError as exc:
        return None, [f"Output is not valid JSON: {exc}"]
    except PydanticValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return None, [f"Output does not match the required schema: {problems}"]


def add_usage(total: TokenUsage, extra: TokenUsage) -> TokenUsage:
    """Sum two usage records"""
    return TokenUsage(
        input_tokens=total.input_tokens + extra.input_tokens,
        output_tokens=total.output_tokens + extra.output_tokens,
        cache_read_input_tokens=total.cache_read_input_tokens + extra.cache_read_input_tokens,
    )


def default_correction_prompt(errors: List[str]) -> str:
    """The follow-up turn after rejected output"""
    listed = "\n".join(f"- {error}" for error in errors)
    return (
        "The court's validation layer rejected your output for these reasons:\n"
        f"{listed}\n\n"
        "Produce a corrected, complete response as a single JSON object. Cite only IDs "
        "that appear in the case record."
    )


def generate_validated(
    *,
    provider: LLMProvider,
    log: InteractionLog,
    agent_id: str,
    prompt_version: str,
    case_id: str,
    request: LLMRequest,
    parse: Parser[T],
    max_attempts: int,
    correction: Callable[[List[str]], str] = default_correction_prompt,
    error_cls: Type[AgentError] = AgentError,
    task: str = "output",
) -> ValidatedGeneration[T]:
    """Generate until the parser accepts the output, logging every attempt"""
    attempts: List[AgentAttempt] = []
    usage = TokenUsage()

    for number in range(1, max_attempts + 1):
        try:
            response = provider.generate(request)
        except LLMError as exc:
            log.record(
                agent_id=agent_id,
                prompt_version=prompt_version,
                request=request,
                case_id=case_id,
                attempt=number,
                error=f"{type(exc).__name__}: {exc}",
            )
            attempts.append(AgentAttempt(attempt=number, accepted=False, errors=[str(exc)]))
            raise error_cls(f"Model call failed on attempt {number}: {exc}", attempts) from exc

        usage = add_usage(usage, response.usage)
        output, errors = parse(response.text)

        log.record(
            agent_id=agent_id,
            prompt_version=prompt_version,
            request=request,
            response=response,
            case_id=case_id,
            attempt=number,
            validation_passed=not errors,
            validation_errors=errors,
        )
        attempts.append(
            AgentAttempt(attempt=number, accepted=not errors, errors=errors, output=response.text)
        )

        if output is not None and not errors:
            return ValidatedGeneration(output, attempts, usage, response)

        # Rejected: show the model its own output and exactly what was wrong.
        request = request.model_copy(
            update={
                "messages": request.messages
                + [
                    LLMMessage(role=MessageRole.ASSISTANT, content=response.text),
                    LLMMessage(role=MessageRole.USER, content=correction(errors)),
                ]
            }
        )

    raise error_cls(
        f"No valid {task} after {max_attempts} attempt(s); "
        f"last errors: {'; '.join(attempts[-1].errors)}",
        attempts,
    )
