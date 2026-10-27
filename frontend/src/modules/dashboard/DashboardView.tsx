import React from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  Flame,
  Info,
  Layers,
  Play,
  Radar,
  Server,
  Shield,
  ShieldAlert,
  Zap,
} from "lucide-react";
import { Card } from "../../shared/components/Card";
import type {
  AlertItem,
  AlertSummary,
  DatasetItem,
  DetectionResult,
  MLModel,
  SystemHealth,
} from "../../shared/types";
import { API_BASE_URL } from "../../shared/api/client";

interface DashboardViewProps {
  health: SystemHealth | null;
  healthLoading: boolean;
  datasets: DatasetItem[];
  datasetsLoading: boolean;
  models: MLModel[];
  modelsLoading: boolean;
  alerts: AlertItem[];
  alertsSummary: AlertSummary | null;
  alertsLoading: boolean;
  recentRuns: DetectionResult[];
  onNavigate: (tab: "dashboard" | "datasets" | "detection" | "models" | "alerts") => void;
  onQuickRun: (datasetId: string) => void;
}

export function DashboardView({
  health,
  healthLoading,
  datasets,
  datasetsLoading,
  models,
  alerts,
  alertsSummary,
  alertsLoading,
  recentRuns,
  onNavigate,
  onQuickRun,
}: DashboardViewProps) {
  const isOnline = health?.status === "ok";
  const totalAlerts = alertsSummary?.total ?? alerts.length;
  const criticalCount = alertsSummary?.by_severity?.CRITICAL ?? 0;
  const highCount = alertsSummary?.by_severity?.HIGH ?? 0;
  const mediumCount = alertsSummary?.by_severity?.MEDIUM ?? 0;
  const lowCount = alertsSummary?.by_severity?.LOW ?? 0;
  const processedFrames = recentRuns.reduce((sum, run) => sum + run.total_frames, 0);
  const normalFrames = recentRuns.reduce((sum, run) => sum + run.normal_count, 0);
  const flaggedFrames = recentRuns.reduce((sum, run) => sum + run.alert_count, 0);
  const stage2 = models.find((model) => model.id === "stage2_classifier");

  return (
    <div className="space-y-8">
      {/* Hero / Phase-II Status Banner */}
      <section className="relative overflow-hidden rounded-2xl border border-cyan-500/20 bg-gradient-to-r from-slate-900 via-slate-900 to-cyan-950/40 p-6 sm:p-8 shadow-2xl">
        <div className="relative z-10 flex flex-col justify-between gap-6 md:flex-row md:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-400">
              <Zap size={13} />
              <span>Phase-II Engineering Review Active</span>
            </div>
            <h1 className="mt-3 text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Intra-Vehicular CAN-Bus Anomaly Recognition
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-300 leading-relaxed">
              STARF evaluates CAN traffic with configurable protocol rules, an explicitly reported Stage 2 runtime mode, and hybrid severity decisions.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => onQuickRun("demo_dos_attack")}
              className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2.5 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 transition-all hover:brightness-110 active:scale-95"
            >
              <Play size={16} className="fill-slate-950" />
              <span>Run DoS Detection Demo</span>
            </button>
            <button
              onClick={() => onNavigate("detection")}
              className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2.5 text-sm font-semibold text-slate-200 transition-all hover:bg-slate-750 hover:text-white"
            >
              <Radar size={16} />
              <span>Open Detection Console</span>
            </button>
          </div>
        </div>

        {/* Subtle decorative background grid pattern */}
        <div className="absolute -right-10 -top-10 h-64 w-64 rounded-full bg-cyan-500/5 blur-3xl" />
      </section>

      {/* KPI Stat Cards (Real Live Data) */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          label="Frames Processed"
          value={processedFrames.toLocaleString()}
          icon={<Database size={20} />}
          subtitle={recentRuns.length ? `Across ${recentRuns.length} recent run${recentRuns.length === 1 ? "" : "s"}` : "No detection runs yet"}
          badge={recentRuns.length ? "RECENT" : "READY"}
          badgeColor="cyan"
        />
        <Card
          label="Normal Frames"
          value={normalFrames.toLocaleString()}
          icon={<Radar size={20} />}
          subtitle="Final pipeline decisions labeled normal"
          badge={recentRuns.length ? "MEASURED" : "NO DATA"}
          badgeColor="emerald"
        />
        <Card
          label="Flagged Frames"
          value={flaggedFrames.toLocaleString()}
          icon={<Activity size={20} />}
          subtitle={recentRuns.length ? "Alerts produced by recent detection runs" : "No detection results yet"}
          badge={stage2?.status_label ?? "UNKNOWN"}
          badgeColor="amber"
        />
        <Card
          label="Persisted Alerts"
          value={alertsLoading ? "..." : totalAlerts}
          icon={<ShieldAlert size={20} />}
          subtitle={
            criticalCount > 0
              ? `${criticalCount} Critical, ${highCount} High`
              : `${highCount} High, ${mediumCount} Medium`
          }
          badge={totalAlerts > 0 ? "INSPECT" : "CLEAN"}
          badgeColor={totalAlerts > 0 ? "rose" : "slate"}
          loading={alertsLoading}
        />
      </section>

      {/* System Status & Severity Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Backend & Environment Health */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <Server size={18} className="text-cyan-400" />
              <span>System & Service Status</span>
            </h2>
            <span
              className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                isOnline
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                  : "border-rose-500/30 bg-rose-500/10 text-rose-400"
              }`}
            >
              {isOnline ? "Operational" : "Unavailable"}
            </span>
          </div>

          <div className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between items-center py-1">
              <span className="text-slate-400">Backend Endpoint</span>
              <code className="text-xs text-cyan-300 font-mono bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                {API_BASE_URL}
              </code>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-slate-400">Environment</span>
              <span className="capitalize font-medium text-slate-200">
                {health?.environment ?? "development"}
              </span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-slate-400">Integration Mode</span>
              <span className="capitalize font-medium text-slate-200">
                {health?.integration ?? "mock"}
              </span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-slate-400">Ping Latency</span>
              <span className="font-mono text-emerald-400">
                {health?.latencyMs !== undefined ? `${health.latencyMs} ms` : "Offline"}
              </span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-slate-400">Alert Database</span>
              <span className="text-slate-200 font-medium">SQLite (aiosqlite async)</span>
            </div>
          </div>

          <div className="mt-5 rounded-lg bg-slate-950 p-3 border border-slate-800/80 text-xs text-slate-400 flex items-start gap-2">
            <Info size={15} className="text-cyan-400 shrink-0 mt-0.5" />
            <span>
              Real end-to-end pipeline is connected. Running detection evaluates frames with Stage 1 rules,
              queries Stage 2 ML, arbitrates in fusion, and persists alerts to SQLite.
            </span>
          </div>
        </div>

        {/* Severity Breakdown */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <Shield size={18} className="text-cyan-400" />
              <span>Alert Severity Distribution</span>
            </h2>
            <button
              onClick={() => onNavigate("alerts")}
              className="text-xs text-cyan-400 hover:underline flex items-center gap-1"
            >
              <span>View All</span>
              <ArrowRight size={12} />
            </button>
          </div>

          <div className="mt-4 space-y-4">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-1 text-rose-400 font-semibold">
                  <Flame size={12} /> CRITICAL (85–100)
                </span>
                <span className="text-white font-mono font-bold">{criticalCount}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-rose-500 rounded-full transition-all"
                  style={{
                    width: `${totalAlerts > 0 ? (criticalCount / totalAlerts) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-1 text-orange-400 font-semibold">
                  <AlertOctagon size={12} /> HIGH (60–84)
                </span>
                <span className="text-white font-mono font-bold">{highCount}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-orange-500 rounded-full transition-all"
                  style={{
                    width: `${totalAlerts > 0 ? (highCount / totalAlerts) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-1 text-amber-400 font-semibold">
                  <AlertTriangle size={12} /> MEDIUM (30–59)
                </span>
                <span className="text-white font-mono font-bold">{mediumCount}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-amber-500 rounded-full transition-all"
                  style={{
                    width: `${totalAlerts > 0 ? (mediumCount / totalAlerts) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-1 text-slate-400 font-semibold">
                  <CheckCircle2 size={12} /> LOW (0–29)
                </span>
                <span className="text-white font-mono font-bold">{lowCount}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-slate-600 rounded-full transition-all"
                  style={{
                    width: `${totalAlerts > 0 ? (lowCount / totalAlerts) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-800 flex justify-between text-xs text-slate-400">
            <span>Total Logged Alerts:</span>
            <span className="font-mono text-cyan-400 font-semibold">{totalAlerts}</span>
          </div>
        </div>

        {/* Quick Execution & Presets */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <Layers size={18} className="text-cyan-400" />
                <span>Quick CAN Evaluation</span>
              </h2>
            </div>
            <p className="mt-3 text-xs text-slate-400">
              Run detection against repository CAN samples. Their source is identified in Dataset Explorer:
            </p>

            <div className="mt-4 space-y-2">
              {datasets.map((d) => (
                <div
                  key={d.id}
                  className="flex items-center justify-between p-2.5 rounded-lg border border-slate-800 bg-slate-950/60 hover:border-slate-700 transition-colors"
                >
                  <div>
                    <p className="text-xs font-medium text-white">{d.name}</p>
                    <p className="text-[11px] text-slate-500 font-mono">
                      {d.rows.toLocaleString()} frames &bull; {d.size_formatted ?? "CSV"}
                    </p>
                  </div>
                  <button
                    onClick={() => onQuickRun(d.id)}
                    className="flex items-center gap-1 text-xs font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 px-2.5 py-1 rounded transition-colors"
                  >
                    <Play size={11} />
                    <span>Run</span>
                  </button>
                </div>
              ))}

              {datasets.length === 0 && !datasetsLoading && (
                <div className="text-center py-6 text-xs text-slate-500">
                  No datasets found in data/samples/
                </div>
              )}
            </div>
          </div>

          <button
            onClick={() => onNavigate("datasets")}
            className="mt-4 w-full py-2 text-center text-xs font-medium text-slate-400 hover:text-white transition-colors"
          >
            Manage & Upload Datasets &rarr;
          </button>
        </div>
      </div>

      {/* Recent Alerts Table (Real Live Alerts from DB) */}
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <ShieldAlert size={20} className="text-rose-400" />
              <span>Recent Intrusion Alerts</span>
            </h2>
            <p className="text-xs text-slate-400">
              Real-time anomaly alerts persisted to SQLite database by the hybrid detection pipeline
            </p>
          </div>
          <button
            onClick={() => onNavigate("alerts")}
            className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-medium"
          >
            <span>Full Alert Console</span>
            <ArrowRight size={13} />
          </button>
        </div>

        {alertsLoading ? (
          <div className="py-12 text-center text-sm text-slate-400">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent mb-2" />
            <p>Loading real-time alerts...</p>
          </div>
        ) : alerts.length === 0 ? (
          <div className="py-12 text-center">
            <CheckCircle2 size={36} className="mx-auto text-emerald-400 mb-3" />
            <p className="text-sm font-medium text-slate-300">No intrusion alerts recorded</p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Run detection on the DoS sample dataset to evaluate CAN frames and generate alerts.
            </p>
            <button
              onClick={() => onQuickRun("demo_dos_attack")}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 px-3 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/20"
            >
              <Play size={12} />
              <span>Run Sample DoS Attack</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3 px-3">ID</th>
                  <th className="py-3 px-3">CAN ID</th>
                  <th className="py-3 px-3">Severity</th>
                  <th className="py-3 px-3">Label</th>
                  <th className="py-3 px-3">Confidence</th>
                  <th className="py-3 px-3">Arbitration Stage</th>
                  <th className="py-3 px-3">Violated Rules</th>
                  <th className="py-3 px-3">Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {alerts.slice(0, 6).map((alert) => (
                  <tr key={alert.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-3 font-mono text-slate-500">#{alert.id}</td>
                    <td className="py-3 px-3 font-mono font-semibold text-cyan-300">
                      {alert.can_id_hex}
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold tracking-wide ${
                          alert.severity_level === "CRITICAL"
                            ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                            : alert.severity_level === "HIGH"
                            ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                            : alert.severity_level === "MEDIUM"
                            ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                            : "bg-slate-800 text-slate-300"
                        }`}
                      >
                        {alert.severity_level} ({alert.severity_score})
                      </span>
                    </td>
                    <td className="py-3 px-3 font-semibold uppercase text-slate-200">
                      {alert.label}
                    </td>
                    <td className="py-3 px-3 font-mono text-slate-300">
                      {(alert.confidence * 100).toFixed(1)}%
                    </td>
                    <td className="py-3 px-3">
                      <span className="font-mono text-xs text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                        {alert.stage}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-mono text-cyan-400 font-medium">
                      {alert.rule_ids || "—"}
                    </td>
                    <td className="py-3 px-3 text-slate-300 max-w-xs truncate" title={alert.reason}>
                      {alert.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
