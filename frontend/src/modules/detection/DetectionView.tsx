import React, { useState } from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  Flame,
  History,
  Layers,
  Play,
  Radar,
  RotateCcw,
  Shield,
  ShieldAlert,
  Sliders,
  Terminal,
} from "lucide-react";
import { runDetection } from "../../shared/api/client";
import type {
  CANFrameInput,
  DatasetItem,
  DetectionResult,
  DetectionRunRequest,
} from "../../shared/types";

interface DetectionViewProps {
  datasets: DatasetItem[];
  recentRuns: DetectionResult[];
  onDetectionComplete: (result: DetectionResult) => void;
  initialDatasetId?: string | null;
}

// Preset frame test vectors
const SAMPLE_DOS_FRAMES: CANFrameInput[] = [
  { timestamp: 0.1000, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1001, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1002, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1003, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1004, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1005, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1006, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1007, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1008, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
  { timestamp: 0.1009, can_id: "0x000", dlc: 8, payload: "0000000000000000" },
];

const SAMPLE_NORMAL_FRAMES: CANFrameInput[] = [
  { timestamp: 0.010, can_id: "0x140", dlc: 8, payload: "966EBFC8E5E4E9D1" },
  { timestamp: 0.020, can_id: "0x316", dlc: 8, payload: "1242E6962EF85E4B" },
  { timestamp: 0.030, can_id: "0x140", dlc: 8, payload: "D61CDA8952D194A8" },
  { timestamp: 0.040, can_id: "0x260", dlc: 8, payload: "F1D0746DBB100808" },
  { timestamp: 0.050, can_id: "0x140", dlc: 8, payload: "423B63CAF013E6DB" },
  { timestamp: 0.060, can_id: "0x430", dlc: 8, payload: "2D4BA5661C2C2116" },
  { timestamp: 0.070, can_id: "0x316", dlc: 8, payload: "85826EE77B1B6BCF" },
  { timestamp: 0.080, can_id: "0x545", dlc: 8, payload: "BD1E2FADEF045F5E" },
];

const SAMPLE_SPOOFING_FRAMES: CANFrameInput[] = [
  { timestamp: 0.050, can_id: "0x140", dlc: 8, payload: "FFFFFFFFFFFFFFFF" },
  { timestamp: 0.051, can_id: "0x7FF", dlc: 8, payload: "1122334455667788" },
  { timestamp: 0.052, can_id: "0x7E0", dlc: 8, payload: "0011223344556677" },
  { timestamp: 0.053, can_id: "0x140", dlc: 4, payload: "AABBCCDD" },
];

export function DetectionView({
  datasets,
  recentRuns,
  onDetectionComplete,
  initialDatasetId,
}: DetectionViewProps) {
  const [sourceMode, setSourceMode] = useState<"dataset" | "manual">(
    initialDatasetId ? "dataset" : "dataset"
  );
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(
    initialDatasetId ?? (datasets[0]?.id || "demo_dos_attack")
  );

  // Manual frame state
  const [manualFramesText, setManualFramesText] = useState<string>(
    JSON.stringify(SAMPLE_DOS_FRAMES, null, 2)
  );
  const [validationError, setValidationError] = useState<string | null>(null);

  // Execution state
  const [running, setRunning] = useState(false);
  const [activeResult, setActiveResult] = useState<DetectionResult | null>(
    recentRuns[0] ?? null
  );
  const [executionError, setExecutionError] = useState<string | null>(null);

  const handlePresetSelect = (preset: CANFrameInput[]) => {
    setManualFramesText(JSON.stringify(preset, null, 2));
    setValidationError(null);
  };

  const handleRun = async () => {
    setRunning(true);
    setExecutionError(null);
    setValidationError(null);

    const payload: DetectionRunRequest = {};

    if (sourceMode === "dataset") {
      if (!selectedDatasetId) {
        setExecutionError("Please select a dataset to run detection.");
        setRunning(false);
        return;
      }
      payload.dataset_id = selectedDatasetId;
    } else {
      // Validate JSON input
      try {
        const parsed = JSON.parse(manualFramesText);
        if (!Array.isArray(parsed) || parsed.length === 0) {
          throw new Error("Input must be a non-empty array of CAN frames.");
        }
        payload.frames = parsed;
      } catch (err) {
        setValidationError(
          `JSON format error: ${err instanceof Error ? err.message : "Invalid JSON"}`
        );
        setRunning(false);
        return;
      }
    }

    try {
      const result = await runDetection(payload);
      setActiveResult(result);
      onDetectionComplete(result);
    } catch (err) {
      setExecutionError(err instanceof Error ? err.message : "Detection execution failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <Radar className="text-cyan-400" />
            <span>Hybrid CAN-Bus Anomaly Detection Console</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Executes Stage 1 Deterministic Rules + Stage 2 Multi-Class Classifier + 7-Row Arbitration Fusion
          </p>
        </div>

        {activeResult && (
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg">
            <span className="text-slate-500">Run ID:</span>
            <span className="text-cyan-300 font-semibold">{activeResult.run_id.slice(0, 8)}...</span>
            <span className="text-slate-500">&bull;</span>
            <span className="text-emerald-400 font-semibold">{activeResult.execution_time_ms} ms</span>
          </div>
        )}
      </div>

      <div className="grid gap-8 lg:grid-cols-12">
        {/* Left Column: Input Configuration & Ingestion (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm space-y-5">
            <h2 className="text-base font-semibold text-white flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Sliders size={18} className="text-cyan-400" />
                <span>Detection Input Source</span>
              </span>
              <span className="rounded bg-cyan-500/10 px-2 py-0.5 text-[11px] font-mono text-cyan-400 border border-cyan-500/20">
                Stage 1 &rarr; Stage 2
              </span>
            </h2>

            {/* Mode Switcher */}
            <div className="grid grid-cols-2 rounded-lg bg-slate-950 p-1 border border-slate-800">
              <button
                type="button"
                onClick={() => setSourceMode("dataset")}
                className={`rounded-md py-1.5 text-xs font-semibold transition-all ${
                  sourceMode === "dataset"
                    ? "bg-slate-800 text-cyan-400 shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Managed Dataset
              </button>
              <button
                type="button"
                onClick={() => setSourceMode("manual")}
                className={`rounded-md py-1.5 text-xs font-semibold transition-all ${
                  sourceMode === "manual"
                    ? "bg-slate-800 text-cyan-400 shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Custom Frame Editor
              </button>
            </div>

            {/* Mode 1: Dataset Selector */}
            {sourceMode === "dataset" ? (
              <div className="space-y-3">
                <label className="block text-xs font-medium text-slate-300">
                  Select Benchmark Dataset (from data/samples/)
                </label>
                <div className="space-y-2">
                  {datasets.map((ds) => (
                    <label
                      key={ds.id}
                      className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all ${
                        selectedDatasetId === ds.id
                          ? "border-cyan-500/50 bg-cyan-950/20"
                          : "border-slate-800 bg-slate-950/40 hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <input
                          type="radio"
                          name="dataset"
                          value={ds.id}
                          checked={selectedDatasetId === ds.id}
                          onChange={() => setSelectedDatasetId(ds.id)}
                          className="accent-cyan-400"
                        />
                        <div>
                          <p className="text-xs font-semibold text-white">{ds.name}</p>
                          <p className="text-[11px] text-slate-500 font-mono">
                            {ds.filename ?? `${ds.id}.csv`} &bull; {ds.rows.toLocaleString()} frames
                          </p>
                        </div>
                      </div>
                      <span className="text-xs font-mono text-cyan-400">
                        {ds.size_formatted ?? ""}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              /* Mode 2: Manual Ingestion Editor */
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-300">Preset CAN Test Vectors:</span>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => handlePresetSelect(SAMPLE_DOS_FRAMES)}
                      className="rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 text-[10px] font-semibold"
                    >
                      DoS Burst
                    </button>
                    <button
                      type="button"
                      onClick={() => handlePresetSelect(SAMPLE_NORMAL_FRAMES)}
                      className="rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold"
                    >
                      Normal Driving
                    </button>
                    <button
                      type="button"
                      onClick={() => handlePresetSelect(SAMPLE_SPOOFING_FRAMES)}
                      className="rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 px-2 py-0.5 text-[10px] font-semibold"
                    >
                      Spoofing / DLC
                    </button>
                  </div>
                </div>

                <textarea
                  value={manualFramesText}
                  onChange={(e) => setManualFramesText(e.target.value)}
                  rows={9}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs font-mono text-cyan-300 placeholder-slate-600 focus:border-cyan-500 focus:outline-none"
                  placeholder="[{ timestamp: 0.1, can_id: '0x000', dlc: 8, payload: '0000000000000000' }]"
                />

                {validationError && (
                  <p className="text-xs text-rose-400 bg-rose-500/10 p-2 rounded border border-rose-500/20">
                    {validationError}
                  </p>
                )}
              </div>
            )}

            {executionError && (
              <div className="rounded-lg bg-rose-500/10 border border-rose-500/30 p-3 text-xs text-rose-300">
                {executionError}
              </div>
            )}

            {/* Run Button */}
            <button
              onClick={handleRun}
              disabled={running}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/25 transition-all hover:brightness-110 active:scale-98 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {running ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-950 border-t-transparent" />
                  <span>Evaluating Detection Pipeline...</span>
                </>
              ) : (
                <>
                  <Play size={16} className="fill-slate-950" />
                  <span>Execute Hybrid Detection Pipeline</span>
                </>
              )}
            </button>
          </div>

          {/* Session Run History */}
          {recentRuns.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
                <History size={14} className="text-cyan-400" />
                <span>Session Run History</span>
              </h3>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {recentRuns.map((r) => (
                  <button
                    key={r.job_id}
                    onClick={() => setActiveResult(r)}
                    className={`w-full text-left p-2.5 rounded-lg border text-xs transition-colors flex items-center justify-between ${
                      activeResult?.job_id === r.job_id
                        ? "border-cyan-500/40 bg-cyan-950/20"
                        : "border-slate-800 bg-slate-950/40 hover:border-slate-700"
                    }`}
                  >
                    <div>
                      <p className="font-semibold text-white">
                        {r.dataset_id ? r.dataset_id.replace("_", " ").toUpperCase() : "Custom Frames"}
                      </p>
                      <p className="text-[11px] font-mono text-slate-500">
                        {r.total_frames} frames &bull; {r.execution_time_ms} ms
                      </p>
                    </div>
                    <span
                      className={`font-mono text-xs font-bold px-2 py-0.5 rounded ${
                        r.alert_count > 0 ? "bg-rose-500/20 text-rose-400" : "bg-emerald-500/20 text-emerald-400"
                      }`}
                    >
                      {r.alert_count} alerts
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Live Detection Results Dashboard (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {activeResult ? (
            <div className="space-y-6">
              {/* Telemetry Summary Banner */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-slate-800 gap-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-xl shadow-lg ${
                        activeResult.alert_count > 0
                          ? "bg-rose-500/20 text-rose-400 shadow-rose-500/10 border border-rose-500/30"
                          : "bg-emerald-500/20 text-emerald-400 shadow-emerald-500/10 border border-emerald-500/30"
                      }`}
                    >
                      {activeResult.alert_count > 0 ? (
                        <ShieldAlert size={22} />
                      ) : (
                        <CheckCircle2 size={22} />
                      )}
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-white">
                        {activeResult.alert_count > 0
                          ? `${activeResult.alert_count} Anomaly Alerts Flagged`
                          : "All Frames Verified Normal"}
                      </h2>
                      <p className="text-xs text-slate-400">
                        {activeResult.total_frames} frames evaluated • Stage 2: {activeResult.ml_mode ?? "unknown"}
                      </p>
                    </div>
                  </div>

                  <span className="rounded-full bg-slate-800 px-3 py-1 font-mono text-xs font-semibold text-emerald-400 border border-slate-700">
                    {activeResult.execution_time_ms} ms latency
                  </span>
                </div>

                {/* Metric Quick Stats */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
                  <div className="bg-slate-950/60 border border-slate-800/80 p-3 rounded-lg text-center">
                    <p className="text-[10px] font-mono text-slate-400 uppercase">Total Frames</p>
                    <p className="text-xl font-bold font-mono text-white mt-1">
                      {activeResult.total_frames}
                    </p>
                  </div>
                  <div className="bg-slate-950/60 border border-slate-800/80 p-3 rounded-lg text-center">
                    <p className="text-[10px] font-mono text-slate-400 uppercase">Clean (Stage 1)</p>
                    <p className="text-xl font-bold font-mono text-emerald-400 mt-1">
                      {activeResult.normal_count}
                    </p>
                  </div>
                  <div className="bg-slate-950/60 border border-slate-800/80 p-3 rounded-lg text-center">
                    <p className="text-[10px] font-mono text-slate-400 uppercase">Alerts Persisted</p>
                    <p className="text-xl font-bold font-mono text-rose-400 mt-1">
                      {activeResult.alert_count}
                    </p>
                  </div>
                  <div className="bg-slate-950/60 border border-slate-800/80 p-3 rounded-lg text-center">
                    <p className="text-[10px] font-mono text-slate-400 uppercase">Throughput</p>
                    <p className="text-xl font-bold font-mono text-cyan-400 mt-1">
                      {activeResult.execution_time_ms > 0
                        ? Math.round(
                            (activeResult.total_frames / activeResult.execution_time_ms) * 1000
                          ).toLocaleString()
                        : "—"}{" "}
                      <span className="text-xs font-normal">fps</span>
                    </p>
                  </div>
                </div>

                {/* Attack Labels Breakdown */}
                <div className="mt-5 pt-4 border-t border-slate-800">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    Multi-Class Label Distribution
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(activeResult.by_label || {}).map(([lbl, cnt]) => (
                      <span
                        key={lbl}
                        className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-mono font-semibold border ${
                          lbl === "dos"
                            ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                            : lbl === "fuzzy"
                            ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                            : lbl === "spoofing"
                            ? "bg-purple-500/10 text-purple-400 border-purple-500/30"
                            : "bg-slate-800 text-slate-300 border-slate-700"
                        }`}
                      >
                        <span className="uppercase">{lbl}:</span>
                        <span>{cnt}</span>
                      </span>
                    ))}
                  </div>
                </div>

                {/* Stage 1 Rule Hits Breakdown */}
                {activeResult.rule_hits && Object.keys(activeResult.rule_hits).length > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-800">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                      Stage 1 Deterministic Rule Violations Triggered
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(activeResult.rule_hits).map(([rId, cnt]) => (
                        <span
                          key={rId}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-950/40 text-cyan-300 border border-cyan-500/30 px-2.5 py-1 text-xs font-mono"
                        >
                          <span className="font-bold">{rId}:</span>
                          <span>{cnt} hits</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Generated Alerts Table */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
                <h3 className="text-base font-semibold text-white mb-4 flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <ShieldAlert size={18} className="text-rose-400" />
                    <span>Pipeline Generated Alerts ({activeResult.alerts?.length ?? 0})</span>
                  </span>
                  <span className="text-xs text-slate-400 font-mono">SQLite Persisted</span>
                </h3>

                {activeResult.alerts && activeResult.alerts.length > 0 ? (
                  <div className="overflow-x-auto rounded-lg border border-slate-800">
                    <table className="w-full text-left text-xs font-sans">
                      <thead className="bg-slate-950 text-slate-400 font-mono uppercase tracking-wider border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3">CAN ID</th>
                          <th className="py-2.5 px-3">Timestamp</th>
                          <th className="py-2.5 px-3">Severity</th>
                          <th className="py-2.5 px-3">Classification</th>
                          <th className="py-2.5 px-3">Confidence</th>
                          <th className="py-2.5 px-3">Stage</th>
                          <th className="py-2.5 px-3">Rules</th>
                            <th className="py-2.5 px-3">Evidence and explanation</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {activeResult.alerts.slice(0, 15).map((a, i) => (
                          <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                            <td className="py-2.5 px-3 font-mono font-bold text-cyan-300">
                              {a.can_id_hex}
                            </td>
                            <td className="py-2.5 px-3 font-mono text-slate-400">
                              {a.timestamp.toFixed(6)}
                            </td>
                            <td className="py-2.5 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  a.severity_level === "CRITICAL"
                                    ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                                    : a.severity_level === "HIGH"
                                    ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                                    : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                                }`}
                              >
                                {a.severity_level}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 font-semibold uppercase text-slate-200">
                              {a.label}
                            </td>
                            <td className="py-2.5 px-3 font-mono text-slate-300">
                              {(a.confidence * 100).toFixed(1)}%
                            </td>
                            <td className="py-2.5 px-3 font-mono text-[11px] text-slate-400">
                              {a.stage}
                            </td>
                            <td className="py-2.5 px-3 font-mono text-cyan-400 font-semibold">
                              {a.rule_ids || "—"}
                            </td>
                              <td className="py-2.5 px-3 text-slate-300 max-w-md">
                                <div title={a.reason}>{a.reason}</div>
                                {a.stage2_prediction && <div className="mt-1 text-[10px] text-amber-300">Stage 2 ({a.stage2_mode}): {a.stage2_prediction}{a.stage2_confidence != null ? ` · ${Math.round(a.stage2_confidence * 100)}%` : ""}</div>}
                                {a.shap_values && <div className="mt-1 text-[10px] text-cyan-300">SHAP: {Object.entries(a.shap_values).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1])).slice(0, 3).map(([name, value]) => `${name} ${value.toFixed(3)}`).join(" · ")}</div>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-center py-6 text-xs text-slate-500">
                    No intrusion alerts were generated for this batch.
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/30 p-12 text-center text-slate-500">
              <Radar size={48} className="mx-auto mb-3 text-slate-600 animate-pulse" />
              <h3 className="text-base font-semibold text-slate-300">No Detection Run Active</h3>
              <p className="mt-1 text-xs text-slate-500 max-w-md mx-auto">
                Select a benchmark dataset on the left or enter custom CAN frames, then click "Execute
                Hybrid Detection Pipeline" to view real-time arbitration results.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
