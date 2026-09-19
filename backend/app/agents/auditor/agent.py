"""The Legal Process Auditor agent

Reviews a trial dossier for what deterministic checks cannot judge, and
rates the judge's decision chain. Its output is validated like every other
agent's: an unknown agent, stage, or referenced ID is rejected and the audit
regenerated.
"""

from typing import Any, Collection, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from app.domain import AuditReport
from app.llm import (
    InteractionLog,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    MessageRole,
    TokenUsage,
    strict_json_schema,
)

from ..base import AgentAttempt, AgentError, generate_validated, parse_model_output
from .findings import AuditFinding, FindingSource
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_audit_prompt, build_correction_prompt
from .schema import AuditorOutput, ChainLink

AUDITOR_AGENT_ID = "auditor_agent"
MAX_AUDITOR_FINDINGS = 25


class AuditorAgentError(AgentError):
    """The auditor could not produce a valid audit"""


class AuditorValidator:
    """Checks that the audit refers only to things that exist in the trial"""

    def __init__(
        self,
        participants: Collection[str],
        stages: Collection[str],
        known_ids: Collection[str],
    ) -> None:
        self.participants = set(participants)
        self.stages = set(stages)
        self.known_ids = set(known_ids)

    def validate(self, output: AuditorOutput) -> List[str]:
        errors: List[str] = []
        if len(output.findings) > MAX_AUDITOR_FINDINGS:
            errors.append(
                f"{len(output.findings)} findings; report at most {MAX_AUDITOR_FINDINGS}, "
                "the most significant first."
            )
        for index, finding in enumerate(output.findings, start=1):
            where = f"finding {index} ({finding.issue_type})"
            if finding.agent_id and finding.agent_id not in self.participants:
                errors.append(
                    f"{where}: agent '{finding.agent_id}' did not take part in this trial "
                    f"({', '.join(sorted(self.participants))})."
                )
            if finding.stage and finding.stage not in self.stages:
                errors.append(
                    f"{where}: stage '{finding.stage}' did not occur in this trial "
                    f"({', '.join(sorted(self.stages))})."
                )
            for reference in finding.references:
                if reference not in self.known_ids:
                    errors.append(
                        f"{where}: unknown reference '{reference}'; it is not an argument, "
                        "message, fact, evidence, witness, or rule in this trial."
                    )

        links = [c.link for c in output.decision_chain]
        for link in ChainLink:
            count = links.count(link)
            if count != 1:
                errors.append(
                    f"decision_chain must rate '{link.value}' exactly once (found {count})."
                )
        return errors


class AuditorResult(BaseModel):
    """The accepted audit from the auditor agent"""

    output: AuditorOutput
    findings: List[AuditFinding]
    attempts: List[AgentAttempt] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    provider: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def rejected_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.accepted)


class AuditorAgent:
    """The Legal Process Auditor"""

    agent_id = AUDITOR_AGENT_ID

    def __init__(
        self,
        provider: LLMProvider,
        log: Optional[InteractionLog] = None,
        max_attempts: int = 3,
        max_tokens: int = 16000,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.provider = provider
        self.log = log if log is not None else InteractionLog()
        self.max_attempts = max_attempts
        self.max_tokens = max_tokens
        self.output_schema = strict_json_schema(AuditorOutput)

    def build_request(
        self, dossier: Dict[str, Any], deterministic: Sequence[AuditFinding]
    ) -> LLMRequest:
        return LLMRequest(
            system=SYSTEM_PROMPT,
            messages=[
                LLMMessage(
                    role=MessageRole.USER, content=build_audit_prompt(dossier, deterministic)
                )
            ],
            json_schema=self.output_schema,
            schema_name="process_audit",
            max_tokens=self.max_tokens,
        )

    def audit(
        self,
        case_id: str,
        dossier: Dict[str, Any],
        deterministic: Sequence[AuditFinding],
        participants: Collection[str],
        stages: Collection[str],
        known_ids: Collection[str],
    ) -> AuditorResult:
        """Audit one trial beyond what the deterministic checks already found"""
        validator = AuditorValidator(participants, stages, known_ids)

        def parse(text: str) -> Tuple[Optional[AuditorOutput], List[str]]:
            output, errors = parse_model_output(text, AuditorOutput)
            if output is None:
                return None, errors
            return output, validator.validate(output)

        generation = generate_validated(
            provider=self.provider,
            log=self.log,
            agent_id=self.agent_id,
            prompt_version=PROMPT_VERSION,
            case_id=case_id,
            request=self.build_request(dossier, deterministic),
            parse=parse,
            max_attempts=self.max_attempts,
            correction=build_correction_prompt,
            error_cls=AuditorAgentError,
            task="process audit",
        )
        output = generation.output
        findings = [
            AuditFinding(
                finding_id=f"AUD-A-{index:03d}",
                category=f.category,
                severity=f.severity,
                check=f.issue_type,
                agent_id=f.agent_id,
                stage=f.stage,
                description=f.description,
                references=list(f.references),
                source=FindingSource.AUDITOR_AGENT,
            )
            for index, f in enumerate(output.findings, start=1)
        ]
        return AuditorResult(
            output=output,
            findings=findings,
            attempts=generation.attempts,
            provider=generation.response.provider,
            model=generation.response.model,
            usage=generation.usage,
        )


class ProcessAudit(BaseModel):
    """The complete audit of one trial"""

    findings: List[AuditFinding]
    report: AuditReport
    auditor: Optional[AuditorResult] = None

    @property
    def usage(self) -> TokenUsage:
        return self.auditor.usage if self.auditor else TokenUsage()
