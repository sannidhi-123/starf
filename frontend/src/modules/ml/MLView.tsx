import React from "react";
import {
  Activity,
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  Clock,
  Code2,
  Cpu,
  GitBranch,
  Info,
  Layers,
  RefreshCw,
  Scale,
  Shield,
  ShieldAlert,
  Zap,
} from "lucide-react";
import type { MLModel } from "../../shared/types";

interface MLViewProps {
  models: MLModel[];
  loading: boolean;
  onRefresh: () => void;
}

export function MLView({ models, loading, onRefresh }: MLViewProps) {
  const stage2 = models.find((model) => model.id === "stage2_classifier");
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <Activity className="text-cyan-400" />
            <span>Hybrid Detection Architecture & Pipeline Models</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Runtime model status, active rule checks, and decision fusion details
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-850 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={14} className={loading ? "animate-spin text-cyan-400" : ""} />
          <span>Refresh Metadata</span>
        </button>
      </div>

      {/* Honest Status Callout */}
      <div className={`rounded-xl border p-5 flex items-start gap-3 ${stage2?.status === "active" ? "border-emerald-500/30 bg-emerald-500/10" : "border-amber-500/30 bg-amber-500/10"}`}>
        <Info size={20} className={`${stage2?.status === "active" ? "text-emerald-400" : "text-amber-400"} shrink-0 mt-0.5`} />
        <div className="text-xs text-slate-300 space-y-1">
          <p className="font-semibold text-white">
            Stage 2 runtime: {stage2?.status_label ?? "status unavailable"}
          </p>
          <p>
            {stage2?.description ?? "Connect the backend to read the active model runtime state."}
          </p>
          {stage2?.metrics?.load_error && <p className="text-rose-300">Model load error: {stage2.metrics.load_error}</p>}
          <p>Stage 1 metrics in the repository report have no attack examples in validation, so they do not establish attack recall.</p>
        </div>
      </div>

      {/* Architecture Pipeline Flow Diagram */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
        <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <GitBranch size={18} className="text-cyan-400" />
          <span>End-to-End Pipeline Telemetry Flow</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-center">
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/80">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Step 1</span>
            <h3 className="text-xs font-bold text-cyan-400 mt-1">Causal Streaming Features</h3>
            <p className="text-[11px] text-slate-400 mt-1">
              Causal streaming features include Δt, 50ms bus rate, per-ID frame count, payload repetition, and Hamming distance.
            </p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/80">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Step 2</span>
            <h3 className="text-xs font-bold text-cyan-400 mt-1">Stage 1 Deterministic Rules</h3>
            <p className="text-[11px] text-slate-400 mt-1">
              Evaluates configured R1–R7 deterministic checks. Threshold performance depends on representative validation data.
            </p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/80">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Step 3</span>
            <h3 className="text-xs font-bold text-amber-400 mt-1">Stage 2 Statistical ML</h3>
            <p className="text-[11px] text-slate-400 mt-1">
              Multi-class inference over suspicious frames (DoS, Fuzzy, Spoofing, Normal).
            </p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/80">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Step 4</span>
            <h3 className="text-xs font-bold text-purple-400 mt-1">Stage 3 Hybrid Fusion</h3>
            <p className="text-[11px] text-slate-400 mt-1">
              7-row arbitration matrix maps dual confirmations to 0–100 severity alerts in SQLite.
            </p>
          </div>
        </div>
      </div>

      {/* Model Cards Grid */}
      <div className="space-y-6">
        {loading ? (
          <div className="py-16 text-center text-slate-400">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent mb-2" />
            <p className="text-sm">Loading model specifications...</p>
          </div>
        ) : (
          models.map((m) => (
            <div
              key={m.id}
              className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm space-y-5"
            >
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-slate-800 gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-cyan-500/10 px-2 py-0.5 text-xs font-mono font-bold text-cyan-400 border border-cyan-500/30">
                      {m.stage}
                    </span>
                    <h2 className="text-lg font-bold text-white">{m.name}</h2>
                    <span className="font-mono text-xs text-slate-500">v{m.version}</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{m.description}</p>
                </div>

                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold border ${
                    m.status === "active"
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-400"
                  }`}
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      m.status === "active" ? "bg-emerald-400" : "bg-amber-400"
                    }`}
                  />
                  <span>{m.status_label}</span>
                </span>
              </div>

              {/* Stage 1 Rules Display */}
              {m.rules && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
                    <Shield size={14} className="text-cyan-400" />
                    <span>Calibrated Deterministic Rules (R1–R7)</span>
                  </h3>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {m.rules.map((r) => (
                      <div
                        key={r.id}
                        className="p-3 rounded-lg border border-slate-800 bg-slate-950/60 flex items-center justify-between"
                      >
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono text-xs font-bold text-cyan-400">{r.id}</span>
                            <span className="text-xs text-slate-300 font-medium">{r.name}</span>
                          </div>
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            Weight: {r.weight} &bull; Classification: {r.level}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Stage 2 Classes & Features */}
              {m.classes && (
                <div className="grid gap-6 md:grid-cols-2">
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                      Multi-Class Target Labels
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {m.classes.map((cls) => (
                        <span
                          key={cls}
                          className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-1 text-xs font-mono font-semibold uppercase text-cyan-300"
                        >
                          {cls}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                      Causal Feature Vector
                    </h3>
                    <div className="space-y-1">
                      {m.features?.map((f, idx) => (
                        <div key={idx} className="text-xs font-mono text-slate-400 flex items-center gap-2">
                          <span className="text-cyan-500">&bull;</span>
                          <span>{f}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Stage 3 Severity Levels */}
              {m.severity_levels && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-2">
                    <Scale size={14} className="text-cyan-400" />
                    <span>Dynamic Severity Grading & Arbitration (0–100 Scale)</span>
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {m.severity_levels.map((s) => (
                      <div
                        key={s.level}
                        className="p-3 rounded-lg border border-slate-800 bg-slate-950/60"
                      >
                        <div className="flex items-center justify-between">
                          <span
                            className={`text-xs font-bold ${
                              s.level === "CRITICAL"
                                ? "text-rose-400"
                                : s.level === "HIGH"
                                ? "text-orange-400"
                                : s.level === "MEDIUM"
                                ? "text-amber-400"
                                : "text-slate-400"
                            }`}
                          >
                            {s.level}
                          </span>
                          <span className="font-mono text-[11px] text-slate-400">Score: {s.range}</span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-2">{s.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Metrics Footer */}
              {m.metrics && (
                <div className="pt-3 border-t border-slate-800 flex flex-wrap gap-6 text-xs font-mono text-slate-400">
                  {Object.entries(m.metrics).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-1.5">
                      <span className="text-slate-500 uppercase">{k.replace("_", " ")}:</span>
                      <span className="text-cyan-300 font-semibold">{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
