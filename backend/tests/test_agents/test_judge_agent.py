"""Tests for the Judge Agent's generate -> validate -> regenerate loop"""

import json

import pytest

from app.agents.judge import (
    DISCLAIMER,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    JudgeAgent,
    JudgeAgentError,
)
from app.llm import InteractionLog, LLMRefusalError, MessageRole, ScriptedProvider


def run(case, evaluation, steps, **kwargs):
    provider = ScriptedProvider(steps)
    log = InteractionLog()
    agent = JudgeAgent(provider, log=log, **kwargs)
    return agent, provider, log


class TestRequest:
    def test_request_carries_system_prompt_and_schema(self, case, evaluation):
        agent, _, _ = run(case, evaluation, [])
        request = agent.build_request(case, evaluation)
        assert request.system == SYSTEM_PROMPT
        assert request.json_schema == agent.output_schema
        assert request.schema_name == "judge_decision"
        assert len(request.messages) == 1

    def test_prompt_contains_the_whole_record(self, case, evaluation):
        agent, _, _ = run(case, evaluation, [])
        prompt = agent.build_request(case, evaluation).messages[0].content
        for item_id in [f.fact_id for f in case.facts] + [e.evidence_id for e in case.evidence]:
            assert f'"{item_id}"' in prompt
        for witness in case.witnesses:
            assert witness.witness_id in prompt
        for rule_id in case.applicable_laws + ["P001", "P004", "E003"]:
            assert f'"rule_id": "{rule_id}"' in prompt
        assert "rule_engine_evaluation" in prompt
        assert "burglary, assault" in prompt

    def test_prompt_is_deterministic(self, case, evaluation):
        agent, _, _ = run(case, evaluation, [])
        first = agent.build_request(case, evaluation)
        second = agent.build_request(case, evaluation)
        assert first.model_dump() == second.model_dump()

    def test_system_prompt_states_the_disclaimer_and_principles(self):
        assert "does not provide legal advice" in SYSTEM_PROMPT
        for principle in ["P001", "P002", "P003", "P004", "P005"]:
            assert principle in SYSTEM_PROMPT

    def test_max_attempts_must_be_positive(self):
        with pytest.raises(ValueError):
            JudgeAgent(ScriptedProvider([]), max_attempts=0)


class TestAcceptedDecision:
    def test_valid_first_attempt(self, case, evaluation, valid_decision):
        agent, provider, log = run(case, evaluation, [valid_decision])
        result = agent.decide(case, evaluation)

        assert len(result.attempts) == 1
        assert result.rejected_attempts == 0
        assert result.attempts[0].accepted
        assert provider.remaining == 0
        assert len(log.records) == 1
        assert log.records[0].validation_passed is True
        assert log.records[0].prompt_version == PROMPT_VERSION
        assert log.records[0].case_id == "CASE_001"

    def test_verdict_mapping(self, case, evaluation, valid_decision):
        agent, _, _ = run(case, evaluation, [valid_decision])
        verdict = agent.decide(case, evaluation).verdict

        assert verdict.case_id == "CASE_001"
        assert verdict.agent_id == "judge_agent"
        assert verdict.charges == ["burglary", "assault"]
        assert verdict.decision == "burglary: not_guilty; assault: not_guilty"
        assert verdict.confidence == 0.8
        assert set(verdict.evidence_used) <= {e.evidence_id for e in case.evidence}
        assert "E007" in verdict.evidence_used
        assert verdict.laws_used[:2] == ["LAW_104", "LAW_101"]
        assert verdict.unresolved_questions == ["What did Alex intend when he entered the house?"]
        assert verdict.metadata["disclaimer"] == DISCLAIMER
        assert verdict.metadata["prompt_version"] == PROMPT_VERSION
        assert len(verdict.metadata["charge_decisions"]) == 2

    def test_usage_is_accumulated_across_attempts(self, case, evaluation, valid_decision):
        agent, _, _ = run(case, evaluation, ["not json", valid_decision])
        result = agent.decide(case, evaluation)
        assert result.usage.output_tokens > 0
        assert result.usage.input_tokens > 0


class TestRegeneration:
    def test_fabricated_reference_is_rejected_then_corrected(
        self, case, evaluation, valid_decision, decision_with
    ):
        fabricated = decision_with(
            lambda d: d["established_facts"][0]["evidence_ids"].append("E999")
        )
        agent, provider, log = run(case, evaluation, [fabricated, valid_decision])
        result = agent.decide(case, evaluation)

        assert [a.accepted for a in result.attempts] == [False, True]
        assert "E999" in result.attempts[0].errors[0]
        assert [r.validation_passed for r in log.records] == [False, True]
        assert "E999" in log.records[0].validation_errors[0]

        retry = provider.requests[1]
        assert [m.role for m in retry.messages] == [
            MessageRole.USER,
            MessageRole.ASSISTANT,
            MessageRole.USER,
        ]
        assert json.loads(retry.messages[1].content) == fabricated
        assert "E999" in retry.messages[2].content
        assert "rejected" in retry.messages[2].content

    def test_invalid_json_is_rejected(self, case, evaluation, valid_decision):
        agent, _, _ = run(case, evaluation, ["{not json", valid_decision])
        result = agent.decide(case, evaluation)
        assert "not valid JSON" in result.attempts[0].errors[0]

    def test_schema_mismatch_is_rejected(self, case, evaluation, valid_decision, decision_with):
        incomplete = decision_with(lambda d: d.pop("analysis"))
        agent, _, _ = run(case, evaluation, [incomplete, valid_decision])
        result = agent.decide(case, evaluation)
        assert "does not match the required schema" in result.attempts[0].errors[0]
        assert "analysis" in result.attempts[0].errors[0]

    def test_out_of_range_confidence_is_rejected(
        self, case, evaluation, valid_decision, decision_with
    ):
        def mutate(d):
            d["overall_confidence"] = 1.7

        agent, _, _ = run(case, evaluation, [decision_with(mutate), valid_decision])
        result = agent.decide(case, evaluation)
        assert "overall_confidence" in result.attempts[0].errors[0]

    def test_gives_up_after_max_attempts(self, case, evaluation, decision_with):
        bad = decision_with(lambda d: d["charge_decisions"].pop())
        agent, provider, log = run(case, evaluation, [bad, bad, bad, bad], max_attempts=3)

        with pytest.raises(JudgeAgentError) as caught:
            agent.decide(case, evaluation)

        assert len(caught.value.attempts) == 3
        assert provider.remaining == 1
        assert [r.validation_passed for r in log.records] == [False, False, False]
        assert "not decided" in str(caught.value)

    def test_conversation_grows_with_each_rejection(self, case, evaluation, valid_decision):
        agent, provider, _ = run(case, evaluation, ["bad", "worse", valid_decision])
        agent.decide(case, evaluation)
        assert [len(r.messages) for r in provider.requests] == [1, 3, 5]


class TestProviderFailures:
    def test_refusal_fails_loudly_and_is_logged(self, case, evaluation):
        agent, _, log = run(case, evaluation, [LLMRefusalError("declined")])
        with pytest.raises(JudgeAgentError, match="declined"):
            agent.decide(case, evaluation)
        assert log.records[0].error.startswith("LLMRefusalError")
        assert log.records[0].validation_passed is None


class TestDivergences:
    def test_divergences_are_attached_to_the_result(self, case, evaluation, decision_with):
        def convict(d):
            burglary = d["charge_decisions"][0]
            burglary["decision"] = "guilty"
            burglary["elements"][1]["assessment"] = "established"

        agent, _, _ = run(case, evaluation, [decision_with(convict)])
        result = agent.decide(case, evaluation)
        assert result.divergences
        assert result.verdict.metadata["engine_divergences"]
        assert result.verdict.decision.startswith("burglary: guilty")

    def test_strict_alignment_forces_regeneration(
        self, case, evaluation, valid_decision, decision_with
    ):
        def convict(d):
            burglary = d["charge_decisions"][0]
            burglary["decision"] = "guilty"
            burglary["elements"][1]["assessment"] = "established"

        agent, _, _ = run(
            case, evaluation, [decision_with(convict), valid_decision], strict_engine_alignment=True
        )
        result = agent.decide(case, evaluation)
        assert [a.accepted for a in result.attempts] == [False, True]
