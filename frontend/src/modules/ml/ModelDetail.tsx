import { useCallback, useEffect, useState } from "react";
import { Play, Trash2, Zap } from "lucide-react";
import { StatusBadge } from "./StatusBadge";
import {
  deleteModel, getModelMetrics, getModelStatus, predict, trainModel,
  type CanFrame, type Metrics, type ModelSummary, type PredictResult,
} from "./api";

const SAMPLE_FRAMES: CanFrame[] = [
  { timestamp: 1.0, can_id: 0, dlc: 8, payload: "0000000000000000", delta_t: 0.0003 },
  { timestamp: 2.0, can_id: 256, dlc: 8, payload: "0A1B2C3D0A1B2C3D", delta_t: 0.01 },
];

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

type Props = { model: ModelSummary; onChanged: () => Promise<void> | void; onDeleted: () => void };

export function ModelDetail({ model, onChanged, onDeleted }: Props) {
  const [status, setStatus] = useState(model.status);
  const [modelError, setModelError] = useState<string | null>(model.error ?? null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [datasetId, setDatasetId] = useState("demo-dataset");
  const [framesJson, setFramesJson] = useState(JSON.stringify(SAMPLE_FRAMES, null, 2));
  const [result, setResult] = useState<PredictResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMetrics = useCallback(async () => {
    try {
      setMetrics(await getModelMetrics(model.id));
    } catch {
      setMetrics(null);
    }
  }, [model.id]);

  useEffect(() => {
    if (status === "trained") void loadMetrics();
  }, [status, loadMetrics]);

  // Poll while training.
  useEffect(() => {
    if (status !== "training") return;
    const timer = setInterval(async () => {
      try {
        const s = await getModelStatus(model.id);
        setStatus(s.status);
        setModelError(s.error ?? null);
        if (s.status !== "training") {
          clearInterval(timer);
          void onChanged();
        }
      } catch (e) {
        setError((e as Error).message);
        clearInterval(timer);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [status, model.id, onChanged]);

  async function onTrain() {
    setError(null);
    try {
      const updated = await trainModel(model.id, datasetId.trim());
      setStatus(updated.status);
      setModelError(null);
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onPredict() {
    setError(null);
    setResult(null);
    try {
      setResult(await predict(model.id, JSON.parse(framesJson) as CanFrame[]));
    } catch (e) {
      setError(e instanceof SyntaxError ? "Frames must be valid JSON" : (e as Error).message);
    }
  }

  async function onDelete() {
    try {
      await deleteModel(model.id);
      onDeleted();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-5 rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{model.name}</h3>
          <p className="text-xs text-slate-500">{model.id} · {model.architecture}{model.data_source ? ` · data: ${model.data_source}` : ""}</p>
        </div>
        <div className="flex items-center gap-3"><StatusBadge status={status} />
          <button onClick={() => void onDelete()} title="Delete model" disabled={status === "training"} className="text-slate-500 hover:text-red-400 disabled:opacity-40"><Trash2 size={16} /></button>
        </div>
      </div>

      {(error || modelError) && <p className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-sm text-red-300">{error ?? modelError}</p>}

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-sm text-slate-400">Dataset ID
          <input value={datasetId} onChange={(e) => setDatasetId(e.target.value)} className="mt-1 block rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
        </label>
        <button onClick={() => void onTrain()} disabled={status === "training" || !datasetId.trim()}
          className="flex items-center gap-1 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400 disabled:opacity-50">
          <Play size={14} />{status === "training" ? "Training…" : status === "trained" ? "Retrain" : "Train"}
        </button>
      </div>

      {metrics && (
        <div>
          <h4 className="mb-2 text-sm font-semibold text-slate-300">Metrics <span className="font-normal text-slate-500">({metrics.test_samples} held-out samples)</span></h4>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {([["Accuracy", pct(metrics.accuracy)], ["Precision", pct(metrics.precision)], ["Recall", pct(metrics.recall)], ["F1", pct(metrics.f1)], ["ROC-AUC", metrics.roc_auc === null ? "n/a" : metrics.roc_auc.toFixed(3)]] as const).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-slate-950 p-3"><dt className="text-xs text-slate-500">{k}</dt><dd className="text-lg font-semibold">{v}</dd></div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-slate-500">TP {metrics.confusion_matrix.tp} · FP {metrics.confusion_matrix.fp} · TN {metrics.confusion_matrix.tn} · FN {metrics.confusion_matrix.fn}</p>
        </div>
      )}

      {status === "trained" && (
        <div>
          <h4 className="mb-2 text-sm font-semibold text-slate-300">Inference</h4>
          <textarea value={framesJson} onChange={(e) => setFramesJson(e.target.value)} rows={7} spellCheck={false}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-slate-200" />
          <button onClick={() => void onPredict()} className="mt-2 flex items-center gap-1 rounded-lg bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700"><Zap size={14} />Run inference</button>
          {result && (
            <table className="mt-3 w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500"><tr><th className="py-1">#</th><th>CAN ID</th><th>Score</th><th>Verdict</th></tr></thead>
              <tbody>{result.predictions.map((p) => (
                <tr key={p.index} className="border-t border-slate-800">
                  <td className="py-1">{p.index}</td><td>0x{p.can_id.toString(16).toUpperCase()}</td><td>{p.score.toFixed(3)}</td>
                  <td className={p.is_anomalous ? "text-red-300" : "text-emerald-300"}>{p.is_anomalous ? "anomalous" : "normal"}</td>
                </tr>))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
