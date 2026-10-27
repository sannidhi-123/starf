/**
 * Centralized API client for the STARF FastAPI backend.
 * Uses configurable VITE_API_BASE_URL (defaults to http://localhost:8000/api/v1).
 */

import type {
  AlertItem,
  AlertSummary,
  DatasetDetails,
  DatasetItem,
  DetectionResult,
  DetectionRunRequest,
  MLModel,
  SystemHealth,
} from "../types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000/api/v1";

class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      let errDetail = `HTTP ${response.status} ${response.statusText}`;
      try {
        const errorData = await response.json();
        if (errorData?.detail) {
          errDetail = typeof errorData.detail === "string"
            ? errorData.detail
            : JSON.stringify(errorData.detail);
        }
      } catch {
        // Fall back to status text
      }
      throw new ApiError(errDetail, response.status);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const msg = error instanceof Error ? error.message : "Network error";
    throw new ApiError(`Backend unreachable at ${url}: ${msg}`, 0);
  }
}

// -----------------------------------------------------------------------------
// Health API
// -----------------------------------------------------------------------------

export async function getHealth(): Promise<SystemHealth> {
  const start = performance.now();
  const data = await fetchJson<{ status: string; environment: string; integration: string }>("/health");
  const latencyMs = Math.round(performance.now() - start);
  return {
    ...data,
    latencyMs,
  };
}

// -----------------------------------------------------------------------------
// Datasets API
// -----------------------------------------------------------------------------

export async function getDatasets(): Promise<DatasetItem[]> {
  const data = await fetchJson<{ items: DatasetItem[] }>("/datasets");
  return data.items ?? [];
}

export async function getDatasetDetails(datasetId: string): Promise<DatasetDetails> {
  return await fetchJson<DatasetDetails>(`/datasets/${encodeURIComponent(datasetId)}`);
}

export async function uploadDataset(filename: string, content: string): Promise<DatasetItem> {
  return await fetchJson<DatasetItem>("/datasets/upload", {
    method: "POST",
    body: JSON.stringify({ filename, content }),
  });
}

// -----------------------------------------------------------------------------
// Detection API
// -----------------------------------------------------------------------------

export async function runDetection(request: DetectionRunRequest): Promise<DetectionResult> {
  return await fetchJson<DetectionResult>("/detection/run", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getRecentDetectionRuns(): Promise<DetectionResult[]> {
  const data = await fetchJson<{ items: DetectionResult[] }>("/detection/runs");
  return data.items ?? [];
}

// -----------------------------------------------------------------------------
// Alerts API
// -----------------------------------------------------------------------------

export interface AlertFilterParams {
  run_id?: string;
  severity?: string;
  limit?: number;
}

export async function getAlerts(params?: AlertFilterParams): Promise<AlertItem[]> {
  const query = new URLSearchParams();
  if (params?.run_id) query.set("run_id", params.run_id);
  if (params?.severity && params.severity !== "ALL") query.set("severity", params.severity);
  if (params?.limit) query.set("limit", String(params.limit));

  const qs = query.toString() ? `?${query.toString()}` : "";
  const data = await fetchJson<{ items: AlertItem[] }>(`/alerts${qs}`);
  return data.items ?? [];
}

export async function getAlertsSummary(runId?: string): Promise<AlertSummary> {
  const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return await fetchJson<AlertSummary>(`/alerts/summary${qs}`);
}

export async function deleteAlert(id: number): Promise<{ deleted: boolean; id: number }> {
  return await fetchJson<{ deleted: boolean; id: number }>(`/alerts/${id}`, {
    method: "DELETE",
  });
}

export async function clearAlerts(): Promise<{ deleted: number }> {
  return await fetchJson<{ deleted: number }>("/alerts", {
    method: "DELETE",
  });
}

// -----------------------------------------------------------------------------
// Machine Learning API
// -----------------------------------------------------------------------------

export async function getMLModels(): Promise<MLModel[]> {
  const data = await fetchJson<{ items: MLModel[] }>("/ml/models");
  return data.items ?? [];
}
