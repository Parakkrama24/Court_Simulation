/**
 * Evidence panel: the evidence itself, and what the Evidence Agent made of it.
 *
 * Spec section 20 asks for evidence, supporting claims, contradicting claims,
 * and reliability. Reliability is the record's own number - the agent may note
 * it but never changes it.
 */

import { percent, titleCase } from "@/lib/court";
import type { Case, EvidenceAnalysis, EvidenceProvenance } from "@/lib/types";
import { EvidenceList } from "@/components/CaseRecord";
import { Badge, Empty, IdList, Meter, cx } from "@/components/ui";

const RATING_STYLES: Record<string, string> = {
  high: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  moderate: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  low: "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

const CLAIM_STYLES: Record<string, string> = {
  established: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  disputed: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  unsupported: "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

export function EvidencePanel({
  record,
  analysis,
  provenance,
}: {
  record: Case;
  analysis: EvidenceAnalysis | null;
  provenance?: EvidenceProvenance[];
}) {
  return (
    <div className="space-y-5">
      {analysis ? (
        <>
          <p className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm text-slate-200">
            {analysis.output.summary}
          </p>

          <section>
            <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
              Claims the record supports
            </h3>
            <ul className="space-y-2">
              {analysis.output.claims.map((claim, index) => (
                <li
                  key={`${claim.claim}-${index}`}
                  className="rounded-lg border border-slate-800 bg-slate-900/30 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={CLAIM_STYLES[claim.status]}>
                      {titleCase(claim.status)}
                    </Badge>
                    <span className="ms-auto flex items-center gap-1.5 text-xs text-slate-500">
                      confidence
                      <Meter
                        value={claim.confidence}
                        tone={claim.confidence >= 0.7 ? "emerald" : "amber"}
                      />
                      {percent(claim.confidence)}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-slate-100">{claim.claim}</p>
                  <p className="mt-1 text-sm text-slate-400">
                    {claim.reasoning}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <IdList label="facts" ids={claim.fact_ids} />
                    <IdList
                      label="supported by"
                      ids={[
                        ...claim.supporting_evidence_ids,
                        ...claim.supporting_witness_ids,
                      ]}
                    />
                    <IdList
                      label="contradicted by"
                      ids={[
                        ...claim.contradicting_evidence_ids,
                        ...claim.contradicting_witness_ids,
                      ]}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {analysis.output.evidence.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
                How each exhibit bears on the case
              </h3>
              <ul className="space-y-1.5">
                {analysis.output.evidence.map((item) => (
                  <li
                    key={item.evidence_id}
                    className="rounded-lg border border-slate-800 bg-slate-900/30 p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <IdList ids={[item.evidence_id]} />
                      <Badge>{titleCase(item.directness)}</Badge>
                      <IdList label="bears on" ids={item.fact_ids} />
                      {item.reliability_concerns.map((concern) => (
                        <Badge
                          key={concern}
                          className="border-amber-500/30 bg-amber-500/10 text-amber-300"
                        >
                          {concern}
                        </Badge>
                      ))}
                    </div>
                    <p className="mt-1 text-slate-400">{item.reasoning}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {analysis.output.contradictions.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
                Contradictions in the record
              </h3>
              <ul className="space-y-2">
                {analysis.output.contradictions.map((item, index) => (
                  <li
                    key={index}
                    className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3"
                  >
                    <p className="text-sm text-slate-100">{item.description}</p>
                    <p className="mt-1 text-xs text-amber-200/80">
                      {item.significance}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <IdList
                        ids={[
                          ...item.evidence_ids,
                          ...item.witness_ids,
                          ...item.fact_ids,
                        ]}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {analysis.output.missing_evidence.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
                What the record does not have
              </h3>
              <ul className="space-y-2">
                {analysis.output.missing_evidence.map((item, index) => (
                  <li
                    key={index}
                    className="rounded-lg border border-slate-800 bg-slate-900/30 p-3"
                  >
                    <p className="text-sm text-slate-100">{item.description}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {item.why_it_matters}
                    </p>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {item.elements.map((element) => (
                        <Badge
                          key={`${element.rule_id}-${element.condition_id}`}
                          className="border-amber-500/30 bg-amber-500/10 text-amber-300"
                        >
                          {element.rule_id} · {element.condition_id}
                        </Badge>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {analysis.output.witnesses.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
                Witness notes
              </h3>
              <ul className="space-y-2">
                {analysis.output.witnesses.map((note) => (
                  <li
                    key={note.witness_id}
                    className="rounded-lg border border-slate-800 bg-slate-900/30 p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <IdList ids={[note.witness_id]} />
                      <Badge className={RATING_STYLES[note.rating]}>
                        {titleCase(note.rating)} reliability
                      </Badge>
                      {note.grounds.map((ground) => (
                        <Badge
                          key={ground}
                          className="border-amber-500/30 bg-amber-500/10 text-amber-300"
                          title="Ground for challenge under evidence rule E003"
                        >
                          {ground}
                        </Badge>
                      ))}
                    </div>
                    <p className="mt-1.5 text-slate-300">{note.reasoning}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {analysis.flags.length > 0 && (
            <p
              className={cx(
                "rounded-lg border border-amber-500/30 bg-amber-500/5 p-3",
                "text-xs text-amber-200",
              )}
            >
              Validation flags: {analysis.flags.join("; ")}
            </p>
          )}
        </>
      ) : (
        <Empty>
          The Evidence Agent did not run in this simulation, so the evidence
          below is the record as filed.
        </Empty>
      )}

      <section>
        <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
          Evidence on the record
        </h3>
        <EvidenceList
          evidence={record.evidence}
          provenance={provenance ?? analysis?.provenance ?? []}
        />
      </section>
    </div>
  );
}
