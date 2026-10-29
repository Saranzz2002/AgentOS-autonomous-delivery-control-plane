import type { RepositoryMetadata } from "@/lib/types";

export function RepositoryOverview({ repository }: { repository: RepositoryMetadata | null }) {
  if (!repository) return <div className="rounded-xl border border-dashed border-white/10 p-5 text-xs text-slate-600">Repository facts appear after analysis.</div>;
  return <div className="space-y-4">
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {[["LANGUAGE", repository.language], ["FRAMEWORK", repository.framework], ["PACKAGE MANAGER", repository.package_manager], ["TEST FRAMEWORK", repository.test_framework]].map(([label, value]) => <div key={label} className="rounded-lg border border-white/[0.07] bg-black/20 p-3"><div className="text-[9px] tracking-[0.14em] text-slate-600">{label}</div><div className="mt-1 truncate text-sm text-slate-200">{value}</div></div>)}
    </div>
    <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-500"><span><b className="text-slate-200">{repository.source_file_count}</b> source files</span><span><b className="text-slate-200">{repository.test_file_count}</b> test files</span><span>branch <code className="text-slate-300">{repository.branch || "unknown"}</code></span><span>commit <code className="text-slate-300">{repository.commit_sha?.slice(0, 8) || "unknown"}</code></span></div>
    <details className="group rounded-lg border border-white/[0.07] bg-black/15">
      <summary className="cursor-pointer list-none px-3 py-2.5 text-xs text-slate-400">Repository tree <span className="float-right font-mono text-slate-600">{repository.tree.length} files　⌄</span></summary>
      <div className="max-h-56 overflow-auto border-t border-white/[0.06] p-3 font-mono text-[10px] leading-5 text-slate-500">{repository.tree.map((path) => <div key={path} className="truncate">{path}</div>)}</div>
    </details>
  </div>;
}
