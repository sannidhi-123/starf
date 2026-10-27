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

export async function createAlert(req: CreateAlertRequest): Promise<Alert> {
  const res = await fetch(BASE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`Failed to create alert (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getAlert(id: string): Promise<Alert> {
  const res = await fetch(`${BASE_URL}/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch alert ${id} (HTTP ${res.status})`);
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

// Re-export UI Component
export { AlertsPanel } from "./AlertsPanel";
