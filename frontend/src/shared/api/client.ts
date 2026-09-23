const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type Health = {
  status: string;
  environment: string;
  integration: string;
  pipeline: string;
  model: string;
};

export type Dataset = { id: string; name: string; status: string };
export type Model = { id: string; name: string; status: string };
export type Alert = { final_class: string; severity: string | null };

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export async function getHealth(): Promise<Health> {
  return get<Health>("/health");
}

export async function getDatasets(): Promise<Dataset[]> {
  const response = await get<{ items: Dataset[] }>("/datasets");
  return response.items;
}

export async function getModels(): Promise<Model[]> {
  const response = await get<{ items: Model[] }>("/ml/models");
  return response.items;
}

export async function getAlerts(): Promise<Alert[]> {
  const response = await get<{ items: Alert[] }>("/alerts");
  return response.items;
}
