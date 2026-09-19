"""Integration tests: auditing real trial runs, the audit stage, and the CLI

Deterministic checks are exercised against trials run with scripted
providers, then staged by adjusting one thing in the finished run - the
auditor inspects whatever record it is given.
"""

import json

import pytest

from app.agents.auditor import AuditCategory, Severity
from app.cli import main
from app.domain import AuditReport, CourtStage, MessageType
from app.llm import InteractionLog, ScriptedProvider
from app.workflow import (
    QUICK_DEBATE_STAGES,
    TrialRun,
    audit_trial,
    build_dossier,
    deterministic_findings,
    run_adversarial_trial,
)

from .conftest import (
    VALID_ANALYSIS,
    auditor_output,
    defense_turn,
    juror_verdict,
    prosecution_turn,
    review_for,
)

BOTH = ["PR-OPEN-1", "DF-OPEN-1"]


def judge_step(decision_with, mutate=None):
    def change(d):
        d["arguments_considered"] = list(BOTH)
        if mutate:
            mutate(d)

    return decision_with(change)


def quick_steps(decision_with, pro=None, dfn=None, judge_mutate=None):
    return [
        pro or prosecution_turn(),
        dfn or defense_turn(),
        prosecution_turn(),
        defense_turn(),
        judge_step(decision_with, judge_mutate),
    ]


def quick_run(steps, **kwargs) -> TrialRun:
    options = dict(stages=QUICK_DEBATE_STAGES, evidence=False, jury=False, audit=False)
    options.update(kwargs)
    return run_adversarial_trial("CASE_001", ScriptedProvider(steps), **options)


def checks(findings):
    return [f.check for f in findings]


def only(findings, check):
    matches = [f for f in findings if f.check == check]
    assert matches, f"no '{check}' finding in {checks(findings)}"
    return matches


# ============================================================================
# Deterministic checks
# ============================================================================


class TestCleanRun:
    def test_a_clean_quick_run_has_only_info_findings(self, decision_with):
        findings = deterministic_findings(quick_run(quick_steps(decision_with)))
        assert findings  # stages not implemented / skipped are always noted
        assert {f.severity for f in findings} == {Severity.INFO}
        assert all(f.finding_id.startswith("AUD-D-") for f in findings)

    def test_stages_not_implemented_versus_skipped(self, decision_with):
        findings = deterministic_findings(quick_run(quick_steps(decision_with)))
        not_implemented = {f.stage for f in only(findings, "stage_not_implemented")}
        assert not_implemented == {"CROSS_EXAMINATION", "JUDGE_QUESTIONS"}
        skipped = {f.stage for f in only(findings, "stage_skipped")}
        assert {"EVIDENCE_ANALYSIS", "JURY_DELIBERATION", "PROSECUTION_REBUTTAL"} <= skipped
        assert "PROSECUTION_OPENING" not in skipped


class TestEvidenceIntegrity:
    def test_caught_hallucination(self, decision_with):
        bad = prosecution_turn()
        bad["arguments"][0]["evidence_ids"] = ["E999"]
        steps = [bad] + quick_steps(decision_with)
        caught = only(deterministic_findings(quick_run(steps)), "caught_hallucination")
        assert caught[0].category == AuditCategory.HALLUCINATION
        assert caught[0].severity == Severity.MINOR
        assert caught[0].agent_id == "prosecution_agent"
        assert caught[0].stage == "PROSECUTION_OPENING"
        assert "E999" in caught[0].references

    def test_accepted_invalid_reference_is_critical(self, decision_with):
        run = quick_run(quick_steps(decision_with))
        run.turns[0].arguments[0].evidence_ids.append("E404")
        critical = only(deterministic_findings(run), "accepted_with_invalid_reference")
        assert critical[0].severity == Severity.CRITICAL
        assert "E404" in critical[0].references

    def test_unsupported_argument_and_neutrality(self, decision_with):
        analysis = json.loads(json.dumps(VALID_ANALYSIS))
        analysis["summary"] = "Alex should be acquitted."
        review = review_for(["PR-OPEN-1", "PR-OPEN-2", "DF-OPEN-1", "DF-OPEN-2"])
        review["reviews"][1].update(support="unsupported", issues=["F004 presented as settled"])
        review["reviews"][2].update(support="partially_supported", issues=["overclaims"])
        steps = [
            analysis,
            prosecution_turn(),
            defense_turn(),
            review,
            prosecution_turn(),
            defense_turn(),
            judge_step(decision_with),
        ]
        stages = [
            CourtStage.PROSECUTION_OPENING,
            CourtStage.DEFENSE_OPENING,
            CourtStage.EVIDENCE_REVIEW,
            CourtStage.CLOSING_ARGUMENTS,
        ]
        findings = deterministic_findings(quick_run(steps, stages=stages, evidence=True))

        unsupported = only(findings, "unsupported_argument")[0]
        assert (unsupported.severity, unsupported.agent_id) == (Severity.MINOR, "prosecution_agent")
        assert unsupported.references == ["PR-OPEN-2"]
        assert only(findings, "partially_supported_argument")[0].severity == Severity.INFO
        neutrality = only(findings, "evidence_agent_neutrality")[0]
        assert (neutrality.category, neutrality.severity) == (
            AuditCategory.PROCEDURAL,
            Severity.MAJOR,
        )


class TestLegalIntegrity:
    def test_judge_beyond_engine_support(self, decision_with):
        def convict(d):
            burglary = d["charge_decisions"][0]
            burglary["decision"] = "guilty"
            burglary["elements"][1]["assessment"] = "established"

        run = quick_run(quick_steps(decision_with, judge_mutate=convict))
        findings = deterministic_findings(run)
        conviction = only(findings, "judge_conviction_without_engine_support")[0]
        assert (conviction.category, conviction.severity) == (AuditCategory.LEGAL, Severity.MAJOR)
        assert conviction.references == ["LAW_104"]

    def test_defense_rule_for_another_party(self, decision_with):
        dfn = defense_turn()
        dfn["arguments"][1]["law_ids"] = ["LAW_201"]
        findings = deterministic_findings(quick_run(quick_steps(decision_with, dfn=dfn)))
        misapplied = only(findings, "defense_rule_other_party")[0]
        assert misapplied.severity == Severity.MINOR
        assert misapplied.references == ["DF-OPEN-2", "LAW_201"]
        assert "David Thompson" in misapplied.description


class TestReasoningIntegrity:
    def test_assumption_presented_as_fact(self, decision_with):
        pro = prosecution_turn()
        pro["arguments"][1]["assumptions"] = []
        findings = deterministic_findings(quick_run(quick_steps(decision_with, pro=pro)))
        flagged = only(findings, "assumption_presented_as_fact")[0]
        assert flagged.references == ["PR-OPEN-2"]
        assert flagged.category == AuditCategory.REASONING

    def test_one_side_ignored(self, decision_with):
        run = quick_run(quick_steps(decision_with))
        run.judgment.decision.arguments_considered = ["PR-OPEN-1"]
        ignored = only(deterministic_findings(run), "one_side_ignored")[0]
        assert ignored.severity == Severity.MAJOR
        assert "defense_agent" in ignored.description

    def test_jury_findings(self, decision_with):
        steps = quick_steps(decision_with)[:4] + [
            juror_verdict(considered=BOTH),
            juror_verdict(considered=BOTH),
            juror_verdict(assault="guilty", considered=BOTH),
            *[juror_verdict(assault="guilty", considered=BOTH, deliberation=True)] * 3,
            judge_step(decision_with),
        ]
        run = quick_run(steps, jury=True)
        findings = deterministic_findings(run)
        disagreement = only(findings, "judge_jury_disagreement")[0]
        assert disagreement.severity == Severity.MINOR
        assert "assault" in disagreement.description
        changes = only(findings, "vote_changed_in_deliberation")
        assert {c.agent_id for c in changes} == {"jury_1", "jury_2"}


class TestProceduralIntegrity:
    def test_role_violation(self, decision_with):
        run = quick_run(quick_steps(decision_with))
        run.messages[0].sender = "defense_agent"  # the prosecution opening
        violation = only(deterministic_findings(run), "role_violation")[0]
        assert violation.severity == Severity.MAJOR
        assert violation.references == ["MSG-PR-OPEN"]

    def test_repeated_rejections(self, decision_with):
        steps = ["bad", "worse"] + quick_steps(decision_with)
        repeated = only(deterministic_findings(quick_run(steps)), "repeated_rejections")[0]
        assert repeated.agent_id == "prosecution_agent"
        assert "3 attempts" in repeated.description


# ============================================================================
# audit_trial, the audit stage, and saved runs
# ============================================================================


class TestAuditTrial:
    def test_deterministic_only(self, decision_with):
        audit = audit_trial(quick_run(quick_steps(decision_with)))
        assert audit.auditor is None
        assert isinstance(audit.report, AuditReport)
        assert audit.report.metadata["deterministic_only"] is True
        assert audit.report.metadata["overall_status"] == "clean"

    def test_with_the_auditor_agent(self, decision_with):
        run = quick_run(quick_steps(decision_with))
        provider = ScriptedProvider([auditor_output()])
        audit = audit_trial(run, provider)
        assert audit.findings[-1].finding_id == "AUD-A-001"
        report = audit.report
        assert report.final_assessment == auditor_output()["final_assessment"]
        assert report.metadata["overall_status"] == "minor_issues"
        assert report.metadata["sources"]["auditor_agent"] == 1
        assert len(report.metadata["decision_chain"]) == 4
        assert report.reasoning_issues[-1]["check"] == "self_contradiction"

    def test_dossier(self, decision_with):
        from app.rules import LegalRuleRegistry

        run = quick_run(quick_steps(decision_with))
        dossier = build_dossier(run, LegalRuleRegistry())
        assert [m["message_id"] for m in dossier["transcript"]][0] == "MSG-PR-OPEN"
        assert len(dossier["party_arguments"]) == 8
        assert dossier["judgment"]["arguments_considered"] == BOTH

    def test_auditor_sees_the_dossier(self, decision_with):
        run = quick_run(quick_steps(decision_with))
        provider = ScriptedProvider([auditor_output()])
        audit_trial(run, provider)
        content = provider.requests[0].messages[0].content
        assert '"transcript"' in content and '"judgment"' in content
        assert '"check": "stage_not_implemented"' in content

    def test_saved_run_audits_identically(self, decision_with, tmp_path):
        run = quick_run(quick_steps(decision_with))
        path = tmp_path / "run.json"
        path.write_text(run.model_dump_json(), encoding="utf-8")
        reloaded = TrialRun.model_validate_json(path.read_text(encoding="utf-8"))
        assert [f.model_dump() for f in deterministic_findings(reloaded)] == [
            f.model_dump() for f in deterministic_findings(run)
        ]


class TestAuditStage:
    def test_audit_closes_the_trial(self, decision_with):
        steps = quick_steps(decision_with) + [auditor_output()]
        log = InteractionLog()
        run = quick_run(steps, audit=True, log=log)

        kinds = [(e["stage"], e["event_type"]) for e in run.event_history]
        assert kinds[-3:] == [
            ("LEGAL_PROCESS_AUDIT", "AGENT_STARTED"),
            ("LEGAL_PROCESS_AUDIT", "AUDIT_COMPLETED"),
            ("CASE_COMPLETE", "CASE_COMPLETE"),
        ]
        completed = run.event_history[-2]
        assert completed["overall_status"] == "minor_issues"
        assert completed["deterministic_only"] is False
        assert run.messages[-1].message_type == MessageType.AUDIT_REPORT
        assert run.messages[-1].sender == "auditor_agent"
        assert run.audit_report.audit_id == "AUD_CASE_001"
        assert [r.agent_id for r in log.records][-1] == "auditor_agent"
        assert run.usage.output_tokens > run.judgment.usage.output_tokens

    def test_audit_without_the_agent(self, decision_with):
        provider = ScriptedProvider(quick_steps(decision_with))
        run = run_adversarial_trial(
            "CASE_001",
            provider,
            stages=QUICK_DEBATE_STAGES,
            evidence=False,
            jury=False,
            audit_agent=False,
        )
        assert provider.remaining == 0
        assert run.audit.auditor is None
        assert run.event_history[-2]["deterministic_only"] is True

    def test_per_role_providers_audit_deterministically(self, decision_with):
        steps = quick_steps(decision_with)
        run = run_adversarial_trial(
            "CASE_001",
            prosecution_provider=ScriptedProvider([steps[0], steps[2]]),
            defense_provider=ScriptedProvider([steps[1], steps[3]]),
            judge_provider=ScriptedProvider([steps[4]]),
            stages=QUICK_DEBATE_STAGES,
            evidence=False,
            jury=False,
        )
        assert run.audit is not None and run.audit.auditor is None

    def test_a_separate_auditor_model(self, decision_with):
        auditor = ScriptedProvider([auditor_output()])
        run = quick_run(quick_steps(decision_with), audit=True, auditor_provider=auditor)
        assert auditor.remaining == 0
        assert run.audit.auditor is not None


# ============================================================================
# CLI
# ============================================================================


class TestAuditCli:
    def _patch(self, monkeypatch, steps):
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(steps)
        )

    def test_trial_prints_the_audit(self, monkeypatch, capsys, tmp_path, decision_with):
        self._patch(monkeypatch, quick_steps(decision_with) + [auditor_output()])
        args = ["trial", "CASE_001", "--quick", "--no-evidence", "--no-jury"]
        assert main(args + ["--log-file", str(tmp_path / "a.jsonl")]) == 0
        out = capsys.readouterr().out
        assert "[LEGAL_PROCESS_AUDIT] AUD_CASE_001 - deterministic checks + auditor agent" in out
        assert "overall: MINOR_ISSUES" in out
        assert "AUD-A-001 [minor   ] reasoning     self_contradiction" in out
        assert "chain facts_to_evidence: sound" in out
        assert out.index("[JUDGE_DECISION]") < out.index("[LEGAL_PROCESS_AUDIT]")

    def test_deterministic_audit_flag(self, monkeypatch, capsys, tmp_path, decision_with):
        self._patch(monkeypatch, quick_steps(decision_with))
        args = ["trial", "CASE_001", "--quick", "--no-evidence", "--no-jury"]
        args += ["--deterministic-audit", "--log-file", str(tmp_path / "a.jsonl")]
        assert main(args) == 0
        assert "deterministic checks only" in capsys.readouterr().out

    def test_audit_a_saved_run(self, capsys, tmp_path, decision_with):
        path = tmp_path / "run.json"
        path.write_text(quick_run(quick_steps(decision_with)).model_dump_json(), encoding="utf-8")
        assert main(["audit", str(path), "--deterministic-only"]) == 0
        out = capsys.readouterr().out
        assert "saved run:" in out
        assert "overall: CLEAN" in out
        assert "stage_not_implemented" in out

    def test_audit_a_saved_run_with_the_agent(self, monkeypatch, capsys, tmp_path, decision_with):
        path = tmp_path / "run.json"
        path.write_text(quick_run(quick_steps(decision_with)).model_dump_json(), encoding="utf-8")
        self._patch(monkeypatch, [auditor_output()])
        code = main(["audit", str(path), "--json", "--log-file", str(tmp_path / "a.jsonl")])
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["report"]["metadata"]["deterministic_only"] is False

    def test_unreadable_run_file(self, capsys, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not a run}", encoding="utf-8")
        assert main(["audit", str(bad), "--deterministic-only"]) == 2
        assert "Cannot load trial run" in capsys.readouterr().err
