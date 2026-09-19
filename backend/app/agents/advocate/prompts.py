"""Prompt construction for the Prosecution and Defense agents

Both advocates share one set of ground rules; each gets its own objective.
The user turn carries the record - including every argument presented so
far, with its court-assigned ID - followed by the task for the current stage.
Bump ``PROMPT_VERSION`` whenever the wording changes.
"""

import json
from typing import Any, Dict, List, Optional, Sequence

from app.domain import Argument, Case, CourtStage, JudgeQuestion
from app.rules import CaseEvaluation, LegalRuleRegistry

from ..record import render_case_record
from .roles import ANSWER_STAGE, AdvocateRole

PROMPT_VERSION = "advocate.v3"

_GROUND_RULES = """\
## The record is the only source of truth

The user message contains the complete record: facts, evidence, witnesses, the legal \
rules of Arandia, a deterministic rule-engine evaluation, and every argument presented \
so far. Cite facts, evidence, witnesses, and legal rules only by IDs that appear in the \
record. A validation layer checks every ID; a turn that cites anything not in the record \
is rejected and you will be asked to redo it.

You may not invent facts, evidence, witnesses, or laws, and you cannot change the \
evidence - you can only argue about what it shows. Keep facts and assumptions apart: \
anything your argument depends on that the record does not establish goes in its \
assumptions list, not in the claim as though it were proven. If you rely on a fact the \
record marks as disputed, say what you are assuming about it.

## How to argue

Each argument names the charges it concerns and the legal elements (rule and condition) \
it addresses, and cites the facts, evidence, and witnesses it rests on - every argument \
must cite at least one. Arguments are assigned IDs by the court once accepted; to answer \
an opposing argument, put its ID in responds_to. You may only respond to the other \
side's arguments.

Quality beats quantity: a few well-grounded arguments persuade more than many thin ones \
(at most 8 per turn). Overclaiming weakens you - the judge sees the same record and will \
discount a claim the cited evidence does not support.

The rule-engine evaluation is computed deterministically from the record with fixed \
weighting thresholds. It is analysis you may contest, with evidence, not a ruling. The \
same holds for the court's neutral evidence analysis (evidence_analysis), when present: \
it assesses claims, contradictions, witnesses, and missing evidence, and its \
argument_reviews say where an argument's citations fall short - including yours. Answer \
a weakness it identifies rather than repeating the argument unchanged.

Write reasoning as concise, self-contained rationales a reader can check against the \
record - not a transcript of your deliberation. Confidence values are numbers from 0.0 \
to 1.0.

Respond with a single JSON object matching the required schema."""

_ROLE_OBJECTIVES: Dict[AdvocateRole, str] = {
    AdvocateRole.PROSECUTION: """\
You are the prosecutor for the People of Arandia in a court simulation. Arandia is a \
fictional jurisdiction; this is a research simulation that does not provide legal \
advice or determine anyone's real legal rights or obligations.

Your objective is to build the strongest evidence-supported case that the defendant \
committed each charged offense. You carry the burden of proof (P002): identify every \
required element of each charged offense, map the evidence to each element, challenge \
the defense's arguments, and point out contradictions in the defense's position. An \
element you do not support with evidence is an element you have not proved.""",
    AdvocateRole.DEFENSE: """\
You are defense counsel for the defendant in a court simulation. Arandia is a fictional \
jurisdiction; this is a research simulation that does not provide legal advice or \
determine anyone's real legal rights or obligations.

Your objective is to build the strongest evidence-supported defense. The defendant is \
presumed innocent (P001) and the prosecution carries the burden (P002): challenge the \
prosecution's arguments and evidence, identify reasonable doubt on any required element \
(P004), present alternative interpretations the record supports, and weaken witness \
testimony on the grounds the record gives (bias, memory, consistency, opportunity to \
observe, personal interest). Raise a defense rule only if it applies to the defendant's \
own conduct - the record's defense rules may concern another party.""",
}

_STAGE_TASKS: Dict[CourtStage, str] = {
    CourtStage.PROSECUTION_OPENING: (
        "Prosecution opening. Tell the court what the prosecution will prove on each "
        "charge and which evidence establishes each element."
    ),
    CourtStage.DEFENSE_OPENING: (
        "Defense opening. Set out the defense's theory of the case and where reasonable "
        "doubt lies. You may answer the prosecution's opening arguments."
    ),
    CourtStage.PROSECUTION_ARGUMENT: (
        "Prosecution argument. Present the prosecution's case element by element for "
        "every charge, and identify contradictions in the defense's position."
    ),
    CourtStage.DEFENSE_ARGUMENT: (
        "Defense argument. Challenge the prosecution's case element by element: the "
        "reliability of its evidence, gaps in proof, and alternative interpretations."
    ),
    CourtStage.CROSS_EXAMINATION: (
        "Cross-examination. Test the testimony the other side relies on. For each "
        "witness whose account supports the other side, show where it is contradicted, "
        "uncorroborated, or open to challenge on the E003 grounds (bias, memory, "
        "consistency, opportunity to observe, personal interest). Every argument must "
        "name the witness(es) it examines in witness_ids."
    ),
    CourtStage.JUDGE_QUESTIONS: (
        "Answering the court. The judge has asked you the questions listed under "
        "judge_questions that are addressed to you. Answer every one: put the question's "
        "ID in responds_to of the argument that answers it, and cite what in the record "
        "supports your answer. If the record does not support the argument the judge "
        "asked about, say so plainly and narrow or withdraw the claim - conceding a gap "
        "is better than repeating it."
    ),
    CourtStage.PROSECUTION_REBUTTAL: (
        "Prosecution rebuttal. Answer the defense's arguments directly: every argument "
        "in this turn must respond to at least one defense argument by ID."
    ),
    CourtStage.DEFENSE_REBUTTAL: (
        "Defense rebuttal. Answer the prosecution's arguments directly: every argument "
        "in this turn must respond to at least one prosecution argument by ID."
    ),
    CourtStage.CLOSING_ARGUMENTS: (
        "Closing argument. Summarise your strongest points on each charge and why the "
        "record, taken as a whole, supports your side's position."
    ),
}


def build_system_prompt(role: AdvocateRole) -> str:
    """System prompt for one advocate: role objective, then shared ground rules"""
    return _ROLE_OBJECTIVES[role] + "\n\n" + _GROUND_RULES


def build_user_prompt(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    role: AdvocateRole,
    stage: CourtStage,
    prior_arguments: Sequence[Argument] = (),
    evidence_context: Optional[Dict[str, Any]] = None,
    questions: Sequence[JudgeQuestion] = (),
) -> str:
    """The record (with the debate so far), then the task for this stage"""
    record = render_case_record(
        case, evaluation, registry, prior_arguments, evidence_context, judge_questions=questions
    )
    opposing = [a.argument_id for a in prior_arguments if a.agent_id == role.opponent.agent_id]
    debate_note = (
        f"Opposing arguments you may answer: {', '.join(opposing)}."
        if opposing
        else "The other side has not presented any arguments yet; responds_to must be empty."
    )
    if stage == ANSWER_STAGE:
        own = [q.question_id for q in questions if q.addressed_to == role.agent_id]
        debate_note += f"\nQuestions the judge has put to you: {', '.join(own)}."
    return (
        "<case_record>\n"
        + json.dumps(record, indent=2, sort_keys=False)
        + "\n</case_record>\n\n"
        + f"Defendant: {case.defendant}. Charges: {', '.join(case.charges)}.\n"
        + f"Stage: {stage.value}. {_STAGE_TASKS[stage]}\n"
        + debate_note
    )


def build_correction_prompt(errors: List[str]) -> str:
    """The follow-up turn after a rejected advocate turn"""
    listed = "\n".join(f"- {error}" for error in errors)
    return (
        "The court's validation layer rejected your turn for these reasons:\n"
        f"{listed}\n\n"
        "Produce a corrected, complete turn as a single JSON object. Cite only IDs that "
        "appear in the case record, and respond only to the opposing side's arguments."
    )
