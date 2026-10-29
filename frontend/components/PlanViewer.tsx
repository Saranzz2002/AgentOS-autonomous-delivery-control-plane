import type { Plan } from "@/lib/types";

function FileList({ title, files }: { title: string; files: Plan["files_to_modify"] }) {
  if (!files.length) return null;
  return <section><h4 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{title}</h4><ul className="space-y-2">{files.map((file) => <li key={`${title}-${file.path}`} className="rounded-lg border border-white/[0.06] bg-black/15 px-3 py-2"><code className="text-xs text-lime-100">{file.path}</code><p className="mt-1 text-xs leading-5 text-slate-500">{file.reason}</p></li>)}</ul></section>;
}

export function PlanViewer({ plan }: { plan: Plan | null }) {
  if (!plan) return <div className="grid min-h-40 place-items-center rounded-xl border border-dashed border-white/10 p-5 text-center text-xs leading-5 text-slate-600">Submit a repository and task to generate an implementation plan grounded in the project files.</div>;
  return <div className="space-y-5">
    <section><h3 className="text-base font-semibold text-slate-100">{plan.goal}</h3>{plan.assumptions.length > 0 && <p className="mt-2 text-xs leading-5 text-slate-500">Assumptions: {plan.assumptions.join(" · ")}</p>}</section>
    <div className="grid gap-5 md:grid-cols-2"><FileList title="Files to inspect" files={plan.files_to_inspect}/><FileList title="Files to modify" files={plan.files_to_modify}/><FileList title="Files to create" files={plan.files_to_create}/>
      <section><h4 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Implementation steps</h4><ol className="space-y-2">{plan.implementation_steps.map((step) => <li key={step.step} className="flex gap-3 text-xs leading-5 text-slate-300"><span className="font-mono text-lime-200">{String(step.step).padStart(2, "0")}</span><span>{step.description}</span></li>)}</ol></section>
      <section><h4 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Testing strategy</h4><ul className="list-inside list-disc space-y-1 text-xs leading-5 text-slate-400">{plan.testing_strategy.map((test) => <li key={test}>{test}</li>)}</ul></section>
      {(plan.risks.length > 0 || plan.dependencies.length > 0) && <section><h4 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Risks & dependencies</h4><ul className="space-y-1 text-xs leading-5 text-slate-400">{[...plan.risks.map((item) => `Risk: ${item}`), ...plan.dependencies.map((item) => `Dependency: ${item}`)].map((item) => <li key={item}>{item}</li>)}</ul></section>}
    </div>
  </div>;
}
