const stages = [
  ["repository", "Repository"], ["context", "Context"], ["planner", "Planner"],
  ["coder", "Coder"], ["tester", "Tester"], ["reviewer", "Reviewer"],
] as const;

type Props = { status: string; analysisStatus: string; contextStatus: string; planStatus: string };

export function AgentPipeline({ status, analysisStatus, contextStatus, planStatus }: Props) {
  const values: Record<string, string> = {
    repository: analysisStatus,
    context: contextStatus,
    planner: planStatus,
    coder: "not_started",
    tester: "not_started",
    reviewer: "not_started",
  };
  const active = status === "analyzing" ? "repository" : status === "planning" ? (planStatus === "running" ? "planner" : "context") : "";
  return <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
    {stages.map(([key, label]) => {
      const complete = values[key] === "completed";
      const running = key === active;
      return <div key={key} className={`flex items-center gap-3 rounded-lg border px-3 py-3 ${complete ? "border-lime-300/25 bg-lime-300/[0.06]" : running ? "border-sky-300/25 bg-sky-300/[0.06]" : "border-white/[0.07] bg-white/[0.02]"}`}>
        <span className={`grid h-6 w-6 place-items-center rounded-full border text-[10px] ${complete ? "border-lime-300/50 text-lime-200" : running ? "border-sky-300/50 text-sky-200" : "border-white/10 text-slate-600"}`}>{complete ? "✓" : running ? "·" : "○"}</span>
        <span className={`text-xs ${complete ? "text-lime-100" : running ? "text-sky-100" : "text-slate-500"}`}>{label}</span>
      </div>;
    })}
  </div>;
}
