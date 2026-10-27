import type { ReactNode } from "react";

interface CardProps {
  label: string;
  value: string | number;
  icon: ReactNode;
  subtitle?: string;
  badge?: string;
  badgeColor?: "cyan" | "emerald" | "amber" | "rose" | "slate";
  loading?: boolean;
  className?: string;
}

export function Card({
  label,
  value,
  icon,
  subtitle,
  badge,
  badgeColor = "cyan",
  loading = false,
  className = "",
}: CardProps) {
  const badgeColors = {
    cyan: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    amber: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    rose: "bg-rose-500/10 text-rose-400 border-rose-500/30",
    slate: "bg-slate-800 text-slate-400 border-slate-700",
  };

  return (
    <article
      className={`relative overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/70 p-5 shadow-lg backdrop-blur-sm transition-all hover:border-slate-700/80 ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800/80 text-cyan-400">
          {icon}
        </div>
        {badge && (
          <span
            className={`rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-wide ${badgeColors[badgeColor]}`}
          >
            {badge}
          </span>
        )}
      </div>

      <div className="mt-4">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</p>
        <p className="mt-1 text-3xl font-bold tracking-tight text-white">
          {loading ? (
            <span className="inline-block h-8 w-20 animate-pulse rounded bg-slate-800" />
          ) : (
            value
          )}
        </p>
        {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
      </div>
    </article>
  );
}
