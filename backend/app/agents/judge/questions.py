"""JUDGE_QUESTIONS: the judge requests more when an argument lacks evidence

Spec section 14: "The Judge should be able to request additional analysis if
an argument lacks evidence." When the evidence review finds an argument
unsupported by what it cites, the judge puts questions to the party that made
it. The party must answer each one by citing the record - or narrow or
withdraw the claim - and the Evidence Agent then reviews the answers.

The judge asks; it does not decide here. The questioning prompt is separate
from the decision prompt, which tells the judge to decide every charge.
"""

import json
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from app.domain import (
    Argument,
    Case,
    CourtMessage,
    CourtStage,
    JudgeQuestion,
    MessageType,
)
from app.llm import LLMMessage, LLMRequest, MessageRole, TokenUsage, strict_json_schema
from app.rules import CaseEvaluation

from ..base import AgentAttempt, AgentError, generate_validated, parse_model_output
from ..record import render_case_record

if TYPE_CHECKING:
    from .agent import JudgeAgent

QUESTIONS_PROMPT_VERSION = "judge-questions.v1"
MAX_QUESTIONS_PER_ROUND = 6

QUESTIONS_SYSTEM_PROMPT = """\
You are the presiding judge in a court simulation set in the Republic of Arandia, a \
fictional jurisdiction. This is a research simulation: it does not provide legal advice \
and does not determine anyone's real legal rights or obligations.

## Your task now: questions, not a decision

The court's neutral evidence review has found that some arguments are not supported by \
the facts, evidence, and witnesses they cite. Before the case continues, put questions \
to the party that made each such argument, so it can substantiate the claim from the \
record - or narrow or withdraw it.

- Cover every argument the review flagged; you may also ask about other arguments.
- Address each question to the party that made the arguments it is about.
- Ask specific, neutral questions about the record: what supports the claim, how a \
contradicting item is answered, what is assumed rather than shown.
- Do not signal how you will decide, and do not ask about anything outside the record.

Cite arguments only by the IDs in the record. At most 6 questions. Respond with a single \
JSON object matching the required schema."""


class Party(str, Enum):
    PROSECUTION = "prosecution"
    DEFENSE = "defense"

    @property
    def agent_id(self) -> str:
        return f"{self.value}_agent"


class QuestionDraft(BaseModel):
    """One question as the judge writes it"""

    addressed_to: Party
    argument_ids: List[str] = Field(..., description="Arguments the question is about")
    question: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, description="Why the court is asking")


class JudgeQuestionsOutput(BaseModel):
    questions: List[QuestionDraft]


class JudgeQuestionsError(AgentError):
    """The judge could not produce valid questions"""


class JudgeQuestionRound(BaseModel):
    """One accepted round of questions"""

    round: int
    flagged_argument_ids: List[str]
    questions: List[JudgeQuestion]
    message: CourtMessage
    attempts: List[AgentAttempt] = Field(default_factory=list)
    prompt_version: str = QUESTIONS_PROMPT_VERSION
    provider: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def rejected_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.accepted)


def validate_questions(
    output: JudgeQuestionsOutput,
    arguments: Sequence[Argument],
    flagged: Sequence[str],
) -> List[str]:
    """Questions must be about real arguments, put to the party that made them"""
    errors: List[str] = []
    owner = {a.argument_id: a.agent_id for a in arguments}

    if not output.questions:
        errors.append("Ask at least one question; arguments were flagged as unsupported.")
    if len(output.questions) > MAX_QUESTIONS_PER_ROUND:
        errors.append(
            f"{len(output.questions)} questions; ask at most {MAX_QUESTIONS_PER_ROUND}."
        )

    covered = set()
    for index, draft in enumerate(output.questions, start=1):
        where = f"question {index}"
        if not draft.argument_ids:
            errors.append(f"{where}: name the argument(s) the question is about.")
        for argument_id in draft.argument_ids:
            party = owner.get(argument_id)
            if party is None:
                errors.append(
                    f"{where}: '{argument_id}' is not an argument presented in this trial."
                )
            elif party != draft.addressed_to.agent_id:
                errors.append(
                    f"{where}: '{argument_id}' was made by {party}; address the question to "
                    "that party."
                )
            else:
                covered.add(argument_id)

    for argument_id in flagged:
        if argument_id not in covered:
            errors.append(
                f"The flagged argument {argument_id} is not covered by any question."
            )
    return errors


def build_questions_request(
    judge: "JudgeAgent",
    case: Case,
    evaluation: CaseEvaluation,
    arguments: Sequence[Argument],
    flagged: Sequence[str],
    evidence_context: Optional[Dict[str, Any]],
    earlier_questions: Sequence[JudgeQuestion],
) -> LLMRequest:
    record = render_case_record(
        case,
        evaluation,
        judge.registry,
        arguments,
        evidence_context,
        judge_questions=earlier_questions,
    )
    content = (
        "<case_record>\n"
        + json.dumps(record, indent=2)
        + "\n</case_record>\n\n"
        + "Stage: JUDGE_QUESTIONS. The evidence review found these arguments unsupported "
        f"by what they cite: {', '.join(flagged)}. Put your questions to the parties."
    )
    return LLMRequest(
        system=QUESTIONS_SYSTEM_PROMPT,
        messages=[LLMMessage(role=MessageRole.USER, content=content)],
        json_schema=strict_json_schema(JudgeQuestionsOutput),
        schema_name="judge_questions",
        max_tokens=judge.max_tokens,
    )


def ask_questions(
    judge: "JudgeAgent",
    case: Case,
    evaluation: CaseEvaluation,
    arguments: Sequence[Argument],
    flagged: Sequence[str],
    round_number: int = 1,
    evidence_context: Optional[Dict[str, Any]] = None,
    earlier_questions: Sequence[JudgeQuestion] = (),
) -> JudgeQuestionRound:
    """One validated round of questions about the flagged arguments"""
    if not flagged:
        raise ValueError("The judge asks questions only about flagged arguments")

    def parse(text: str) -> Tuple[Optional[JudgeQuestionsOutput], List[str]]:
        output, errors = parse_model_output(text, JudgeQuestionsOutput)
        if output is None:
            return None, errors
        return output, validate_questions(output, arguments, flagged)

    generation = generate_validated(
        provider=judge.provider,
        log=judge.log,
        agent_id=judge.agent_id,
        prompt_version=QUESTIONS_PROMPT_VERSION,
        case_id=case.case_id,
        request=build_questions_request(
            judge, case, evaluation, arguments, flagged, evidence_context, earlier_questions
        ),
        parse=parse,
        max_attempts=judge.max_attempts,
        error_cls=JudgeQuestionsError,
        task=f"questions for round {round_number}",
    )
    questions = [
        JudgeQuestion(
            question_id=f"JQ{round_number}-{index}",
            case_id=case.case_id,
            addressed_to=draft.addressed_to.agent_id,
            argument_ids=list(draft.argument_ids),
            question=draft.question,
            reason=draft.reason,
            round=round_number,
        )
        for index, draft in enumerate(generation.output.questions, start=1)
    ]
    message = CourtMessage(
        message_id=f"MSG-JUDGE-QUESTIONS{round_number}",
        case_id=case.case_id,
        sender=judge.agent_id,
        recipient="parties",
        message_type=MessageType.JUDGE_QUESTION,
        stage=CourtStage.JUDGE_QUESTIONS,
        claim=f"{len(questions)} question(s) to the parties",
        argument_ids=list(dict.fromkeys(a for q in questions for a in q.argument_ids)),
        reasoning=" ".join(
            f"[{q.question_id} -> {q.addressed_to}] {q.question}" for q in questions
        ),
    )
    return JudgeQuestionRound(
        round=round_number,
        flagged_argument_ids=list(flagged),
        questions=questions,
        message=message,
        attempts=generation.attempts,
        provider=generation.response.provider,
        model=generation.response.model,
        usage=generation.usage,
    )
