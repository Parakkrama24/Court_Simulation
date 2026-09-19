"""Tests for the stages Phase 8 completes: JUDGE_QUESTIONS and CROSS_EXAMINATION"""

import json

import pytest

from app.agents.advocate import (
    ANSWER_STAGE,
    STAGE_SPEAKERS,
    AdvocateAgent,
    AdvocateRole,
    AdvocateTurnOutput,
    AdvocateTurnValidator,
)
from app.agents.judge import (
    QUESTIONS_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    JudgeAgent,
    JudgeQuestionsError,
    JudgeQuestionsOutput,
    validate_questions,
)
from app.agents.record import render_case_record, render_question
from app.domain import Argument, CourtStage, JudgeQuestion, MessageType
from app.llm import InteractionLog, ScriptedProvider
from app.rules import LegalRuleRegistry

from .conftest import cross_turn, defense_turn, prosecution_turn, questions_output

PROSECUTION = AdvocateRole.PROSECUTION
DEFENSE = AdvocateRole.DEFENSE


def argument(argument_id: str, agent_id: str) -> Argument:
    return Argument(
        argument_id=argument_id,
        agent_id=agent_id,
        claim="A claim",
        evidence_ids=["E001"],
        reasoning="Reasoning",
    )


ARGUMENTS = [
    argument("PR-OPEN-1", "prosecution_agent"),
    argument("PR-OPEN-2", "prosecution_agent"),
    argument("DF-OPEN-1", "defense_agent"),
]


def question(question_id="JQ1-1", addressed_to="prosecution_agent", about=("PR-OPEN-2",)):
    return JudgeQuestion(
        question_id=question_id,
        case_id="CASE_001",
        addressed_to=addressed_to,
        argument_ids=list(about),
        question="What in the record shows this?",
        reason="Unsupported",
    )


# ============================================================================
# The judge's questions
# ============================================================================


class TestQuestionValidation:
    def _validate(self, data, flagged=("PR-OPEN-2",)):
        return validate_questions(JudgeQuestionsOutput.model_validate(data), ARGUMENTS, flagged)

    def test_valid_questions(self):
        assert self._validate(questions_output(("prosecution", ["PR-OPEN-2"]))) == []

    def test_extra_questions_are_allowed(self):
        data = questions_output(("prosecution", ["PR-OPEN-2"]), ("defense", ["DF-OPEN-1"]))
        assert self._validate(data) == []

    def test_unknown_argument(self):
        errors = self._validate(questions_output(("prosecution", ["PR-OPEN-2", "PR-OPEN-9"])))
        assert any("'PR-OPEN-9' is not an argument" in e for e in errors)

    def test_question_put_to_the_wrong_party(self):
        errors = self._validate(questions_output(("defense", ["PR-OPEN-2"])))
        assert any("made by prosecution_agent" in e for e in errors)

    def test_flagged_argument_must_be_covered(self):
        errors = self._validate(questions_output(("prosecution", ["PR-OPEN-1"])))
        assert any("PR-OPEN-2 is not covered" in e for e in errors)

    def test_limits(self):
        assert any("at least one" in e for e in self._validate({"questions": []}))
        many = questions_output(*[("prosecution", ["PR-OPEN-2"])] * 7)
        assert any("at most 6" in e for e in self._validate(many))
        empty = questions_output(("prosecution", []), ("prosecution", ["PR-OPEN-2"]))
        assert any("name the argument" in e for e in self._validate(empty))


class TestAskQuestions:
    def test_questions_get_court_ids_and_a_message(self, case, evaluation):
        data = questions_output(("prosecution", ["PR-OPEN-2"]), ("defense", ["DF-OPEN-1"]))
        log = InteractionLog()
        judge = JudgeAgent(ScriptedProvider([data]), log=log)
        result = judge.ask_questions(case, evaluation, ARGUMENTS, ["PR-OPEN-2"], round_number=2)

        assert [q.question_id for q in result.questions] == ["JQ2-1", "JQ2-2"]
        assert [q.addressed_to for q in result.questions] == ["prosecution_agent", "defense_agent"]
        assert all(q.round == 2 for q in result.questions)
        assert result.message.message_type == MessageType.JUDGE_QUESTION
        assert result.message.stage == CourtStage.JUDGE_QUESTIONS
        assert result.message.recipient == "parties"
        assert log.records[0].prompt_version == "judge-questions.v1"

    def test_questioning_has_its_own_prompt(self, case, evaluation):
        provider = ScriptedProvider([questions_output(("prosecution", ["PR-OPEN-2"]))])
        earlier = [question("JQ1-1")]
        JudgeAgent(provider).ask_questions(
            case, evaluation, ARGUMENTS, ["PR-OPEN-2"], round_number=2, earlier_questions=earlier
        )
        request = provider.requests[0]
        assert request.system == QUESTIONS_SYSTEM_PROMPT != SYSTEM_PROMPT
        assert "questions, not a decision" in request.system
        content = request.messages[0].content
        assert "found these arguments unsupported by what they cite: PR-OPEN-2" in content
        record = json.loads(content.split("<case_record>\n")[1].split("\n</case_record>")[0])
        assert record["judge_questions"][0]["question_id"] == "JQ1-1"

    def test_invalid_questions_are_regenerated(self, case, evaluation):
        bad = questions_output(("defense", ["PR-OPEN-2"]))
        good = questions_output(("prosecution", ["PR-OPEN-2"]))
        provider = ScriptedProvider([bad, good])
        result = JudgeAgent(provider).ask_questions(case, evaluation, ARGUMENTS, ["PR-OPEN-2"])
        assert [a.accepted for a in result.attempts] == [False, True]

    def test_gives_up(self, case, evaluation):
        judge = JudgeAgent(ScriptedProvider(["no"] * 3))
        with pytest.raises(JudgeQuestionsError, match="questions for round 1"):
            judge.ask_questions(case, evaluation, ARGUMENTS, ["PR-OPEN-2"])

    def test_only_about_flagged_arguments(self, case, evaluation):
        with pytest.raises(ValueError, match="flagged"):
            JudgeAgent(ScriptedProvider([])).ask_questions(case, evaluation, ARGUMENTS, [])


# ============================================================================
# The parties answer
# ============================================================================


class TestAnswers:
    def _validate(self, case, turn, role=PROSECUTION, questions=(question(),)):
        return AdvocateTurnValidator(
            case, role, ANSWER_STAGE, ARGUMENTS, questions=questions
        ).validate(AdvocateTurnOutput.model_validate(turn))

    def test_answer_by_question_id(self, case):
        assert self._validate(case, prosecution_turn(["JQ1-1"])).valid

    def test_unanswered_question(self, case):
        report = self._validate(case, prosecution_turn())
        assert any("question JQ1-1 is not answered" in e for e in report.errors)

    def test_cannot_answer_the_other_partys_question(self, case):
        questions = (question(), question("JQ1-2", "defense_agent", ("DF-OPEN-1",)))
        report = self._validate(case, prosecution_turn(["JQ1-1", "JQ1-2"]), questions=questions)
        assert any("'JQ1-2', which the judge put to the other party" in e for e in report.errors)

    def test_answer_turn(self, case, evaluation):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([prosecution_turn(["JQ1-1"])]))
        turn = agent.answer(
            case, evaluation, [question()], ARGUMENTS, id_prefix="PR-ANS1"
        )
        assert turn.stage == CourtStage.JUDGE_QUESTIONS
        assert [a.argument_id for a in turn.arguments] == ["PR-ANS1-1", "PR-ANS1-2"]
        assert turn.arguments[0].counter_argument_ids == ["JQ1-1"]
        assert turn.message.message_type == MessageType.ANSWER

    def test_answer_prompt(self, case, evaluation):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([]))
        request = agent.build_request(
            case, evaluation, ANSWER_STAGE, ARGUMENTS, questions=[question()]
        )
        content = request.messages[0].content
        assert "Questions the judge has put to you: JQ1-1." in content
        assert "narrow or withdraw the claim" in content
        assert '"judge_questions"' in content

    def test_a_party_with_no_questions_does_not_answer(self, case, evaluation):
        agent = AdvocateAgent(DEFENSE, ScriptedProvider([]))
        with pytest.raises(ValueError, match="only to answer questions"):
            agent.build_request(case, evaluation, ANSWER_STAGE, ARGUMENTS, questions=[question()])

    def test_rendered_question(self):
        rendered = render_question(question())
        assert rendered == {
            "question_id": "JQ1-1",
            "round": 1,
            "addressed_to": "prosecution_agent",
            "about_arguments": ["PR-OPEN-2"],
            "question": "What in the record shows this?",
            "reason": "Unsupported",
        }

    def test_record_carries_questions_only_when_asked(self, case, evaluation):
        registry = LegalRuleRegistry()
        assert "judge_questions" not in render_case_record(case, evaluation, registry)
        record = render_case_record(case, evaluation, registry, judge_questions=[question()])
        assert record["judge_questions"][0]["question_id"] == "JQ1-1"


# ============================================================================
# Cross-examination
# ============================================================================


class TestCrossExamination:
    def test_both_parties_cross_examine(self):
        assert STAGE_SPEAKERS[CourtStage.CROSS_EXAMINATION] == [PROSECUTION, DEFENSE]

    def test_every_argument_must_test_a_witness(self, case):
        validator = AdvocateTurnValidator(case, PROSECUTION, CourtStage.CROSS_EXAMINATION)
        report = validator.validate(AdvocateTurnOutput.model_validate(prosecution_turn()))
        assert any("argument 1: this is cross-examination" in e for e in report.errors)

    def test_cross_examination_turn(self, case, evaluation):
        agent = AdvocateAgent(DEFENSE, ScriptedProvider([cross_turn(defense_turn(), "W001")]))
        turn = agent.argue(case, evaluation, CourtStage.CROSS_EXAMINATION)
        assert [a.argument_id for a in turn.arguments] == ["DF-CROSS-1", "DF-CROSS-2"]
        assert turn.message.message_type == MessageType.CROSS_EXAMINATION
        prompt = agent.build_request(case, evaluation, CourtStage.CROSS_EXAMINATION)
        assert "Cross-examination. Test the testimony" in prompt.messages[0].content
