"""Tests for the Legal Process Auditor: findings, report, and the auditor agent"""

import pytest

from app.agents.auditor import (
    AuditCategory,
    AuditFinding,
    AuditorAgent,
    AuditorAgentError,
    AuditorOutput,
    AuditorValidator,
    FindingSource,
    OverallStatus,
    Severity,
    SYSTEM_PROMPT,
    build_audit_report,
    overall_status,
    severity_counts,
    summarise,
)
from app.llm import InteractionLog, ScriptedProvider

from .conftest import auditor_output


def finding(severity: Severity, category=AuditCategory.REASONING, n: int = 1) -> AuditFinding:
    return AuditFinding(
        finding_id=f"AUD-D-{n:03d}",
        category=category,
        severity=severity,
        check="test_check",
        description="A finding",
        source=FindingSource.DETERMINISTIC,
    )


class TestStatusAndReport:
    @pytest.mark.parametrize(
        "severities,status",
        [
            ([], OverallStatus.CLEAN),
            ([Severity.INFO, Severity.INFO], OverallStatus.CLEAN),
            ([Severity.INFO, Severity.MINOR], OverallStatus.MINOR_ISSUES),
            ([Severity.MINOR, Severity.MAJOR], OverallStatus.MAJOR_ISSUES),
            ([Severity.MAJOR, Severity.CRITICAL], OverallStatus.CRITICAL_ISSUES),
        ],
    )
    def test_worst_severity_decides(self, severities, status):
        assert overall_status([finding(s) for s in severities]) == status

    def test_counts_and_summary(self):
        findings = [finding(Severity.MAJOR), finding(Severity.INFO), finding(Severity.INFO)]
        assert severity_counts(findings) == {"info": 2, "minor": 0, "major": 1, "critical": 0}
        assert summarise(findings) == "Overall status: major_issues (1 major, 2 info)."
        assert summarise([]) == "Overall status: clean (no findings)."

    def test_findings_are_filed_by_category(self):
        findings = [
            finding(Severity.MINOR, AuditCategory.EVIDENCE, 1),
            finding(Severity.MINOR, AuditCategory.LEGAL, 2),
            finding(Severity.MINOR, AuditCategory.PROCEDURAL, 3),
            finding(Severity.MINOR, AuditCategory.REASONING, 4),
            finding(Severity.CRITICAL, AuditCategory.HALLUCINATION, 5),
        ]
        report = build_audit_report("CASE_001", findings, metadata={"x": 1})
        assert report.audit_id == "AUD_CASE_001"
        assert [f["finding_id"] for f in report.evidence_violations] == ["AUD-D-001"]
        assert [f["finding_id"] for f in report.legal_violations] == ["AUD-D-002"]
        assert [f["finding_id"] for f in report.procedural_violations] == ["AUD-D-003"]
        assert [f["finding_id"] for f in report.reasoning_issues] == ["AUD-D-004"]
        assert [f["finding_id"] for f in report.hallucinations] == ["AUD-D-005"]
        assert report.metadata["overall_status"] == "critical_issues"
        assert report.metadata["sources"] == {"deterministic": 5, "auditor_agent": 0}
        assert report.metadata["x"] == 1
        assert report.final_assessment.startswith("Overall status: critical_issues")

    def test_agent_assessment_takes_precedence(self):
        report = build_audit_report("CASE_001", [], final_assessment="All good.")
        assert report.final_assessment == "All good."


class TestAuditorValidation:
    def _validator(self):
        return AuditorValidator(
            participants={"prosecution_agent", "defense_agent", "judge_agent"},
            stages={"PROSECUTION_OPENING", "CLOSING_ARGUMENTS", "JUDGE_DECISION"},
            known_ids={"PR-OPEN-2", "PR-CLOSE-2", "F004", "E007", "LAW_101"},
        )

    def _validate(self, data):
        return self._validator().validate(AuditorOutput.model_validate(data))

    def test_valid_output(self):
        assert self._validate(auditor_output()) == []

    def test_empty_findings_are_a_valid_answer(self):
        assert self._validate(auditor_output(findings=[])) == []

    def test_unknown_agent(self):
        data = auditor_output()
        data["findings"][0]["agent_id"] = "jury_9"
        assert any("agent 'jury_9' did not take part" in e for e in self._validate(data))

    def test_unknown_stage(self):
        data = auditor_output()
        data["findings"][0]["stage"] = "CROSS_EXAMINATION"
        assert any("stage 'CROSS_EXAMINATION' did not occur" in e for e in self._validate(data))

    def test_unknown_reference(self):
        data = auditor_output()
        data["findings"][0]["references"].append("E999")
        assert any("unknown reference 'E999'" in e for e in self._validate(data))

    def test_empty_agent_and_stage_are_allowed(self):
        data = auditor_output()
        data["findings"][0].update(agent_id="", stage="")
        assert self._validate(data) == []

    def test_every_chain_link_rated_once(self):
        data = auditor_output()
        data["decision_chain"].pop()
        errors = self._validate(data)
        assert any("'analysis_to_decision' exactly once (found 0)" in e for e in errors)
        data = auditor_output()
        data["decision_chain"].append(dict(data["decision_chain"][0]))
        assert any("'facts_to_evidence' exactly once (found 2)" in e for e in self._validate(data))

    def test_finding_limit(self):
        data = auditor_output(findings=[auditor_output()["findings"][0]] * 26)
        assert any("at most 25" in e for e in self._validate(data))


class TestAuditorAgent:
    def test_system_prompt_forbids_deciding_the_case(self):
        assert "You do not decide the case" in SYSTEM_PROMPT
        assert "FACTS -> EVIDENCE -> LAW -> ANALYSIS" in SYSTEM_PROMPT
        assert "Do not repeat" in SYSTEM_PROMPT

    def test_prompt_carries_the_dossier_and_deterministic_findings(self):
        agent = AuditorAgent(ScriptedProvider([]))
        request = agent.build_request({"case": {"case_id": "CASE_001"}}, [finding(Severity.MINOR)])
        content = request.messages[0].content
        assert "<trial_dossier>" in content and '"case_id": "CASE_001"' in content
        assert "<deterministic_findings>" in content and '"check": "test_check"' in content
        assert request.schema_name == "process_audit"

    def _audit(self, provider, log=None):
        return AuditorAgent(provider, log=log).audit(
            "CASE_001",
            {"case": {}},
            [finding(Severity.INFO)],
            participants={"prosecution_agent"},
            stages={"CLOSING_ARGUMENTS"},
            known_ids={"PR-OPEN-2", "PR-CLOSE-2", "F004"},
        )

    def test_audit(self):
        log = InteractionLog()
        result = self._audit(ScriptedProvider([auditor_output()]), log)
        assert [f.finding_id for f in result.findings] == ["AUD-A-001"]
        assert result.findings[0].source == FindingSource.AUDITOR_AGENT
        assert result.findings[0].check == "self_contradiction"
        assert log.records[0].agent_id == "auditor_agent"

    def test_invalid_audit_is_regenerated(self):
        bad = auditor_output()
        bad["findings"][0]["references"] = ["E999"]
        provider = ScriptedProvider([bad, auditor_output()])
        result = self._audit(provider)
        assert [a.accepted for a in result.attempts] == [False, True]
        assert "E999" in provider.requests[1].messages[2].content

    def test_gives_up(self):
        with pytest.raises(AuditorAgentError, match="process audit"):
            self._audit(ScriptedProvider(["no"] * 3))
