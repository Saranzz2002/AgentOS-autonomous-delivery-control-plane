type Props = { value: string; onChange: (value: string) => void; disabled?: boolean };

export function RepositoryInput({ value, onChange, disabled }: Props) {
  return <label className="block space-y-2">
    <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">GitHub repository</span>
    <input
      className="w-full rounded-lg border border-white/10 bg-[#080d0c] px-4 py-3 font-mono text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-lime-300/60 focus:ring-2 focus:ring-lime-300/10 disabled:opacity-50"
      type="url" required disabled={disabled} value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder="https://github.com/owner/repository"
    />
  </label>;
}
