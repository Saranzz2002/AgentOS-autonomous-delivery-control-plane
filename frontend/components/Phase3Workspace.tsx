"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Event = { timestamp: string; type: string; message: string; iteration: number };
type Run = { run_id: string; status: string; iteration: number; test_status: string; events: Event[]; plan?: { goal: string }; test_result?: { summary: string; stdout: string; stderr: string; exit_code: number | null; duration: number }; error?: string };

async function body(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? `Request failed (${response.status})`);
  return data;
}

export function Phase3Workspace() {
  const [repository, setRepository] = useState("");
  const [task, setTask] = useState("");
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [diff, setDiff] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!runId || !busy) return;
    let active = true;
    const poll = async () => {
      try {
        const next = await body(await fetch(`${API}/api/runs/${runId}`));
        if (!active) return;
        setRun(next);
        if (["completed", "failed"].includes(next.status)) {
          const changes = await body(await fetch(`${API}/api/runs/${runId}/diff`));
          setDiff(changes.diff ?? "");
          setBusy(false);
        }
      } catch (e) {
        if (active) { setError(e instanceof Error ? e.message : "Run status request failed"); setBusy(false); }
      }
    };
    void poll();
    const timer = window.setInterval(poll, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [runId, busy]);

  async function start(event: FormEvent) {
    event.preventDefault(); setError(""); setDiff(""); setRun(null); setBusy(true);
    try {
      const created = await body(await fetch(`${API}/api/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository_url: repository, task }) }));
      setRunId(created.run_id);
      setRun({ run_id: created.run_id, status: created.status, iteration: 0, test_status: "pending", events: [] });
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start the run"); setBusy(false); }
  }

  const stages = [
    ["repository", "Repository"], ["context", "Context"], ["planner", "Plan"],
    ["coder", "Code"], ["changes", "Apply changes"], ["tests", "Tests"],
    ["debugger", "Debug"], ["fix", "Fix"],
  ];
  const latest = (prefix: string) => [...(run?.events ?? [])].reverse().find((event) => event.type.startsWith(prefix));
  const order = (prefix: string) => latest(prefix) ? "✓" : (run?.status === prefix ? "●" : "○");

  return <main className="min-h-screen bg-[#090d0c] text-slate-100">
    <header className="border-b border-white/[0.08] bg-[#0c1110]/90"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><span className="font-semibold tracking-tight">AGENTOS <span className="ml-2 text-[10px] font-normal tracking-[0.16em] text-lime-200">PHASE 03 / AUTONOMOUS DELIVERY</span></span><div className="flex items-center gap-4"><a className="text-xs text-slate-400 hover:text-lime-200" href="/phase2">Phase 2 planner</a><span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">{run?.status ?? "ready"}</span></div></div></header>
    <div className="mx-auto max-w-6xl space-y-5 px-5 py-8">
      <section className="rounded-2xl border border-white/10 bg-[#101615] p-5 sm:p-7"><h1 className="text-3xl font-semibold">Plan, code, test, repair.</h1><p className="mt-2 text-sm text-slate-400">AgentOS applies validated file changes and runs repository tests in a restricted Docker container.</p>
        <form onSubmit={start} className="mt-6 grid gap-3"><input required type="url" placeholder="https://github.com/owner/repository" value={repository} onChange={(e) => setRepository(e.target.value)} disabled={busy} className="rounded-lg border border-white/10 bg-black/20 px-4 py-3 text-sm"/><textarea required rows={3} placeholder="Add a /health endpoint and tests" value={task} onChange={(e) => setTask(e.target.value)} disabled={busy} className="rounded-lg border border-white/10 bg-black/20 px-4 py-3 text-sm"/><button disabled={busy} className="justify-self-start rounded-lg bg-lime-300 px-5 py-3 text-sm font-semibold text-slate-900 disabled:opacity-50">{busy ? "Run in progress…" : "Start autonomous run"}</button></form>
        {error && <p className="mt-4 rounded border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">{error}</p>}
      </section>
      {run && <>
        <section className="rounded-2xl border border-white/10 bg-[#101615] p-5"><div className="mb-4 flex justify-between"><div><div className="text-[10px] tracking-widest text-slate-500">WORKFLOW</div><h2 className="mt-1 font-semibold">{run.plan?.goal ?? task}</h2></div><div className="text-right text-xs text-slate-400">Attempt {run.iteration || (busy ? 1 : 0)} / 3<br/>Tests: {run.test_status}</div></div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{stages.map(([prefix, label]) => <div key={prefix} className={`rounded-lg border p-3 text-sm ${latest(prefix) ? "border-lime-300/30 bg-lime-300/[0.05] text-lime-100" : "border-white/[0.08] text-slate-400"}`}><span className="mr-2">{order(prefix)}</span>{label}</div>)}</div>
          <div className="mt-5 space-y-2">{[1, 2, 3].map((attempt) => { const testEvent = [...run.events].reverse().find((event) => event.type.startsWith("tests.") && event.iteration === attempt); const debugEvent = run.events.find((event) => event.type === "debugger.completed" && event.iteration === attempt); return <div key={attempt} className="flex flex-wrap items-center gap-2 rounded-lg bg-black/20 px-3 py-2 text-xs"><b className="text-slate-300">Attempt {attempt}</b><span className={testEvent?.type === "tests.passed" ? "text-lime-200" : testEvent ? "text-rose-300" : "text-slate-600"}>{testEvent ? `${testEvent.type === "tests.passed" ? "✓" : "×"} ${testEvent.message}` : attempt === run.iteration && busy ? "● In progress" : "○ Waiting"}</span>{debugEvent && <span className="text-amber-200">→ Debugger: {debugEvent.message}</span>}</div>; })}</div>
        </section>
        <div className="grid gap-5 lg:grid-cols-2">
          <section className="rounded-2xl border border-white/10 bg-[#101615] p-5"><h2 className="mb-3 font-semibold">Test results</h2>{run.test_result ? <><p className="text-sm text-slate-300">{run.test_result.summary} · exit {run.test_result.exit_code ?? "—"} · {run.test_result.duration}s</p><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-3 text-xs text-slate-300">{[run.test_result.stdout, run.test_result.stderr].filter(Boolean).join("\n") || "No output"}</pre></> : <p className="text-sm text-slate-500">Waiting for actual sandbox test output.</p>}{run.error && <p className="mt-3 text-xs text-amber-200">{run.error}</p>}</section>
          <section className="rounded-2xl border border-white/10 bg-[#101615] p-5"><h2 className="mb-3 font-semibold">Agent activity</h2><div className="max-h-96 space-y-2 overflow-auto">{run.events.map((event, i) => <div key={`${event.timestamp}-${i}`} className="border-l border-lime-300/30 pl-3"><div className="text-[10px] text-slate-500">{new Date(event.timestamp).toLocaleTimeString()} · attempt {event.iteration || "—"}</div><div className="text-xs text-slate-200">{event.message}</div></div>)}</div></section>
        </div>
        <section className="rounded-2xl border border-white/10 bg-[#101615] p-5"><h2 className="mb-3 font-semibold">Git diff</h2><pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap text-xs text-lime-100">{diff || (busy ? "Changes will appear as the run progresses." : "No diff available.")}</pre></section>
      </>}
      <footer className="border-t border-white/[0.08] pt-4 text-xs text-slate-500">Code execution uses Docker with networking disabled, resource limits, and only the repository workspace mounted.</footer>
    </div>
  </main>;
}
