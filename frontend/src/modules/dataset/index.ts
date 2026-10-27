export type Dataset = {
  id: string;
  name: string;
  filename: string;
  format: string;
  source: string | null;
  status: string;
  row_count: number;
  columns: string[];
  size_bytes: number;
  sha256: string;
  created_at: string | null;
};

export type DatasetPage = { items: Dataset[]; total: number; limit: number; offset: number };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function readError(response: Response): Promise<Error> {
  let message = `API request failed: ${response.status}`;
  try {
    const body = await response.json() as { detail?: string };
    if (body.detail) message = body.detail;
  } catch {
    // Keep the HTTP status message when the response has no JSON body.
  }
  return new Error(message);
}

export async function listDatasets(filters: { q?: string; source?: string } = {}): Promise<DatasetPage> {
  const params = new URLSearchParams({ limit: "100" });
  if (filters.q) params.set("q", filters.q);
  if (filters.source) params.set("source", filters.source);
  const response = await fetch(`${API_BASE_URL}/datasets?${params}`);
  if (!response.ok) throw await readError(response);
  return response.json() as Promise<DatasetPage>;
}

export async function uploadDataset(file: File, name: string, source: string): Promise<Dataset> {
  const form = new FormData();
  form.append("file", file);
  if (name.trim()) form.append("name", name.trim());
  if (source.trim()) form.append("source", source.trim());
  const response = await fetch(`${API_BASE_URL}/datasets`, { method: "POST", body: form });
  if (!response.ok) throw await readError(response);
  return response.json() as Promise<Dataset>;
}

export async function deleteDataset(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw await readError(response);
}

export function datasetDownloadUrl(id: string): string {
  return `${API_BASE_URL}/datasets/${encodeURIComponent(id)}/download`;
}
