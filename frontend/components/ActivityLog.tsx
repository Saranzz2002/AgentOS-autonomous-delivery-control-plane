import type { TaskEvent } from "@/lib/types";

export function ActivityLog({ events }: { events: TaskEvent[] }) {
  if (!events.length) return <p className="text-xs text-slate-600">Activity will appear here when a task starts.</p>;
  return <ol className="max-h-64 space-y-3 overflow-y-auto pr-1">
    {events.map((event) => <li key={event.id} className="flex gap-3 text-xs">
      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-lime-300" />
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-x-2 gap-y-1"><strong className="font-medium text-slate-200">{event.name}</strong><span className="font-mono text-[9px] uppercase tracking-wider text-slate-600">{event.agent}</span></div><p className="mt-1 break-words leading-5 text-slate-500">{event.message}</p></div>
    </li>)}
  </ol>;
}
