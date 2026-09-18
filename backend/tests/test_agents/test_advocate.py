"""Tests for the Prosecution and Defense agents"""

import copy

import pytest

from app.agents.advocate import (
    MAX_ARGUMENTS_PER_TURN,
    AdvocateAgent,
    AdvocateAgentError,
    AdvocateRole,
    AdvocateTurnOutput,
    AdvocateTurnValidator,
)
from app.domain import Argument, CourtStage, MessageType
from app.llm import InteractionLog, MessageRole, ScriptedProvider

PROSECUTION = AdvocateRole.PROSECUTION
DEFENSE = AdvocateRole.DEFENSE


def presented(argument_id: str, role: AdvocateRole) -> Argument:
    return Argument(
        argument_id=argument_id,
        agent_id=role.agent_id,
        claim="An earlier argument",
        evidence_ids=["E001"],
        reasoning="Earlier",
    )


def validate(case, role, stage, turn, prior=()):
    output = AdvocateTurnOutput.model_validate(turn)
    return AdvocateTurnValidator(case, role, stage, prior).validate(output)


# ============================================================================
# Roles
# ============================================================================


class TestRoles:
    def test_agent_ids_and_codes(self):
        assert PROSECUTION.agent_id == "prosecution_agent"
        assert DEFENSE.agent_id == "defense_agent"
        assert PROSECUTION.code == "PR"
        assert DEFENSE.code == "DF"

    def test_opponents(self):
        assert PROSECUTION.opponent is DEFENSE
        assert DEFENSE.opponent is PROSECUTION


# ============================================================================
# Validation
# ============================================================================


class TestAdvocateValidation:
    def test_valid_prosecution_opening(self, case, pro_turn):
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, pro_turn())
        assert report.valid, report.errors
        assert report.flags == []  # F004 is disputed, but an assumption is listed

    def test_valid_defense_reply(self, case, def_turn):
        prior = [presented("PR-OPEN-1", PROSECUTION)]
        report = validate(
            case, DEFENSE, CourtStage.DEFENSE_OPENING, def_turn(["PR-OPEN-1"]), prior
        )
        assert report.valid, report.errors

    @pytest.mark.parametrize(
        "field,value,fragment",
        [
            ("evidence_ids", ["E999"], "E999"),
            ("fact_ids", ["F099"], "F099"),
            ("witness_ids", ["W009"], "W009"),
            ("law_ids", ["LAW_999"], "LAW_999"),
        ],
    )
    def test_fabricated_references_are_rejected(self, case, pro_turn, field, value, fragment):
        turn = pro_turn()
        turn["arguments"][0][field] = turn["arguments"][0][field] + value
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert not report.valid
        assert any(fragment in e for e in report.errors)

    def test_unknown_element_is_rejected(self, case, pro_turn):
        turn = pro_turn()
        turn["arguments"][0]["elements"] = [{"rule_id": "LAW_104", "condition_id": "C9"}]
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert any("no condition 'C9'" in e for e in report.errors)

    def test_element_rule_is_reference_checked(self, case, pro_turn):
        turn = pro_turn()
        turn["arguments"][0]["elements"] = [{"rule_id": "LAW_404", "condition_id": "C1"}]
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert any("LAW_404" in e for e in report.errors)

    def test_invented_charge_is_rejected(self, case, pro_turn):
        turn = pro_turn()
        turn["arguments"][0]["charges"] = ["arson"]
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert any("'arson' is not a charge" in e for e in report.errors)

    def test_missing_charge_is_rejected(self, case, pro_turn):
        turn = pro_turn()
        turn["arguments"][0]["charges"] = []
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert any("name the charge" in e for e in report.errors)

    def test_ungrounded_argument_is_rejected(self, case, pro_turn):
        turn = pro_turn()
        for field in ("fact_ids", "evidence_ids", "witness_ids"):
            turn["arguments"][0][field] = []
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert any("P003" in e for e in report.errors)

    def test_empty_turn_is_rejected(self, case, pro_turn):
        turn = pro_turn()
        turn["arguments"] = []
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert any("no arguments" in e for e in report.errors)

    def test_too_many_arguments_are_rejected(self, case, pro_turn):
        turn = pro_turn()
        turn["arguments"] = [copy.deepcopy(turn["arguments"][0])] * (MAX_ARGUMENTS_PER_TURN + 1)
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert any(f"at most {MAX_ARGUMENTS_PER_TURN}" in e for e in report.errors)

    def test_responding_to_unpresented_argument(self, case, def_turn):
        report = validate(case, DEFENSE, CourtStage.DEFENSE_OPENING, def_turn(["PR-OPEN-7"]))
        assert any("has not been presented" in e for e in report.errors)

    def test_responding_to_own_side(self, case, def_turn):
        prior = [presented("DF-OPEN-1", DEFENSE)]
        report = validate(
            case, DEFENSE, CourtStage.DEFENSE_ARGUMENT, def_turn(["DF-OPEN-1"]), prior
        )
        assert any("your own side's" in e for e in report.errors)

    def test_rebuttal_must_answer_something(self, case, pro_turn):
        prior = [presented("DF-OPEN-1", DEFENSE)]
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_REBUTTAL, pro_turn(), prior)
        assert any("this is a rebuttal" in e for e in report.errors)

    def test_rebuttal_answering_opponent_passes(self, case, pro_turn):
        prior = [presented("DF-OPEN-1", DEFENSE)]
        report = validate(
            case, PROSECUTION, CourtStage.PROSECUTION_REBUTTAL, pro_turn(["DF-OPEN-1"]), prior
        )
        assert report.valid, report.errors

    def test_disputed_fact_without_assumption_is_flagged(self, case, pro_turn):
        turn = pro_turn()
        turn["arguments"][1]["assumptions"] = []
        report = validate(case, PROSECUTION, CourtStage.PROSECUTION_OPENING, turn)
        assert report.valid  # recorded, not rejected
        assert report.flags[0].kind == "disputed_fact_without_assumption"
        assert report.flags[0].argument_index == 2
        assert "F004" in report.flags[0].detail


# ============================================================================
# Agent
# ============================================================================


class TestAdvocateRequest:
    def test_system_prompts_differ_by_role(self, case, evaluation):
        pro = AdvocateAgent(PROSECUTION, ScriptedProvider([]))
        dfn = AdvocateAgent(DEFENSE, ScriptedProvider([]))
        pro_system = pro.build_request(case, evaluation, CourtStage.PROSECUTION_OPENING).system
        def_system = dfn.build_request(case, evaluation, CourtStage.DEFENSE_OPENING).system
        assert "You are the prosecutor" in pro_system
        assert "You are defense counsel" in def_system
        for system in (pro_system, def_system):
            assert "does not provide legal advice" in system
            assert "assumptions" in system
            assert "may not invent facts" in system

    def test_user_prompt_lists_the_debate_so_far(self, case, evaluation):
        agent = AdvocateAgent(DEFENSE, ScriptedProvider([]))
        prior = [presented("PR-OPEN-1", PROSECUTION)]
        prompt = agent.build_request(
            case, evaluation, CourtStage.DEFENSE_OPENING, prior
        ).messages[0].content
        assert '"argument_id": "PR-OPEN-1"' in prompt
        assert "Opposing arguments you may answer: PR-OPEN-1." in prompt
        assert "Stage: DEFENSE_OPENING" in prompt

    def test_first_speaker_is_told_there_is_nothing_to_answer(self, case, evaluation):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([]))
        prompt = agent.build_request(
            case, evaluation, CourtStage.PROSECUTION_OPENING
        ).messages[0].content
        assert "responds_to must be empty" in prompt

    def test_role_cannot_speak_at_the_other_sides_stage(self, case, evaluation):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([]))
        with pytest.raises(ValueError, match="does not speak"):
            agent.build_request(case, evaluation, CourtStage.DEFENSE_OPENING)

    def test_both_sides_speak_at_closing(self, case, evaluation):
        for role in (PROSECUTION, DEFENSE):
            AdvocateAgent(role, ScriptedProvider([])).build_request(
                case, evaluation, CourtStage.CLOSING_ARGUMENTS
            )

    def test_max_attempts_must_be_positive(self):
        with pytest.raises(ValueError):
            AdvocateAgent(PROSECUTION, ScriptedProvider([]), max_attempts=0)


class TestAdvocateTurn:
    def test_arguments_get_court_assigned_ids(self, case, evaluation, pro_turn):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([pro_turn()]))
        turn = agent.argue(case, evaluation, CourtStage.PROSECUTION_OPENING)
        assert [a.argument_id for a in turn.arguments] == ["PR-OPEN-1", "PR-OPEN-2"]
        assert all(a.agent_id == "prosecution_agent" for a in turn.arguments)

    def test_argument_mapping(self, case, evaluation, pro_turn):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([pro_turn()]))
        second = agent.argue(case, evaluation, CourtStage.PROSECUTION_OPENING).arguments[1]
        assert second.fact_ids == ["F004"]
        assert second.witness_ids == ["W001"]
        assert second.law_ids == ["LAW_101"]  # element rules are folded into law_ids
        assert second.metadata["stage"] == "PROSECUTION_OPENING"
        assert second.metadata["charges"] == ["assault"]
        assert second.metadata["assumptions"] == [
            "David's account of the confrontation is accurate."
        ]
        assert second.metadata["elements"][0] == {"rule_id": "LAW_101", "condition_id": "C1"}

    def test_turn_is_one_structured_message(self, case, evaluation, pro_turn):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([pro_turn()]))
        message = agent.argue(case, evaluation, CourtStage.PROSECUTION_OPENING).message
        assert message.message_id == "MSG-PR-OPEN"
        assert message.sender == "prosecution_agent"
        assert message.recipient == "judge_agent"
        assert message.message_type == MessageType.OPENING_STATEMENT
        assert message.stage == CourtStage.PROSECUTION_OPENING
        assert message.argument_ids == ["PR-OPEN-1", "PR-OPEN-2"]
        assert message.evidence_ids == ["E001", "E002", "E006"]
        assert message.law_ids == ["LAW_104", "LAW_101"]

    def test_custom_id_prefix(self, case, evaluation, pro_turn):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([pro_turn()]))
        turn = agent.argue(case, evaluation, CourtStage.PROSECUTION_OPENING, id_prefix="PR-X")
        assert turn.arguments[0].argument_id == "PR-X-1"
        assert turn.message.message_id == "MSG-PR-X"

    def test_fabricated_turn_is_regenerated_and_logged(self, case, evaluation, pro_turn):
        bad = pro_turn()
        bad["arguments"][0]["evidence_ids"] = ["E042"]
        provider = ScriptedProvider([bad, pro_turn()])
        log = InteractionLog()
        agent = AdvocateAgent(PROSECUTION, provider, log=log)
        turn = agent.argue(case, evaluation, CourtStage.PROSECUTION_OPENING)

        assert [a.accepted for a in turn.attempts] == [False, True]
        assert turn.rejected_attempts == 1
        assert [r.agent_id for r in log.records] == ["prosecution_agent"] * 2
        assert [r.validation_passed for r in log.records] == [False, True]
        retry = provider.requests[1].messages
        assert retry[1].role == MessageRole.ASSISTANT
        assert "E042" in retry[2].content

    def test_gives_up_after_max_attempts(self, case, evaluation):
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider(["no"] * 2), max_attempts=2)
        with pytest.raises(AdvocateAgentError) as caught:
            agent.argue(case, evaluation, CourtStage.PROSECUTION_OPENING)
        assert len(caught.value.attempts) == 2
        assert "prosecution turn at PROSECUTION_OPENING" in str(caught.value)

    def test_flags_are_carried_on_the_turn(self, case, evaluation, pro_turn):
        turn_data = pro_turn()
        turn_data["arguments"][1]["assumptions"] = []
        agent = AdvocateAgent(PROSECUTION, ScriptedProvider([turn_data]))
        turn = agent.argue(case, evaluation, CourtStage.PROSECUTION_OPENING)
        assert turn.flags[0].kind == "disputed_fact_without_assumption"
