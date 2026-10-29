"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiRequest(runId: string, action: "approve" | "reject", comment: string) {
  const response = await fetch(`${API}/api/runs/${runId}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comment }) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? `Approval request failed (${response.status})`);
  return data;
}

export function ApprovalPanel({ runId, status, onStatus, disabled = false }: { runId: string; status: string; onStatus: (status: string) => void; disabled?: boolean }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const waiting = status === "WAITING_FOR_HUMAN_APPROVAL";
  const readableStatus = status === "READY_TO_SHIP" ? "Approved" : status === "CHANGES_REQUESTED" ? "Revisions in progress" : status === "REJECTED" ? "Declined" : waiting ? "Action needed" : status.replaceAll("_", " ").toLowerCase();
  async function submit(action: "approve" | "reject") {
    setBusy(true); setError("");
    try { const result = await apiRequest(runId, action, comment); onStatus(result.status); if (action === "approve") setComment(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Approval action failed"); }
    finally { setBusy(false); }
  }
  return <section className="rounded-2xl border border-lime-300/20 bg-gradient-to-br from-lime-300/[0.08] to-[#101615] p-5 sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="text-[10px] font-medium tracking-widest text-lime-200">YOUR DECISION</div><h2 className="mt-1 text-lg font-semibold">{status === "READY_TO_SHIP" ? "Approved and ready to ship" : status === "CHANGES_REQUESTED" ? "Your requested revisions are underway" : status === "REJECTED" ? "This run was declined" : "Review the changes before approving"}</h2></div><span aria-live="polite" className="rounded-full border border-white/10 px-3 py-1 text-[10px] capitalize text-slate-300">{readableStatus}</span></div>{status === "READY_TO_SHIP" ? <p className="mt-3 text-sm text-lime-100">Your approval is recorded. The changes have not been deployed or merged.</p> : status === "REJECTED" ? <p className="mt-3 text-sm text-rose-200">Review the feedback and start another run when you’re ready.</p> : <><label className="mt-4 block text-xs text-slate-300" htmlFor="approval-comment">Review note <span className="text-slate-500">(optional for approval; add context when requesting changes)</span></label><textarea id="approval-comment" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000} rows={3} disabled={!waiting || disabled || busy} className="mt-2 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-lime-300/50 focus:ring-2 focus:ring-lime-300/10 disabled:opacity-50" placeholder="What should the agent keep or change?"/><div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button onClick={() => void submit("reject")} disabled={!waiting || disabled || busy} className="rounded-lg border border-rose-300/30 px-4 py-3 text-sm font-semibold text-rose-200 transition hover:bg-rose-300/10 disabled:cursor-not-allowed disabled:opacity-40">Request changes</button><button onClick={() => void submit("approve")} disabled={!waiting || disabled || busy} className="rounded-lg bg-lime-300 px-5 py-3 text-sm font-bold text-[#10170d] shadow-lg shadow-lime-900/20 transition hover:bg-lime-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime-200 disabled:cursor-not-allowed disabled:opacity-40">{busy ? "Saving your decision…" : "Approve changes"}</button></div></>}{error && <p role="alert" className="mt-3 text-xs text-rose-200">{error}</p>}</section>;
}
