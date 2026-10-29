"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { DiffViewer } from "@/components/DiffViewer";
import { Review, ReviewSummary } from "@/components/ReviewSummary";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Event = { timestamp: string; type: string; message: string; iteration: number };
type Diff = { files_changed: string[]; insertions: number; deletions: number; diff: string };
type Repository = { name?: string; language?: string; framework?: string; test_framework?: string; package_manager?: string; entry_point?: string | null; source_file_count?: number };
type PlanItem = { path: string; reason: string };
type Plan = { goal?: string; assumptions?: string[]; files_to_inspect?: PlanItem[]; files_to_modify?: PlanItem[]; files_to_create?: PlanItem[]; implementation_steps?: { step: number; description: string }[]; testing_strategy?: string[]; risks?: string[]; dependencies?: string[] };
type Run = { run_id: string; status: string; iteration: number; review_iteration: number; human_revision_cycles: number; test_status: string; events: Event[]; review: Review | null; repository?: Repository | null; repository_tree?: string[]; relevant_files?: string[]; plan?: Plan | null; test_result?: { summary: string; stdout: string; stderr: string; exit_code: number | null; duration: number } | null; error?: string | null; approval?: { status: string; comment: string; updated_at: string } | null };

async function body(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? `Request failed (${response.status})`);
  return data;
}

const stoppedStates = new Set(["WAITING_FOR_HUMAN_APPROVAL", "READY_TO_SHIP", "REJECTED", "FAILED"]);
const stages: [string, string][] = [["repository", "Inspect code"], ["context", "Find context"], ["planner", "Plan work"], ["coder", "Write code"], ["changes", "Apply patch"], ["tests", "Run tests"], ["debugger", "Diagnose"], ["fix", "Refine"], ["review", "Code review"], ["approval", "Your decision"], ["ship", "Ready to ship"]];

function statusLabel(status?: string) {
  if (!status) return "Ready to start";
  return ({ READY: "Ready to start", WAITING_FOR_HUMAN_APPROVAL: "Your review", READY_TO_SHIP: "Approved to ship", CHANGES_REQUESTED: "Revisions in progress", REJECTED: "Changes declined", FAILED: "Run failed" } as Record<string, string>)[status] ?? status.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase());
}

export function Phase4Workspace() {
  const [repository, setRepository] = useState("");
  const [task, setTask] = useState("");
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!runId || !busy) return;
    let active = true;
    const poll = async () => {
      try {
        const next: Run = await body(await fetch(`${API}/api/runs/${runId}`));
        if (!active) return;
        setRun(next);
        if (stoppedStates.has(next.status)) {
          const changes: Diff = await body(await fetch(`${API}/api/runs/${runId}/diff`));
          setDiff(changes);
          setBusy(false);
        }
      } catch (e) {
        if (active) { setError(e instanceof Error ? e.message : "Run status request failed"); setBusy(false); }
      }
    };
    void poll();
    const timer = window.setInterval(poll, 1200);
    return () => { active = false; window.clearInterval(timer); };
  }, [runId, busy]);

  async function start(event: FormEvent) {
    event.preventDefault(); setError(""); setDiff(null); setRun(null); setBusy(true);
    try {
      const created = await body(await fetch(`${API}/api/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository_url: repository, task }) }));
      setRunId(created.run_id);
      setRun({ run_id: created.run_id, status: created.status, iteration: 0, review_iteration: 0, human_revision_cycles: 0, test_status: "pending", events: [], review: null });
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start the run"); setBusy(false); }
  }

  const latest = (prefix: string) => [...(run?.events ?? [])].reverse().find((event) => event.type.startsWith(prefix));
  const done = (prefix: string) => Boolean(latest(prefix));
  function updateStatus(status: string) {
    setRun((current) => current ? { ...current, status } : current);
    if (status === "CHANGES_REQUESTED") setBusy(true);
  }

  return <main className="min-h-screen bg-[#090d0c] text-slate-100">
    <header className="sticky top-0 z-10 border-b border-white/[0.08] bg-[#0c1110]/95 backdrop-blur"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><a href="/" aria-label="AgentOS home" className="font-semibold tracking-tight">AGENTOS <span className="ml-2 hidden text-[10px] font-normal tracking-[0.16em] text-lime-200 sm:inline">DELIVERY WORKSPACE</span></a><div className="flex items-center gap-4"><a className="text-xs text-slate-400 transition hover:text-lime-200" href="/phase2">Planning workspace</a><span aria-live="polite" className="rounded-full border border-white/10 px-3 py-1 text-[10px] text-slate-300">{statusLabel(run?.status)}</span></div></div></header>
    <div className="mx-auto max-w-6xl space-y-5 px-5 py-8">
      <section className="rounded-2xl border border-white/10 bg-[#101615] p-5 shadow-2xl shadow-black/10 sm:p-8"><div className="text-[10px] font-medium tracking-[0.2em] text-lime-200">SOFTWARE DELIVERY · HUMAN CONTROL</div><h1 className="mt-3 max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl">From repository to reviewed changes, with you in control.</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Describe the work and AgentOS will inspect the codebase, make a patch, run sandboxed tests, and prepare an independent review. You choose whether it is approved to ship.</p>
        <form onSubmit={start} className="mt-7 grid gap-4"><div className="grid gap-2"><label htmlFor="repository-url" className="text-xs font-medium text-slate-300">Repository URL</label><input id="repository-url" required type="url" placeholder="https://github.com/owner/repository" value={repository} onChange={(e) => setRepository(e.target.value)} disabled={busy} className="rounded-lg border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition placeholder:text-slate-600 focus:border-lime-300/60 focus:ring-2 focus:ring-lime-300/10"/><span className="text-xs text-slate-500">Use a repository URL that the AgentOS backend can access.</span></div><div className="grid gap-2"><label htmlFor="task-description" className="text-xs font-medium text-slate-300">What should change?</label><textarea id="task-description" required rows={3} placeholder="For example: Add a /health endpoint and tests for success and not-found responses." value={task} onChange={(e) => setTask(e.target.value)} disabled={busy} className="resize-y rounded-lg border border-white/10 bg-black/20 px-4 py-3 text-sm leading-6 outline-none transition placeholder:text-slate-600 focus:border-lime-300/60 focus:ring-2 focus:ring-lime-300/10"/></div><div className="flex flex-wrap items-center gap-4"><button disabled={busy} className="rounded-lg bg-lime-300 px-5 py-3 text-sm font-semibold text-slate-900 transition hover:bg-lime-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime-200 disabled:cursor-wait disabled:opacity-50">{busy ? "Working on your request…" : "Create delivery run"}</button><span className="text-xs text-slate-500">Changes stay in the workspace until you approve them.</span></div></form>
        {error && <p className="mt-4 rounded border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">{error}</p>}
      </section>
      {run && <>
        <section className="rounded-2xl border border-white/10 bg-[#101615] p-5 sm:p-6"><div className="mb-5 flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="text-[10px] font-medium tracking-widest text-slate-500">DELIVERY PROGRESS</div><h2 className="mt-2 max-w-3xl break-words text-base font-semibold leading-6">{run.review?.summary ?? task}</h2></div><div className="flex gap-4 text-xs text-slate-400"><span>Test run <b className="font-medium text-slate-200">{run.iteration}/3</b></span><span>Review <b className="font-medium text-slate-200">{run.review_iteration}/2</b></span></div></div><div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">{stages.map(([prefix, label]) => <div key={prefix} className={`rounded-lg border p-3 text-xs ${done(prefix) ? "border-lime-300/30 bg-lime-300/[0.05] text-lime-100" : "border-white/[0.08] text-slate-400"}`}><span className="mr-2" aria-hidden="true">{done(prefix) ? "✓" : busy && run.status === prefix.toUpperCase() ? "●" : "○"}</span>{label}</div>)}</div><div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-white/[0.06] pt-4 text-xs text-slate-500"><span>Run status: <b className="font-medium text-slate-300">{statusLabel(run.status)}</b></span><span>Test status: <b className="font-medium text-slate-300">{statusLabel(run.test_status)}</b></span><span>Requested revision rounds: {run.human_revision_cycles}/2</span></div></section>
        {(run.repository || run.plan) && <section className="grid gap-5 rounded-2xl border border-white/10 bg-[#101615] p-5 lg:grid-cols-2">
          <div><div className="text-[10px] tracking-widest text-slate-500">REPOSITORY INTELLIGENCE</div><h2 className="mt-1 font-semibold">{run.repository?.name ?? "Repository"}</h2><div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-300">{[run.repository?.language, run.repository?.framework, run.repository?.test_framework, run.repository?.package_manager].filter(Boolean).map((item) => <span key={item} className="rounded-full border border-white/10 px-2 py-1">{item}</span>)}</div><h3 className="mt-4 text-xs font-semibold">Repository map</h3><div className="mt-2 max-h-36 overflow-auto rounded-lg bg-black/25 p-3 font-mono text-[11px] text-slate-400">{run.repository_tree?.length ? run.repository_tree.slice(0, 40).map((path) => <div key={path}>{path}</div>) : "Repository map is being prepared…"}</div><h3 className="mt-4 text-xs font-semibold">Relevant context files</h3><div className="mt-2 flex flex-wrap gap-2">{run.relevant_files?.length ? run.relevant_files.map((path) => <span key={path} className="rounded border border-lime-300/20 px-2 py-1 font-mono text-[10px] text-lime-100">{path}</span>) : <span className="text-xs text-slate-500">No source snippets selected for this repository.</span>}</div></div>
          <div><div className="text-[10px] tracking-widest text-slate-500">IMPLEMENTATION PLAN</div><h2 className="mt-1 font-semibold">{run.plan?.goal ?? "Plan is being generated…"}</h2><ol className="mt-3 list-decimal space-y-2 pl-5 text-xs text-slate-300">{run.plan?.implementation_steps?.map((step) => <li key={step.step}>{step.description}</li>)}</ol>{Boolean(run.plan?.testing_strategy?.length) && <><h3 className="mt-4 text-xs font-semibold">Testing strategy</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-400">{run.plan?.testing_strategy?.map((item, index) => <li key={index}>{item}</li>)}</ul></>}</div>
        </section>}
        {run.test_result && <section className="rounded-2xl border border-white/10 bg-[#101615] p-5"><div className="flex flex-wrap items-start justify-between gap-2"><div><div className="text-[10px] font-medium tracking-widest text-slate-500">SANDBOXED VERIFICATION</div><h2 className="mt-1 font-semibold">Test results</h2></div><span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">{run.test_result.exit_code === 0 ? "Passed" : "Needs attention"}</span></div><p className="mt-3 text-sm text-slate-300">{run.test_result.summary} <span className="text-slate-500">· exit code {run.test_result.exit_code ?? "—"} · {run.test_result.duration}s</span></p><pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-white/[0.06] bg-black/30 p-3 text-xs leading-5 text-slate-300">{[run.test_result.stdout, run.test_result.stderr].filter(Boolean).join("\n") || "The test run returned no console output."}</pre></section>}
        {run.review && <ReviewSummary review={run.review}/>}
        {run.review && <ApprovalPanel runId={run.run_id} status={run.status} onStatus={updateStatus} disabled={busy && run.status !== "WAITING_FOR_HUMAN_APPROVAL"}/>}
        {run.error && <p className="rounded-lg border border-rose-300/20 bg-rose-300/[0.06] p-3 text-sm text-rose-100">{run.error}</p>}
        <DiffViewer diff={diff?.diff ?? ""} summary={diff ?? undefined}/>
        <section className="rounded-2xl border border-white/10 bg-[#101615] p-5"><div className="flex items-center justify-between"><div><div className="text-[10px] font-medium tracking-widest text-slate-500">RUN LOG</div><h2 className="mt-1 font-semibold">Activity</h2></div><span className="text-xs text-slate-500">{run.events.length} updates</span></div><div className="mt-4 max-h-96 space-y-3 overflow-auto">{run.events.length ? run.events.map((event, i) => <div key={`${event.timestamp}-${i}`} className="border-l border-lime-300/30 pl-3"><div className="text-[10px] text-slate-500">{new Date(event.timestamp).toLocaleTimeString()} · cycle {event.iteration || "—"}</div><div className="mt-1 text-xs leading-5 text-slate-200">{event.message}</div></div>) : <p className="text-sm text-slate-500">Updates will appear here as the delivery run progresses.</p>}</div></section>
      </>}
      <footer className="border-t border-white/[0.08] pt-4 text-xs leading-5 text-slate-500">Tests run in an isolated Docker environment. A person must approve reviewed changes before they are marked ready to ship. AgentOS does not deploy or merge code.</footer>
    </div>
  </main>;
}
