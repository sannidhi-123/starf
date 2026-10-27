import React, { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  Eye,
  FileSpreadsheet,
  FileText,
  Play,
  RefreshCw,
  Upload,
  X,
} from "lucide-react";
import { getDatasetDetails, uploadDataset } from "../../shared/api/client";
import type { DatasetDetails, DatasetItem } from "../../shared/types";

interface DatasetViewProps {
  datasets: DatasetItem[];
  loading: boolean;
  onRefresh: () => void;
  onRunDetection: (datasetId: string) => void;
}

export function DatasetView({
  datasets,
  loading,
  onRefresh,
  onRunDetection,
}: DatasetViewProps) {
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);
  const [datasetDetails, setDatasetDetails] = useState<DatasetDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const handleInspect = async (id: string) => {
    setSelectedDataset(id);
    setDetailsLoading(true);
    setDetailsError(null);
    try {
      const details = await getDatasetDetails(id);
      setDatasetDetails(details);
    } catch (err) {
      setDetailsError(err instanceof Error ? err.message : "Failed to load dataset details");
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;

    if (!uploadFile.name.toLowerCase().endsWith(".csv")) {
      setUploadMsg({ type: "error", text: "Only CSV files are supported (.csv)" });
      return;
    }

    setUploading(true);
    setUploadMsg(null);
    try {
      const content = await uploadFile.text();
      const res = await uploadDataset(uploadFile.name, content);
      setUploadMsg({
        type: "success",
        text: `Successfully uploaded ${res.name} (${res.rows.toLocaleString()} frames)`,
      });
      setUploadFile(null);
      onRefresh();
    } catch (err) {
      setUploadMsg({
        type: "error",
        text: err instanceof Error ? err.message : "Upload failed",
      });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <Database className="text-cyan-400" />
            <span>CAN-Bus Dataset Repository</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Repository samples and uploaded traces. Dataset provenance is shown only when verified.
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-850 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={14} className={loading ? "animate-spin text-cyan-400" : ""} />
          <span>Refresh Datasets</span>
        </button>
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        {/* Datasets Table */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
            <h2 className="text-base font-semibold text-white mb-4 flex items-center justify-between">
              <span>Available Samples & Captures</span>
              <span className="text-xs font-normal text-slate-400 font-mono">
                {datasets.length} files located
              </span>
            </h2>

            {loading ? (
              <div className="py-16 text-center text-slate-400">
                <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent mb-2" />
                <p className="text-sm">Scanning dataset directory...</p>
              </div>
            ) : datasets.length === 0 ? (
              <div className="py-12 text-center text-slate-500">
                <FileSpreadsheet size={36} className="mx-auto mb-2 opacity-50" />
                <p className="text-sm">No CSV datasets found in data/samples/</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-950/80 text-xs font-mono uppercase tracking-wider text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">Dataset Name</th>
                      <th className="py-3 px-4">File Name</th>
                      <th className="py-3 px-4">Total Rows</th>
                      <th className="py-3 px-4">Provenance</th>
                      <th className="py-3 px-4">File Size</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-sans">
                    {datasets.map((ds) => (
                      <tr key={ds.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3.5 px-4 font-semibold text-white">
                          <div className="flex items-center gap-2">
                            <span className="h-2 w-2 rounded-full bg-cyan-400" />
                            <span>{ds.name}</span>
                          </div>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-xs text-slate-400">
                          {ds.filename ?? `${ds.id}.csv`}
                        </td>
                        <td className="py-3.5 px-4 font-mono text-cyan-300 font-medium">
                          {ds.rows > 0 ? ds.rows.toLocaleString() : "Evaluating"}
                        </td>
                        <td className="py-3.5 px-4 text-xs text-amber-300">{ds.source_kind ?? "provenance unverified"}</td>
                        <td className="py-3.5 px-4 font-mono text-xs text-slate-400">
                          {ds.size_formatted ?? "—"}
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <div className="inline-flex items-center gap-2">
                            <button
                              onClick={() => handleInspect(ds.id)}
                              className="inline-flex items-center gap-1 rounded bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors"
                            >
                              <Eye size={12} />
                              <span>Inspect</span>
                            </button>
                            <button
                              onClick={() => onRunDetection(ds.id)}
                              className="inline-flex items-center gap-1 rounded bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 px-2.5 py-1 text-xs font-semibold transition-colors"
                            >
                              <Play size={11} className="fill-cyan-400" />
                              <span>Detect</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Upload Form */}
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
            <h2 className="text-base font-semibold text-white flex items-center gap-2 mb-2">
              <Upload size={18} className="text-cyan-400" />
              <span>Upload CAN Capture</span>
            </h2>
            <p className="text-xs text-slate-400 mb-4">
              Add custom CAN log traces for anomaly testing. Supports standard Car-Hacking format with
              columns <code>Timestamp</code>, <code>CAN ID</code>, <code>DLC</code>, and <code>DATA[0..7]</code>.
            </p>

            <form onSubmit={handleUploadSubmit} className="space-y-4">
              <div className="rounded-xl border-2 border-dashed border-slate-700/80 p-6 text-center hover:border-cyan-500/50 transition-colors bg-slate-950/40">
                <FileText size={32} className="mx-auto text-slate-500 mb-2" />
                <label className="cursor-pointer">
                  <span className="text-xs font-semibold text-cyan-400 hover:underline">
                    Browse CAN CSV File
                  </span>
                  <input
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files?.[0]) setUploadFile(e.target.files[0]);
                    }}
                  />
                </label>
                {uploadFile ? (
                  <p className="mt-2 text-xs font-mono text-emerald-400 font-semibold truncate">
                    {uploadFile.name} ({(uploadFile.size / 1024).toFixed(1)} KB)
                  </p>
                ) : (
                  <p className="mt-1 text-[11px] text-slate-500">Supports comma-separated UTF-8 CSV</p>
                )}
              </div>

              {uploadMsg && (
                <div
                  className={`rounded-lg p-3 text-xs flex items-center gap-2 ${
                    uploadMsg.type === "success"
                      ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                      : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
                  }`}
                >
                  {uploadMsg.type === "success" ? (
                    <CheckCircle2 size={14} className="shrink-0" />
                  ) : (
                    <AlertCircle size={14} className="shrink-0" />
                  )}
                  <span>{uploadMsg.text}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={!uploadFile || uploading}
                className="w-full rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 py-2.5 text-xs font-bold text-slate-950 transition-all hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {uploading ? "Ingesting Dataset..." : "Upload to Server"}
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Dataset Inspector Modal */}
      {selectedDataset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
          <div className="relative w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 p-5 bg-slate-950/60">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Database size={18} className="text-cyan-400" />
                  <span>{datasetDetails?.name ?? selectedDataset}</span>
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  {datasetDetails?.filename} &bull; {datasetDetails?.rows.toLocaleString()} rows &bull;{" "}
                  {datasetDetails?.size_formatted}
                </p>
              </div>
              <button
                onClick={() => {
                  setSelectedDataset(null);
                  setDatasetDetails(null);
                }}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {detailsLoading ? (
                <div className="py-16 text-center text-slate-400">
                  <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent mb-2" />
                  <p className="text-sm">Reading dataset frames...</p>
                </div>
              ) : detailsError ? (
                <div className="rounded-lg bg-rose-500/10 border border-rose-500/30 p-4 text-xs text-rose-300">
                  {detailsError}
                </div>
              ) : datasetDetails ? (
                <>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs text-amber-200">
                    Source: {datasetDetails.source_kind ?? "provenance unverified"}
                  </div>
                  {datasetDetails.label_distribution && <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Label distribution</h4>
                    <div className="flex flex-wrap gap-2">{Object.entries(datasetDetails.label_distribution).map(([label, count]) => <span key={label} className="rounded bg-slate-800 px-2.5 py-1 text-xs font-mono text-slate-200">{label}: {count.toLocaleString()}</span>)}</div>
                  </div>}
                  {/* Columns */}
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                      CSV Column Schema
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {datasetDetails.columns.map((col) => (
                        <span
                          key={col}
                          className="rounded bg-slate-800 px-2.5 py-1 text-xs font-mono text-cyan-300 border border-slate-700"
                        >
                          {col}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Sample Frames Preview Table */}
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                      Frame Preview (First 15 frames)
                    </h4>
                    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider border-b border-slate-800">
                          <tr>
                            <th className="py-2.5 px-3">Timestamp (s)</th>
                            <th className="py-2.5 px-3">CAN ID</th>
                            <th className="py-2.5 px-3">DLC</th>
                            <th className="py-2.5 px-3">Hex Payload (D0..D7)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {datasetDetails.sample_frames.map((sf, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/30">
                              <td className="py-2 px-3 text-slate-300">{sf.timestamp}</td>
                              <td className="py-2 px-3 font-semibold text-cyan-400">{sf.can_id}</td>
                              <td className="py-2 px-3 text-slate-400">{sf.dlc}</td>
                              <td className="py-2 px-3 text-slate-200 tracking-wider">
                                {sf.payload || "00"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 border-t border-slate-800 bg-slate-950/80 p-4">
              <button
                onClick={() => {
                  setSelectedDataset(null);
                  setDatasetDetails(null);
                }}
                className="rounded-lg px-4 py-2 text-xs font-medium text-slate-400 hover:text-white"
              >
                Close
              </button>
              {selectedDataset && (
                <button
                  onClick={() => {
                    const dsId = selectedDataset;
                    setSelectedDataset(null);
                    onRunDetection(dsId);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 px-4 py-2 text-xs font-bold text-slate-950 shadow-lg shadow-cyan-500/20"
                >
                  <Play size={12} className="fill-slate-950" />
                  <span>Run Detection on This Dataset</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
