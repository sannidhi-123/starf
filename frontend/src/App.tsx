import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Activity, Database, Download, FileUp, Radar, Search, HardDrive, Trash2 } from "lucide-react";
import { Card } from "./shared/components/Card";
 feature/ml
import { ModelsPanel } from "./modules/ml";

import { datasetDownloadUrl, deleteDataset, listDatasets, uploadDataset, type Dataset } from "./modules/dataset";
main

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    try {
      const page = await listDatasets({ q: query, source: sourceFilter });
      setDatasets(page.items);
      setTotal(page.total);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load datasets.");
    }
  }

  useEffect(() => { void refresh(); }, [query, sourceFilter]);

  const sources = useMemo(() => Array.from(new Set(datasets.map((dataset) => dataset.source).filter((item): item is string => Boolean(item)))), [datasets]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!file) {
      setError("Choose a CSV or Parquet file first.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await uploadDataset(file, name, source);
      setName("");
      setSource("");
      setFile(null);
      formElement.reset();
      setNotice(`${created.name} was uploaded and validated.`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(dataset: Dataset) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await deleteDataset(dataset.id);
      setNotice(`${dataset.name} was deleted.`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete dataset.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-5 py-10 text-slate-100 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.25em] text-cyan-400">STARK · Dataset management</p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Dataset intelligence workspace</h1>
          <p className="mt-3 max-w-2xl text-slate-400">Upload CAN traffic datasets, inspect their metadata, and manage the files used by the detection workflow.</p>
        </header>

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Workspace summary">
          <Card label="Datasets" value={String(total)} icon={<Database size={20} />} />
          <Card label="Ready" value={String(datasets.filter((dataset) => dataset.status === "ready").length)} icon={<Activity size={20} />} />
          <Card label="Frames listed" value={datasets.reduce((sum, dataset) => sum + dataset.row_count, 0).toLocaleString()} icon={<Radar size={20} />} />
          <Card label="Formats" value={String(new Set(datasets.map((dataset) => dataset.format)).size)} icon={<HardDrive size={20} />} />
        </section>

        <section className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 sm:p-6">
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold">Your datasets</h2>
                <p className="mt-1 text-sm text-slate-400">{total} dataset{total === 1 ? "" : "s"} stored</p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <label className="relative">
                  <span className="sr-only">Search by dataset name</span>
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search datasets" className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2 pl-9 pr-3 text-sm outline-none focus:border-cyan-500 sm:w-48" />
                </label>
                <label>
                  <span className="sr-only">Filter by source</span>
                  <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-500 sm:w-40">
                    <option value="">All sources</option>
                    {sources.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
              </div>
            </div>

            {error && <p role="alert" className="mb-4 rounded-lg border border-rose-900 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">{error}</p>}
            {notice && <p role="status" className="mb-4 rounded-lg border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">{notice}</p>}

            {datasets.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-12 text-center">
                <Database className="mx-auto mb-3 text-slate-500" size={28} />
                <p className="font-medium">No datasets found</p>
                <p className="mt-1 text-sm text-slate-400">Upload a CSV or Parquet file to get started.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[38rem] text-left text-sm">
                  <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
                    <tr><th className="pb-3 pr-4 font-medium">Dataset</th><th className="pb-3 pr-4 font-medium">Source</th><th className="pb-3 pr-4 font-medium">Rows</th><th className="pb-3 pr-4 font-medium">Size</th><th className="pb-3 pr-4 font-medium">Status</th><th className="pb-3 font-medium"><span className="sr-only">Actions</span></th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {datasets.map((dataset) => (
                      <tr key={dataset.id}>
                        <td className="py-4 pr-4"><p className="font-medium text-slate-100">{dataset.name}</p><p className="mt-1 text-xs text-slate-500">{dataset.filename} · {dataset.format.toUpperCase()}</p><p className="mt-1 text-xs text-slate-500">{dataset.columns.length} columns</p></td>
                        <td className="py-4 pr-4 text-slate-300">{dataset.source || "—"}</td>
                        <td className="py-4 pr-4 tabular-nums text-slate-300">{dataset.row_count.toLocaleString()}</td>
                        <td className="py-4 pr-4 text-slate-300">{formatBytes(dataset.size_bytes)}</td>
                        <td className="py-4 pr-4"><span className="rounded-full bg-emerald-950 px-2.5 py-1 text-xs text-emerald-300">{dataset.status}</span></td>
                        <td className="py-4 text-right"><div className="flex justify-end"><a href={datasetDownloadUrl(dataset.id)} aria-label={`Download ${dataset.name}`} title="Download dataset" className="rounded-md p-2 text-slate-500 hover:bg-cyan-950 hover:text-cyan-300"><Download size={16} /></a><button disabled={busy} onClick={() => void handleDelete(dataset)} aria-label={`Delete ${dataset.name}`} title="Delete dataset" className="rounded-md p-2 text-slate-500 hover:bg-rose-950 hover:text-rose-300 disabled:opacity-40"><Trash2 size={16} /></button></div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <aside className="h-fit rounded-2xl border border-slate-800 bg-slate-900/70 p-5 sm:p-6">
            <div className="mb-5 flex items-center gap-3"><span className="rounded-lg bg-cyan-950 p-2 text-cyan-300"><FileUp size={20} /></span><div><h2 className="font-semibold">Upload dataset</h2><p className="text-xs text-slate-400">CSV or Parquet · up to 100 MB</p></div></div>
            <form onSubmit={(event) => void handleUpload(event)} className="space-y-4">
              <label className="block text-sm text-slate-300">Dataset name <span className="text-slate-500">(optional)</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={255} placeholder="Defaults to filename" className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-cyan-500" /></label>
              <label className="block text-sm text-slate-300">Source <span className="text-slate-500">(optional)</span><input value={source} onChange={(event) => setSource(event.target.value)} maxLength={128} placeholder="e.g. Car-Hacking" className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-cyan-500" /></label>
              <label className="block text-sm text-slate-300">Dataset file<input type="file" accept=".csv,.parquet" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="mt-1.5 block w-full cursor-pointer rounded-lg border border-slate-700 bg-slate-950 text-xs text-slate-400 file:mr-3 file:border-0 file:bg-slate-800 file:px-3 file:py-2.5 file:text-slate-200" /></label>
              <button disabled={busy || !file} className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 px-4 py-2.5 font-semibold text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Working…" : <><FileUp size={16} /> Upload and validate</>}</button>
            </form>
            <p className="mt-4 text-xs leading-5 text-slate-500">Uploads are checked for valid structure, stored locally, and indexed with row count, columns, size, and SHA-256 metadata.</p>
          </aside>
        </section>
        <ModelsPanel />
      </div>
    </main>
  );
}