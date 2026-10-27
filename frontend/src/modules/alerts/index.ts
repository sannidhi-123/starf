import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Eye,
  Filter,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

// ============================================================================
// Types
// ============================================================================

export type AlertSeverity = "low" | "medium" | "high" | "critical";
export type AlertStatus = "active" | "acknowledged" | "resolved";
export type AttackCategory =
  | "dos_flooding"
  | "fuzzy_attack"
  | "spoofing"
  | "replay_attack"
  | "malfunction"
  | "unknown";

export interface Alert {
  id: string;
  can_id?: string | null;
  timestamp: number;
  message: string;
  description: string;
  severity: AlertSeverity;
  status: AlertStatus;
  attack_category: AttackCategory;
  confidence?: number | null;
  source?: string | null;
  metadata?: Record<string, unknown>;
  evidence?: Record<string, unknown>;
  created_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
}

export interface AlertStats {
  total: number;
  active: number;
  acknowledged: number;
  resolved: number;
  by_severity: Record<string, number>;
  by_attack: Record<string, number>;
}

export interface CreateAlertRequest {
  can_id?: string;
  timestamp?: number;
  message?: string;
  description?: string;
  severity?: AlertSeverity;
  attack_category?: AttackCategory;
  confidence?: number;
  source?: string;
  metadata?: Record<string, unknown>;
  evidence?: Record<string, unknown>;
}

export interface AlertFilterParams {
  severity?: string;
  status?: string;
  attack_category?: string;
  can_id?: string;
  limit?: number;
  offset?: number;
}

// ============================================================================
// API Client Functions
// ============================================================================

const BASE_URL = "/api/v1/alerts";

export async function listAlerts(params: AlertFilterParams = {}): Promise<Alert[]> {
  const query = new URLSearchParams();
  if (params.severity) query.set("severity", params.severity);
  if (params.status) query.set("status", params.status);
  if (params.attack_category) query.set("attack_category", params.attack_category);
  if (params.can_id) query.set("can_id", params.can_id);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));

  const url = query.toString() ? `${BASE_URL}?${query.toString()}` : BASE_URL;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch alerts (HTTP ${res.status})`);
  }
  const data = await res.json();
  return Array.isArray(data) ? data : data.items ?? [];
}

export async function getAlert(id: string): Promise<Alert> {
  const res = await fetch(`${BASE_URL}/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`Failed to load alert ${id} (HTTP ${res.status})`);
  }
  return res.json();
}

export async function createAlert(payload: CreateAlertRequest): Promise<Alert> {
  const res = await fetch(BASE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to create alert (HTTP ${res.status})`);
  }
  return res.json();
}

export async function acknowledgeAlert(id: string): Promise<Alert> {
  const res = await fetch(`${BASE_URL}/${encodeURIComponent(id)}/acknowledge`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Failed to acknowledge alert ${id} (HTTP ${res.status})`);
  }
  return res.json();
}

export async function resolveAlert(id: string): Promise<Alert> {
  const res = await fetch(`${BASE_URL}/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Failed to resolve alert ${id} (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchAlertStats(): Promise<AlertStats> {
  const res = await fetch(`${BASE_URL}/stats`);
  if (!res.ok) {
    throw new Error(`Failed to fetch alert stats (HTTP ${res.status})`);
  }
  return res.json();
}

// ============================================================================
// React UI Component
// ============================================================================

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [alertList, alertStats] = await Promise.all([
        listAlerts({
          severity: severityFilter || undefined,
          status: statusFilter || undefined,
        }),
        fetchAlertStats().catch(() => null),
      ]);
      setAlerts(alertList);
      if (alertStats) setStats(alertStats);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load alerts");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [severityFilter, statusFilter]);

  async function handleAcknowledge(id: string) {
    try {
      const updated = await acknowledgeAlert(id);
      setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)));
      setActionNotice(`Alert ${id.slice(0, 8)} acknowledged.`);
      void fetchAlertStats().then(setStats).catch(() => null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  }

  async function handleResolve(id: string) {
    try {
      const updated = await resolveAlert(id);
      setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)));
      setActionNotice(`Alert ${id.slice(0, 8)} resolved.`);
      void fetchAlertStats().then(setStats).catch(() => null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  }

  const filteredAlerts = useMemo(() => {
    if (!searchQuery) return alerts;
    const q = searchQuery.toLowerCase();
    return alerts.filter(
      (a) =>
        (a.can_id && a.can_id.toLowerCase().includes(q)) ||
        a.message.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        a.attack_category.toLowerCase().includes(q)
    );
  }, [alerts, searchQuery]);

  function severityBadge(sev: AlertSeverity) {
    switch (sev) {
      case "critical":
        return <span className="rounded-full bg-rose-950/80 border border-rose-800 px-2 py-0.5 text-xs font-semibold text-rose-300">CRITICAL</span>;
      case "high":
        return <span className="rounded-full bg-amber-950/80 border border-amber-800 px-2 py-0.5 text-xs font-semibold text-amber-300">HIGH</span>;
      case "medium":
        return <span className="rounded-full bg-yellow-950/80 border border-yellow-800 px-2 py-0.5 text-xs font-semibold text-yellow-300">MEDIUM</span>;
      default:
        return <span className="rounded-full bg-cyan-950/80 border border-cyan-800 px-2 py-0.5 text-xs font-semibold text-cyan-300">LOW</span>;
    }
  }

  function statusBadge(st: AlertStatus) {
    switch (st) {
      case "resolved":
        return <span className="inline-flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 size={13} /> Resolved</span>;
      case "acknowledged":
        return <span className="inline-flex items-center gap-1 text-xs text-blue-400"><Eye size={13} /> Acknowledged</span>;
      default:
        return <span className="inline-flex items-center gap-1 text-xs text-rose-400 animate-pulse"><AlertTriangle size={13} /> Active</span>;
    }
  }

  return (
    <section className="mt-10 rounded-2xl border border-slate-800 bg-slate-900/70 p-5 sm:p-6" aria-label="Alerts & Incident Response">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-lg bg-rose-950 p-2 text-rose-400">
              <ShieldAlert size={20} />
            </span>
            <h2 className="text-xl font-bold tracking-tight text-slate-100">
              Security Alerts & Incident Feed
            </h2>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Real-time intra-vehicular CAN anomaly tracking, attack classification, and response lifecycle.
          </p>
        </div>
        <button
          onClick={() => void loadData()}
          disabled={loading}
          className="flex items-center gap-2 self-start rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* KPI Stats */}
      {stats && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
            <p className="text-xs font-medium text-slate-400">Total Incidents</p>
            <p className="mt-1 text-2xl font-bold text-slate-100">{stats.total}</p>
          </div>
          <div className="rounded-xl border border-rose-950/60 bg-rose-950/20 p-4">
            <p className="text-xs font-medium text-rose-300">Active Anomaly</p>
            <p className="mt-1 text-2xl font-bold text-rose-400">{stats.active}</p>
          </div>
          <div className="rounded-xl border border-blue-950/60 bg-blue-950/20 p-4">
            <p className="text-xs font-medium text-blue-300">Acknowledged</p>
            <p className="mt-1 text-2xl font-bold text-blue-400">{stats.acknowledged}</p>
          </div>
          <div className="rounded-xl border border-emerald-950/60 bg-emerald-950/20 p-4">
            <p className="text-xs font-medium text-emerald-300">Resolved</p>
            <p className="mt-1 text-2xl font-bold text-emerald-400">{stats.resolved}</p>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by CAN ID, message, attack..."
            className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2 pl-9 pr-3 text-xs text-slate-100 outline-none focus:border-rose-500"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Filter size={13} />
            <span>Filters:</span>
          </div>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-rose-500"
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-rose-500"
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
      </div>

      {/* Notifications / Alerts */}
      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-rose-900 bg-rose-950/40 px-4 py-3 text-xs text-rose-300">
          {error}
        </div>
      )}
      {actionNotice && (
        <div role="status" className="mb-4 rounded-lg border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-xs text-emerald-300">
          {actionNotice}
        </div>
      )}

      {/* Alerts Table */}
      {filteredAlerts.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 px-6 py-12 text-center">
          <ShieldCheck className="mx-auto mb-2 text-emerald-500/70" size={32} />
          <p className="text-sm font-medium text-slate-300">No security alerts to display</p>
          <p className="mt-1 text-xs text-slate-500">
            CAN-bus telemetry is compliant with deterministic rules and ML thresholds.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] text-left text-xs">
            <thead className="border-b border-slate-800 uppercase tracking-wider text-slate-400">
              <tr>
                <th className="pb-3 pr-4 font-semibold">Incident / CAN ID</th>
                <th className="pb-3 pr-4 font-semibold">Attack Category</th>
                <th className="pb-3 pr-4 font-semibold">Severity</th>
                <th className="pb-3 pr-4 font-semibold">Status</th>
                <th className="pb-3 pr-4 font-semibold">Confidence</th>
                <th className="pb-3 pr-4 font-semibold">Reported</th>
                <th className="pb-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {filteredAlerts.map((alert) => (
                <tr key={alert.id} className="hover:bg-slate-800/30">
                  <td className="py-3.5 pr-4">
                    <p className="font-semibold text-slate-100">{alert.message}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-cyan-400">
                      {alert.can_id ? `CAN ID: ${alert.can_id}` : "System Wide"}
                    </p>
                    <p className="mt-0.5 line-clamp-1 text-slate-400">{alert.description}</p>
                  </td>
                  <td className="py-3.5 pr-4">
                    <span className="rounded bg-slate-800 px-2 py-1 font-mono text-[11px] uppercase text-slate-300">
                      {alert.attack_category.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="py-3.5 pr-4">{severityBadge(alert.severity)}</td>
                  <td className="py-3.5 pr-4">{statusBadge(alert.status)}</td>
                  <td className="py-3.5 pr-4 font-mono text-slate-300">
                    {alert.confidence !== null && alert.confidence !== undefined
                      ? `${(alert.confidence * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                  <td className="py-3.5 pr-4 text-slate-400">
                    <span className="inline-flex items-center gap-1">
                      <Clock size={11} />
                      {new Date(alert.timestamp * 1000).toLocaleTimeString()}
                    </span>
                  </td>
                  <td className="py-3.5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {alert.status === "active" && (
                        <button
                          onClick={() => void handleAcknowledge(alert.id)}
                          className="rounded border border-blue-800 bg-blue-950/60 px-2.5 py-1 text-[11px] font-medium text-blue-300 hover:bg-blue-900"
                        >
                          Acknowledge
                        </button>
                      )}
                      {alert.status !== "resolved" && (
                        <button
                          onClick={() => void handleResolve(alert.id)}
                          className="rounded border border-emerald-800 bg-emerald-950/60 px-2.5 py-1 text-[11px] font-medium text-emerald-300 hover:bg-emerald-900"
                        >
                          Resolve
                        </button>
                      )}
                      <button
                        onClick={() => setSelectedAlert(alert)}
                        className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:bg-slate-700"
                      >
                        Inspect
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Incident Detail Modal */}
      {selectedAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-100">Incident Telemetry Details</h3>
                <p className="mt-1 font-mono text-xs text-slate-400">ID: {selectedAlert.id}</p>
              </div>
              <button
                onClick={() => setSelectedAlert(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              >
                ✕
              </button>
            </div>
            <div className="space-y-3 text-xs text-slate-300">
              <div>
                <span className="font-semibold text-slate-400">Summary:</span>
                <p className="mt-1 text-sm text-slate-100">{selectedAlert.message}</p>
              </div>
              <div>
                <span className="font-semibold text-slate-400">Detailed Description:</span>
                <p className="mt-1 text-slate-200">{selectedAlert.description}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800">
                <div>
                  <span className="text-slate-400">CAN Arbitration ID:</span>
                  <p className="font-mono text-cyan-400">{selectedAlert.can_id || "N/A"}</p>
                </div>
                <div>
                  <span className="text-slate-400">Attack Classification:</span>
                  <p className="font-mono uppercase">{selectedAlert.attack_category}</p>
                </div>
                <div>
                  <span className="text-slate-400">Severity:</span>
                  <div className="mt-0.5">{severityBadge(selectedAlert.severity)}</div>
                </div>
                <div>
                  <span className="text-slate-400">Status:</span>
                  <div className="mt-0.5">{statusBadge(selectedAlert.status)}</div>
                </div>
              </div>
              {selectedAlert.evidence && Object.keys(selectedAlert.evidence).length > 0 && (
                <div className="pt-2 border-t border-slate-800">
                  <span className="font-semibold text-slate-400">Telemetry Evidence:</span>
                  <pre className="mt-1.5 max-h-36 overflow-auto rounded-lg bg-slate-950 p-2.5 font-mono text-[11px] text-cyan-300">
                    {JSON.stringify(selectedAlert.evidence, null, 2)}
                  </pre>
                </div>
              )}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setSelectedAlert(null)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
