"use client";

import { FormEvent, useEffect, useState } from "react";
import { ActivityLog } from "@/components/ActivityLog";
import { AgentPipeline } from "@/components/AgentPipeline";
import { PlanViewer } from "@/components/PlanViewer";
import { RepositoryInput } from "@/components/RepositoryInput";
import { RepositoryOverview } from "@/components/RepositoryOverview";
import { StatusBadge } from "@/components/StatusBadge";
import { TaskInput } from "@/components/TaskInput";
import type { Plan, RepositoryMetadata, TaskEvent } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type TaskView = {
  status: string;
  analysis_status: string;
  context_status: string;
  plan_status: string;
  repository: RepositoryMetadata | null;
  plan: Plan | null;
  events: TaskEvent[];
};

const emptyTask: TaskView = {
  status: "idle", analysis_status: "pending", context_status: "pending",
  plan_status: "pending", repository: null, plan: null, events: [],
};

async function responseBody(response: Response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`);
  return body;
}

export function Phase2Workspace() {
  const [apiStatus, setApiStatus] = useState("checking");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [taskText, setTaskText] = useState("");
  const [taskId, setTaskId] = useState("");
  const [task, setTask] = useState<TaskView>(emptyTask);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetch(`${API}/health`).then((response) => response.ok ? response.json() : Promise.reject())
      .then(() => setApiStatus("connected"))
      .catch(() => setApiStatus("offline"));
  }, []);

  useEffect(() => {
    if (!taskId || !busy) return;
    const refresh = async () => {
      try {
        const body = await responseBody(await fetch(`${API}/api/tasks/${taskId}`));
        setTask((current) => ({ ...current, ...body }));
      } catch { /* The active request reports its own error. */ }
    };
    const interval = window.setInterval(refresh, 900);
    return () => window.clearInterval(interval);
  }, [taskId, busy]);

  async function analyzeAndPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setTask(emptyTask);
    setTaskId("");
    let createdTaskId = "";
    try {
      const created = await responseBody(await fetch(`${API}/api/tasks`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository_url: repositoryUrl, task: taskText }),
      }));
      createdTaskId = created.task_id;
      setTaskId(createdTaskId);
      setTask((current) => ({ ...current, status: "created", events: [{
        id: `local-${createdTaskId}`, name: "Task created", agent: "task",
        message: "Task accepted for repository analysis.", timestamp: new Date().toISOString(),
      }] }));

      const analysis = await responseBody(await fetch(`${API}/api/tasks/${createdTaskId}/analyze`, { method: "POST" }));
      setTask((current) => ({ ...current, status: "analyzed", analysis_status: "completed", repository: analysis.repository }));

      const planned = await responseBody(await fetch(`${API}/api/tasks/${createdTaskId}/plan`, { method: "POST" }));
      setTask((current) => ({ ...current, status: "planned", context_status: "completed", plan_status: "completed", plan: planned.plan }));
      setMessage("Repository analysis and plan complete.");
      const finalTask = await responseBody(await fetch(`${API}/api/tasks/${createdTaskId}`));
      setTask((current) => ({ ...current, ...finalTask }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The planning request failed.");
      if (createdTaskId) {
        try {
          const latest = await responseBody(await fetch(`${API}/api/tasks/${createdTaskId}`));
          setTask((current) => ({ ...current, ...latest }));
        } catch { /* Keep the request error visible. */ }
      }
    } finally {
      setBusy(false);
    }
  }

  return <main className="min-h-screen bg-[#090d0c] text-slate-100">
    <header className="border-b border-white/[0.08] bg-[#0c1110]/90">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
        <a className="flex items-center gap-3 no-underline" href="/" aria-label="AgentOS delivery workspace"><span className="grid h-8 w-8 place-items-center rounded-lg bg-lime-300 font-bold text-[#10170d]">A</span><span className="font-semibold tracking-tight text-white">agent<span className="font-normal text-slate-400">os</span></span></a>
        <div className="flex items-center gap-4"><a href="/" className="text-xs text-slate-400 transition hover:text-lime-200">Delivery workspace</a><span className="hidden text-[10px] tracking-[0.18em] text-slate-500 sm:inline">REPOSITORY PLANNING</span><StatusBadge status={apiStatus}/></div>
      </div>
    </header>

    <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8 sm:py-10">
      <div className="mb-8 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div><div className="mb-3 text-[10px] font-medium tracking-[0.22em] text-lime-200">PHASE 02　/　PLAN WITH REPOSITORY CONTEXT</div><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Understand first.<br className="sm:hidden"/> Plan with evidence.</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">AgentOS inspects the repository, selects the files relevant to your task, and produces a reviewable engineering plan.</p></div>
        <StatusBadge status={task.status}/>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.75fr)]">
        <div className="space-y-5">
          <section className="rounded-2xl border border-white/[0.09] bg-[#101615] p-5 shadow-2xl shadow-black/20 sm:p-6">
            <div className="mb-5 flex items-start justify-between gap-4"><div><div className="text-[10px] tracking-[0.16em] text-slate-500">01　·　NEW PLANNING TASK</div><h2 className="mt-2 text-lg font-semibold">Repository and task</h2></div><span className="rounded-md border border-white/10 px-2 py-1 font-mono text-[9px] text-slate-500">PUBLIC GITHUB</span></div>
            <form onSubmit={analyzeAndPlan} className="space-y-4">
              <RepositoryInput value={repositoryUrl} onChange={setRepositoryUrl} disabled={busy}/>
              <TaskInput value={taskText} onChange={setTaskText} disabled={busy}/>
              <div className="flex flex-col justify-between gap-3 pt-1 sm:flex-row sm:items-center"><p className="text-[10px] leading-5 text-slate-600">The planner receives selected repository context, not the whole codebase.</p><button type="submit" disabled={busy || apiStatus !== "connected"} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-lime-300 px-5 py-3 text-xs font-semibold text-[#17200f] transition hover:bg-lime-200 disabled:cursor-not-allowed disabled:opacity-40">{busy ? <><span className="spinner"/> Working…</> : <>Analyze &amp; Plan <span>↗</span></>}</button></div>
            </form>
            {message && <div className={`mt-4 rounded-lg border px-3 py-2.5 text-xs ${task.status === "planned" ? "border-lime-300/20 bg-lime-300/[0.06] text-lime-100" : "border-amber-300/20 bg-amber-300/[0.05] text-amber-100"}`}>{message}</div>}
          </section>

          <section className="rounded-2xl border border-white/[0.09] bg-[#101615] p-5 sm:p-6">
            <div className="mb-5"><div className="text-[10px] tracking-[0.16em] text-slate-500">02　·　REPOSITORY INTELLIGENCE</div><h2 className="mt-2 text-lg font-semibold">Repository overview</h2></div>
            <RepositoryOverview repository={task.repository}/>
          </section>

          <section className="rounded-2xl border border-white/[0.09] bg-[#101615] p-5 sm:p-6">
            <div className="mb-5 flex items-center justify-between"><div><div className="text-[10px] tracking-[0.16em] text-slate-500">03　·　PLANNER OUTPUT</div><h2 className="mt-2 text-lg font-semibold">Implementation plan</h2></div>{task.plan && <span className="rounded-full border border-lime-300/25 bg-lime-300/[0.06] px-3 py-1 text-[10px] text-lime-100">SCHEMA VALIDATED</span>}</div>
            <PlanViewer plan={task.plan}/>
          </section>
        </div>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-white/[0.09] bg-[#101615] p-5 sm:p-6"><div className="mb-4"><div className="text-[10px] tracking-[0.16em] text-slate-500">PIPELINE</div><h2 className="mt-2 text-base font-semibold">Agent stages</h2></div><AgentPipeline status={task.status} analysisStatus={task.analysis_status} contextStatus={task.context_status} planStatus={task.plan_status}/><p className="mt-4 text-[10px] leading-5 text-slate-600">Coding, test execution, and review are not part of this phase.</p></section>
          <section className="rounded-2xl border border-white/[0.09] bg-[#101615] p-5 sm:p-6"><div className="mb-4 flex items-center justify-between"><div><div className="text-[10px] tracking-[0.16em] text-slate-500">ACTIVITY</div><h2 className="mt-2 text-base font-semibold">Task events</h2></div>{taskId && <code className="text-[9px] text-slate-600">{taskId.slice(0, 8)}</code>}</div><ActivityLog events={task.events}/></section>
          <section className="rounded-2xl border border-white/[0.07] bg-[#0d1211] p-4"><div className="text-[10px] font-medium tracking-[0.14em] text-slate-500">PHASE 2 BOUNDARY</div><p className="mt-2 text-xs leading-5 text-slate-500">AgentOS reads and plans against public repositories. It does not modify files or run repository commands in this phase.</p></section>
        </aside>
      </div>
      <footer className="mt-8 flex flex-wrap justify-between gap-3 border-t border-white/[0.07] pt-5 text-[9px] tracking-[0.12em] text-slate-600"><span>AGENTOS　·　DELIVERY INFRASTRUCTURE</span><span>HUMAN APPROVAL REQUIRED</span></footer>
    </div>
  </main>;
}
