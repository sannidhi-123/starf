import type { ReactNode } from "react";

type CardProps = { label: string; value: string; icon: ReactNode };

export function Card({ label, value, icon }: CardProps) {
  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg">
      <div className="flex items-center justify-between text-cyan-400">{icon}<span className="text-xs uppercase tracking-wide text-slate-500">mock</span></div>
      <p className="mt-6 text-sm text-slate-400">{label}</p>
      <p className="mt-1 text-3xl font-semibold">{value}</p>
    </article>
  );
}
