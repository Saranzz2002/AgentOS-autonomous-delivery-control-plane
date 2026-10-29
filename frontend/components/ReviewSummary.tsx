import { Finding, ReviewFindingCard } from "@/components/ReviewFinding";
import { ReviewScores } from "@/components/ReviewScores";

export type Review = {
  recommendation: "APPROVE" | "CHANGES_REQUESTED" | "REJECT";
  summary: string;
  task_compliance_score: number;
  code_quality_score: number;
  test_quality_score: number;
  security_score: number;
  findings: Finding[];
  strengths: string[];
  risks: string[];
};

export function ReviewSummary({ review }: { review: Review }) {
  const style = review.recommendation === "APPROVE" ? "text-lime-200 border-lime-300/30 bg-lime-300/10" : review.recommendation === "REJECT" ? "text-rose-200 border-rose-300/30 bg-rose-300/10" : "text-amber-100 border-amber-300/30 bg-amber-300/10";
  return <section className="space-y-5 rounded-2xl border border-white/10 bg-[#101615] p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-[10px] tracking-widest text-slate-500">AI CODE REVIEW</div><h2 className="mt-1 text-lg font-semibold">Review complete</h2></div><span className={`rounded-lg border px-3 py-2 text-xs font-semibold ${style}`}>{review.recommendation === "APPROVE" ? "READY FOR HUMAN APPROVAL" : review.recommendation}</span></div><p className="text-sm leading-6 text-slate-300">{review.summary}</p><ReviewScores scores={review}/><div><h3 className="mb-3 text-sm font-semibold">Review findings</h3>{review.findings.length ? <div className="space-y-3">{review.findings.map((finding, index) => <ReviewFindingCard key={`${finding.category}-${finding.file}-${index}`} finding={finding}/>)}</div> : <p className="text-xs text-lime-200">✓ No blocking findings reported.</p>}</div><div className="grid gap-4 sm:grid-cols-2">{review.strengths.length > 0 && <div><h3 className="mb-2 text-xs font-semibold text-lime-200">Strengths</h3><ul className="list-disc space-y-1 pl-4 text-xs text-slate-400">{review.strengths.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}{review.risks.length > 0 && <div><h3 className="mb-2 text-xs font-semibold text-amber-200">Risks</h3><ul className="list-disc space-y-1 pl-4 text-xs text-slate-400">{review.risks.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}</div></section>;
}
