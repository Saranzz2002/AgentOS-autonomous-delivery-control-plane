type Props = { value: string; onChange: (value: string) => void; disabled?: boolean };

export function TaskInput({ value, onChange, disabled }: Props) {
  return <label className="block space-y-2">
    <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">Engineering task</span>
    <textarea
      className="min-h-28 w-full resize-y rounded-lg border border-white/10 bg-[#080d0c] px-4 py-3 text-sm leading-6 text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-lime-300/60 focus:ring-2 focus:ring-lime-300/10 disabled:opacity-50"
      required minLength={8} maxLength={4000} disabled={disabled} value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder="Add a health-check endpoint and create tests for it."
    />
    <span className="block text-right text-[10px] text-slate-600">{value.length}/4000</span>
  </label>;
}
