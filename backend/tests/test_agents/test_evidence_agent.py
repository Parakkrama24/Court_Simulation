"""Tests for the Evidence Agent: provenance, validation, analysis, and review"""

import json

import pytest

from app.agents.evidence import (
    MAX_CLAIMS,
    EvidenceAgent,
    EvidenceAgentError,
    EvidenceAnalysisOutput,
    EvidenceAnalysisValidator,
    EvidenceReviewOutput,
    EvidenceReviewValidator,
    ReliabilityRating,
    SYSTEM_PROMPT,
    evidence_context,
    reliability_band,
    trace_case_provenance,
    trace_provenance,
)
from app.domain import Argument, CourtStage, Evidence, EvidenceType, MessageType
from app.llm import InteractionLog, ScriptedProvider

from .conftest import review_for


def argument(argument_id: str, agent_id: str) -> Argument:
    return Argument(
        argument_id=argument_id,
        agent_id=agent_id,
        claim=f"Claim {argument_id}",
        evidence_ids=["E001"],
        reasoning="Reasoning",
    )


ARGUMENTS = [
    argument("PR-OPEN-1", "prosecution_agent"),
    argument("PR-OPEN-2", "prosecution_agent"),
    argument("DF-OPEN-1", "defense_agent"),
]
ARGUMENT_IDS = [a.argument_id for a in ARGUMENTS]


def validate_analysis(case, evaluation, data):
    output = EvidenceAnalysisOutput.model_validate(data)
    return EvidenceAnalysisValidator(case, evaluation).validate(output)


def validate_review(data, arguments=ARGUMENTS):
    output = EvidenceReviewOutput.model_validate(data)
    return EvidenceReviewValidator(arguments).validate(output)


# ============================================================================
# Provenance (deterministic)
# ============================================================================


class TestProvenance:
    def test_every_evidence_item_is_traced(self, case):
        records = trace_case_provenance(case)
        assert [r.evidence_id for r in records] == [e.evidence_id for e in case.evidence]

    def test_handler_date_and_facts(self, case):
        e001 = trace_case_provenance(case)[0]
        assert e001.handled_by == "Officer Martinez"
        assert e001.date == "2024-01-16"
        assert e001.supports_facts == ["F001", "F002"]
        assert e001.gaps == []

    def test_testimonial_evidence_is_linked_to_its_witness(self, case):
        e006 = next(r for r in trace_case_provenance(case) if r.evidence_id == "E006")
        assert e006.witness_id == "W002"
        assert e006.gaps == ["no collection date recorded"]

    def test_missing_handler_is_a_gap(self, case):
        e005 = next(r for r in trace_case_provenance(case) if r.evidence_id == "E005")
        assert e005.handled_by is None
        assert "no record of who collected or produced it" in e005.gaps

    def test_unlinked_evidence_is_a_gap(self, case):
        orphan = Evidence(
            evidence_id="E099",
            type=EvidenceType.DOCUMENTARY,
            description="Unlinked note",
            source="unknown",
        )
        record = trace_provenance(orphan, case)
        assert "not linked to any fact in the record" in record.gaps
        assert len(record.gaps) == 3


# ============================================================================
# Analysis validation
# ============================================================================


class TestAnalysisValidation:
    def test_valid_analysis_passes_cleanly(self, case, evaluation, valid_analysis):
        report = validate_analysis(case, evaluation, valid_analysis)
        assert report.valid, report.errors
        assert report.flags == []

    @pytest.mark.parametrize(
        "path,value,fragment",
        [
            (("claims", 0, "supporting_evidence_ids"), ["E001", "E404"], "E404"),
            (("claims", 1, "supporting_witness_ids"), ["W009"], "W009"),
            (("claims", 0, "fact_ids"), ["F099"], "F099"),
            (("contradictions", 0, "evidence_ids"), ["E007", "E777"], "E777"),
        ],
    )
    def test_fabricated_references(self, case, evaluation, valid_analysis, path, value, fragment):
        target = valid_analysis
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any(fragment in e for e in report.errors)

    def test_unknown_element_in_missing_evidence(self, case, evaluation, valid_analysis):
        valid_analysis["missing_evidence"][0]["elements"] = [
            {"rule_id": "LAW_104", "condition_id": "C5"}
        ]
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("no condition 'C5'" in e for e in report.errors)

    def test_established_claim_cannot_be_contradicted(self, case, evaluation, valid_analysis):
        valid_analysis["claims"][1]["status"] = "established"
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("'established' requires" in e for e in report.errors)

    def test_established_claim_needs_support(self, case, evaluation, valid_analysis):
        valid_analysis["claims"][2]["status"] = "established"
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("'established' requires" in e for e in report.errors)

    def test_disputed_claim_needs_both_sides(self, case, evaluation, valid_analysis):
        valid_analysis["claims"][0]["status"] = "disputed"
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("'disputed' requires" in e for e in report.errors)

    def test_unsupported_claim_cannot_list_support(self, case, evaluation, valid_analysis):
        valid_analysis["claims"][0]["status"] = "unsupported"
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("'unsupported' cannot" in e for e in report.errors)

    def test_item_cannot_both_support_and_contradict(self, case, evaluation, valid_analysis):
        valid_analysis["claims"][1]["contradicting_evidence_ids"] = ["E007", "E006"]
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("E006 cannot both support and contradict" in e for e in report.errors)

    def test_every_evidence_item_must_be_assessed(self, case, evaluation, valid_analysis):
        valid_analysis["evidence"].pop()
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("evidence E008 is not assessed" in e for e in report.errors)

    def test_evidence_assessed_twice(self, case, evaluation, valid_analysis):
        valid_analysis["evidence"].append(dict(valid_analysis["evidence"][0]))
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("evidence E001 is assessed 2 times" in e for e in report.errors)

    def test_every_witness_must_be_assessed(self, case, evaluation, valid_analysis):
        valid_analysis["witnesses"].pop(0)
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("witness W001 is not assessed" in e for e in report.errors)

    def test_disputed_fact_must_be_covered(self, case, evaluation, valid_analysis):
        valid_analysis["claims"].pop(1)
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("Disputed fact F004" in e and "P005" in e for e in report.errors)

    def test_contradiction_needs_two_items(self, case, evaluation, valid_analysis):
        valid_analysis["contradictions"][0].update(
            evidence_ids=["E007"], witness_ids=[], fact_ids=[]
        )
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any("at least two items" in e for e in report.errors)

    def test_claim_limits(self, case, evaluation, valid_analysis):
        valid_analysis["claims"] = []
        errors = validate_analysis(case, evaluation, valid_analysis).errors
        assert any("No claims" in e for e in errors)
        valid_analysis["claims"] = [VALID_CLAIM] * (MAX_CLAIMS + 1)
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any(f"the {MAX_CLAIMS} most important" in e for e in report.errors)


VALID_CLAIM = {
    "claim": "Alex physically attacked David.",
    "fact_ids": ["F004"],
    "supporting_evidence_ids": ["E006"],
    "supporting_witness_ids": [],
    "contradicting_evidence_ids": ["E007"],
    "contradicting_witness_ids": [],
    "status": "disputed",
    "confidence": 0.5,
    "reasoning": "Both sides cited.",
}


class TestAnalysisFlags:
    def test_outcome_language_is_flagged_not_rejected(self, case, evaluation, valid_analysis):
        valid_analysis["summary"] = "Alex should be acquitted of assault."
        report = validate_analysis(case, evaluation, valid_analysis)
        assert report.valid
        assert report.flags[0].kind == "neutrality"
        assert "acquitted" in report.flags[0].detail

    def test_witness_rating_outside_engine_band(self, case, evaluation, valid_analysis):
        valid_analysis["witnesses"][2]["rating"] = "high"  # W003 scores 0.15
        report = validate_analysis(case, evaluation, valid_analysis)
        assert report.valid
        assert report.flags[0].kind == "witness_rating_divergence"
        assert "W003" in report.flags[0].detail

    def test_circumstantial_evidence_called_direct(self, case, evaluation, valid_analysis):
        case.evidence[1].type = EvidenceType.CIRCUMSTANTIAL
        valid_analysis["evidence"][1]["directness"] = "direct"
        report = validate_analysis(case, evaluation, valid_analysis)
        assert report.flags[0].kind == "directness_divergence"

    def test_engine_fact_conflict_not_named(self, case, evaluation, valid_analysis):
        evaluation.conflicting_evidence.append(
            {"type": "fact_conflict", "rule_id": "E004", "fact_id": "F003"}
        )
        report = validate_analysis(case, evaluation, valid_analysis)
        assert any(f.kind == "engine_conflict_not_named" for f in report.flags)

    def test_reliability_bands(self):
        assert reliability_band(0.95) == ReliabilityRating.HIGH
        assert reliability_band(0.65) == ReliabilityRating.MODERATE
        assert reliability_band(0.15) == ReliabilityRating.LOW


# ============================================================================
# Review validation
# ============================================================================


class TestReviewValidation:
    def test_complete_review_passes(self):
        assert validate_review(review_for(ARGUMENT_IDS)).valid

    def test_every_argument_must_be_reviewed(self):
        report = validate_review(review_for(ARGUMENT_IDS[:2]))
        assert any("argument DF-OPEN-1 is not assessed" in e for e in report.errors)

    def test_unknown_argument(self):
        report = validate_review(review_for(ARGUMENT_IDS + ["PR-GHOST-1"]))
        assert any("'PR-GHOST-1' is not under review" in e for e in report.errors)

    def test_argument_reviewed_twice(self):
        report = validate_review(review_for(ARGUMENT_IDS + ["PR-OPEN-1"]))
        assert any("PR-OPEN-1 is assessed 2 times" in e for e in report.errors)

    def test_weak_finding_needs_issues(self):
        report = validate_review(review_for(ARGUMENT_IDS, support="unsupported"))
        assert any("lists no issues" in e for e in report.errors)

    def test_weak_finding_with_issues_passes(self):
        data = review_for(ARGUMENT_IDS, support="partially_supported", issues=["overclaims"])
        assert validate_review(data).valid

    def test_outcome_language_is_flagged(self):
        data = review_for(ARGUMENT_IDS)
        data["summary"] = "The prosecution has shown the defendant is guilty."
        report = validate_review(data)
        assert report.valid
        assert report.flags[0].kind == "neutrality"


# ============================================================================
# Agent
# ============================================================================


class TestEvidenceAgent:
    def test_system_prompt_is_neutral(self):
        assert "You are neutral" in SYSTEM_PROMPT
        assert "never argue for the prosecution or the defense" in SYSTEM_PROMPT
        assert "does not provide legal advice" in SYSTEM_PROMPT

    def test_analysis_prompt_includes_provenance_and_disputed_facts(self, case, evaluation):
        request = EvidenceAgent(ScriptedProvider([])).build_analysis_request(case, evaluation)
        prompt = request.messages[0].content
        assert '"evidence_provenance"' in prompt
        assert "every disputed fact (F004)" in prompt
        assert request.schema_name == "evidence_analysis"

    def test_analyze(self, case, evaluation, valid_analysis):
        log = InteractionLog()
        analysis = EvidenceAgent(ScriptedProvider([valid_analysis]), log=log).analyze(
            case, evaluation
        )
        assert len(analysis.output.claims) == 4
        assert len(analysis.provenance) == 8
        assert analysis.claims_with_status("unsupported") == [
            "Alex intended to commit an offense inside the house."
        ]
        assert log.records[0].agent_id == "evidence_agent"

    def test_analysis_message(self, case, evaluation, valid_analysis):
        message = EvidenceAgent(ScriptedProvider([valid_analysis])).analyze(
            case, evaluation
        ).message
        assert message.sender == "evidence_agent"
        assert message.recipient == "court"
        assert message.message_type == MessageType.EVIDENCE_ANALYSIS
        assert message.stage == CourtStage.EVIDENCE_ANALYSIS
        assert "2 established, 1 disputed, 1 unsupported" in message.reasoning

    def test_inconsistent_analysis_is_regenerated(self, case, evaluation, valid_analysis):
        bad = json.loads(json.dumps(valid_analysis))
        bad["claims"][1]["status"] = "established"
        provider = ScriptedProvider([bad, valid_analysis])
        analysis = EvidenceAgent(provider).analyze(case, evaluation)
        assert [a.accepted for a in analysis.attempts] == [False, True]
        assert "'established' requires" in provider.requests[1].messages[2].content

    def test_analysis_gives_up(self, case, evaluation):
        agent = EvidenceAgent(ScriptedProvider(["nope"] * 2), max_attempts=2)
        with pytest.raises(EvidenceAgentError, match="evidence analysis"):
            agent.analyze(case, evaluation)

    def test_review(self, case, evaluation):
        data = review_for(["PR-OPEN-1", "PR-OPEN-2"])
        data["reviews"][1].update(support="unsupported", issues=["F004 presented as settled"])
        review = EvidenceAgent(ScriptedProvider([data])).review(
            case, evaluation, ARGUMENTS, ARGUMENTS[:2], message_id="MSG-EVIDENCE-REVIEW2"
        )
        assert review.unsupported_argument_ids == ["PR-OPEN-2"]
        assert review.message.message_id == "MSG-EVIDENCE-REVIEW2"
        assert review.message.message_type == MessageType.EVIDENCE_REVIEW
        assert review.message.argument_ids == ["PR-OPEN-1", "PR-OPEN-2"]

    def test_review_prompt_lists_the_arguments_under_review(self, case, evaluation):
        request = EvidenceAgent(ScriptedProvider([])).build_review_request(
            case, evaluation, ARGUMENTS, ARGUMENTS[2:]
        )
        prompt = request.messages[0].content
        assert "exactly once: DF-OPEN-1." in prompt
        assert '"argument_id": "PR-OPEN-1"' in prompt  # context includes all arguments
        assert "Review both parties by the same standard" in prompt

    def test_review_needs_arguments(self, case, evaluation):
        with pytest.raises(ValueError, match="no arguments"):
            EvidenceAgent(ScriptedProvider([])).review(case, evaluation, [])


class TestEvidenceContext:
    def test_nothing_to_share(self):
        assert evidence_context(None) is None

    def test_analysis_and_reviews(self, case, evaluation, valid_analysis):
        agent = EvidenceAgent(ScriptedProvider([valid_analysis, review_for(ARGUMENT_IDS)]))
        analysis = agent.analyze(case, evaluation)
        review = agent.review(case, evaluation, ARGUMENTS)
        context = evidence_context(analysis, [review])

        assert context["summary"] == valid_analysis["summary"]
        assert len(context["claims"]) == 4
        assert len(context["provenance"]) == 8
        assert [r["argument_id"] for r in context["argument_reviews"]] == ARGUMENT_IDS
        json.dumps(context)  # plain data, ready for the prompt

    def test_review_prompt_does_not_duplicate_provenance(self, case, evaluation, valid_analysis):
        agent = EvidenceAgent(ScriptedProvider([valid_analysis]))
        context = evidence_context(agent.analyze(case, evaluation))
        prompt = agent.build_review_request(
            case, evaluation, ARGUMENTS, ARGUMENTS, context
        ).messages[0].content
        assert '"evidence_provenance"' not in prompt
        assert '"provenance"' in prompt
