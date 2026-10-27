// Module-local client: frontend/src/shared/ is shared and only exposes getHealth().
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type ModelStatus = "registered" | "training" | "trained" | "failed";

export type Hyperparameters = {
  epochs: number;
  learning_rate: number;
  l2: number;
  threshold: number;
  test_split: number;
  seed: number;
};

export type ModelSummary = {
  id: string;
  name: string;
  architecture?: string;
  description?: string;
  status: ModelStatus | string; // integration models may report e.g. "available"
  hyperparameters?: Hyperparameters;
  data_source?: string | null;
  error?: string | null;
  trained_at?: string | null;
  has_metrics?: boolean;
};

export type Metrics = {
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  roc_auc: number | null;
  confusion_matrix: { tp: number; fp: number; tn: number; fn: number };
  train_samples: number;
  test_samples: number;
  final_loss: number;
};

export type CanFrame = {
  timestamp: number;
  can_id: number;
  dlc: number;
  payload?: string;
  delta_t?: number;
};

export type Prediction = { index: number; can_id: number; score: number; is_anomalous: boolean };
export type PredictResult = { model_id: string; threshold: number; total: number; anomalous_count: number; predictions: Prediction[] };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/ml${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = `API request failed: ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* keep default message */
    }
    throw new Error(detail);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const listModels = async () => (await request<{ items: ModelSummary[] }>("/models")).items;
export const registerModel = (name: string, description = "") =>
  request<ModelSummary>("/models", { method: "POST", body: JSON.stringify({ name, description }) });
export const deleteModel = (id: string) => request<void>(`/models/${id}`, { method: "DELETE" });
export const trainModel = (id: string, datasetId: string) =>
  request<ModelSummary>(`/models/${id}/train`, { method: "POST", body: JSON.stringify({ dataset_id: datasetId }) });
export const getModelStatus = (id: string) => request<{ id: string; status: ModelStatus; error?: string | null }>(`/models/${id}/status`);
export const getModelMetrics = (id: string) => request<Metrics>(`/models/${id}/metrics`);
export const predict = (id: string, frames: CanFrame[]) =>
  request<PredictResult>(`/models/${id}/predict`, { method: "POST", body: JSON.stringify({ frames }) });
