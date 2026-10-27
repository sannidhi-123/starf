import { useCallback, useEffect, useState } from "react";
import { Activity, Plus, RefreshCw } from "lucide-react";
import { ModelDetail } from "./ModelDetail";
import { StatusBadge } from "./StatusBadge";
import { listModels, registerModel, type ModelSummary } from "./api";

export function ModelsPanel() {
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setModels(await listModels());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onRegister(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const created = await registerModel(name.trim());
      setName("");
      setSelectedId(created.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const selected = models.find((m) => m.id === selectedId);
  // Integration-provided models (e.g. mock "baseline") have no architecture and are read-only.
  const isManaged = selected?.architecture !== undefined;

  return (
    <section className="mt-12">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-2xl font-semibold"><Activity size={22} className="text-cyan-400" />Models</h2>
        <button onClick={() => void refresh()} className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200"><RefreshCw size={14} />Refresh</button>
      </div>
      {error && <p className="mt-3 rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-sm text-red-300">{error}</p>}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-1">
          <form onSubmit={onRegister} className="flex gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New model name" maxLength={100}
              className="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm placeholder:text-slate-600" />
            <button type="submit" className="flex items-center gap-1 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400"><Plus size={14} />Register</button>
          </form>
          <ul className="space-y-2">
            {models.map((m) => (
              <li key={m.id}>
                <button onClick={() => setSelectedId(m.id)}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm ${m.id === selectedId ? "border-cyan-500 bg-slate-900" : "border-slate-800 bg-slate-900/50 hover:border-slate-700"}`}>
                  <span className="truncate">{m.name}</span><StatusBadge status={m.status} />
                </button>
              </li>
            ))}
            {models.length === 0 && !error && <li className="text-sm text-slate-500">No models yet. Register one to get started.</li>}
          </ul>
        </div>

        <div className="lg:col-span-2">
          {selected && isManaged ? (
            <ModelDetail key={selected.id} model={selected} onChanged={refresh} onDeleted={() => { setSelectedId(null); void refresh(); }} />
          ) : selected ? (
            <p className="rounded-xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-400">"{selected.name}" is provided by the integration layer and is read-only.</p>
          ) : (
            <p className="rounded-xl border border-dashed border-slate-800 p-5 text-sm text-slate-500">Select a model to train it, view metrics, or run inference.</p>
          )}
        </div>
      </div>
    </section>
  );
}
