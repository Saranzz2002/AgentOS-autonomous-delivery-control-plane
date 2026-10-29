export type Finding = { severity: "critical" | "high" | "medium" | "low" | "info"; category: string; file: string | null; line: number | null; description: string; recommendation: string };

const styles: Record<Finding["severity"], string> = {
  critical: "border-rose-400/30 bg-rose-400/10 text-rose-200", high: "border-orange-300/30 bg-orange-300/10 text-orange-200",
  medium: "border-amber-300/30 bg-amber-300/10 text-amber-100", low: "border-sky-300/30 bg-sky-300/10 text-sky-100",
  info: "border-slate-300/20 bg-slate-300/5 text-slate-300",
};

export function ReviewFindingCard({ finding }: { finding: Finding }) {
  return <article className="rounded-xl border border-white/[0.08] bg-black/20 p-4"><div className="flex flex-wrap items-center gap-2"><span className={`rounded border px-2 py-1 text-[10px] font-bold uppercase ${styles[finding.severity]}`}>{finding.severity}</span><span className="text-[10px] uppercase tracking-wider text-slate-400">{finding.category}</span>{finding.file && <code className="ml-auto text-[10px] text-slate-400">{finding.file}{finding.line ? `:${finding.line}` : ""}</code>}</div><p className="mt-3 text-sm text-slate-200">{finding.description}</p><p className="mt-2 text-xs leading-5 text-slate-400"><b className="text-slate-300">Recommendation:</b> {finding.recommendation}</p></article>;
}
