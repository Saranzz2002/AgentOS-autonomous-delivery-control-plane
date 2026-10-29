type Scores = { task_compliance_score: number; code_quality_score: number; test_quality_score: number; security_score: number };

export function ReviewScores({ scores }: { scores: Scores }) {
  const rows: [string, number][] = [
    ["Task compliance", scores.task_compliance_score], ["Code quality", scores.code_quality_score],
    ["Test quality", scores.test_quality_score], ["Security", scores.security_score],
  ];
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{rows.map(([label, score]) => <div key={label} className="rounded-lg border border-white/[0.08] bg-black/20 p-3"><div className="text-[10px] text-slate-400">{label}</div><div className="mt-1 text-xl font-semibold text-lime-200">{score}<span className="text-xs text-slate-500"> / 10</span></div></div>)}</div>;
}
