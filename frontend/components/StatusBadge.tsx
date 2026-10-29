export function StatusBadge({ status }: { status: string }) {
  const active = ["checking", "running", "analyzing", "planning"].includes(status);
  const good = ["connected", "completed", "analyzed", "planned"].includes(status);
  return <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${good ? "border-lime-400/30 bg-lime-300/10 text-lime-200" : active ? "border-sky-300/30 bg-sky-300/10 text-sky-200" : "border-white/10 bg-white/[0.04] text-slate-400"}`}>
    <span className={`h-1.5 w-1.5 rounded-full ${good ? "bg-lime-300" : active ? "animate-pulse bg-sky-300" : "bg-slate-500"}`} />
    {status.replaceAll("_", " ")}
  </span>;
}
