const statusStyle: Record<string, string> = {
  registered: "bg-slate-700 text-slate-200",
  training: "bg-amber-500/20 text-amber-300",
  trained: "bg-emerald-500/20 text-emerald-300",
  failed: "bg-red-500/20 text-red-300",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs ${statusStyle[status] ?? "bg-cyan-500/20 text-cyan-300"}`}>{status}</span>;
}
