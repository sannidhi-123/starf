import React, { useCallback, useEffect, useState } from "react";
import {
  getAlerts,
  getAlertsSummary,
  getDatasets,
  getHealth,
  getMLModels,
  getRecentDetectionRuns,
} from "./shared/api/client";
import { Navigation, type NavTab } from "./shared/components/Navigation";
import type {
  AlertItem,
  AlertSummary,
  DatasetItem,
  DetectionResult,
  MLModel,
  SystemHealth,
} from "./shared/types";
import { DashboardView } from "./modules/dashboard/DashboardView";
import { DatasetView } from "./modules/dataset/DatasetView";
import { DetectionView } from "./modules/detection/DetectionView";
import { MLView } from "./modules/ml/MLView";
import { AlertsView } from "./modules/alerts/AlertsView";

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");

  // Global Backend Data State
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(false);

  const [models, setModels] = useState<MLModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);

  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [alertsSummary, setAlertsSummary] = useState<AlertSummary | null>(null);
  const [alertsLoading, setAlertsLoading] = useState(false);

  const [recentRuns, setRecentRuns] = useState<DetectionResult[]>([]);

  // Filter state for alerts
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [runIdFilter, setRunIdFilter] = useState("");

  // Navigation transfer state (e.g. quick run from dashboard/datasets)
  const [targetedDatasetId, setTargetedDatasetId] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Data Fetching
  // ---------------------------------------------------------------------------

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const data = await getHealth();
      setHealth(data);
    } catch {
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const fetchDatasets = useCallback(async () => {
    setDatasetsLoading(true);
    try {
      const items = await getDatasets();
      setDatasets(items);
    } catch {
      setDatasets([]);
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  const fetchModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const items = await getMLModels();
      setModels(items);
    } catch {
      setModels([]);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  const fetchAlerts = useCallback(async () => {
    setAlertsLoading(true);
    try {
      const [items, summary] = await Promise.all([
        getAlerts({
          severity: severityFilter,
          run_id: runIdFilter || undefined,
          limit: 200,
        }),
        getAlertsSummary(),
      ]);
      setAlerts(items);
      setAlertsSummary(summary);
    } catch {
      setAlerts([]);
      setAlertsSummary(null);
    } finally {
      setAlertsLoading(false);
    }
  }, [severityFilter, runIdFilter]);

  const fetchRecentRuns = useCallback(async () => {
    try {
      const runs = await getRecentDetectionRuns();
      setRecentRuns(runs);
    } catch {
      setRecentRuns([]);
    }
  }, []);

  const refreshAll = useCallback(() => {
    fetchHealth();
    fetchDatasets();
    fetchModels();
    fetchAlerts();
    fetchRecentRuns();
  }, [fetchHealth, fetchDatasets, fetchModels, fetchAlerts, fetchRecentRuns]);

  // Initial mount load
  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // Re-fetch alerts when filters change
  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Background health heartbeat every 15s
  useEffect(() => {
    const timer = setInterval(() => {
      fetchHealth();
    }, 15000);
    return () => clearInterval(timer);
  }, [fetchHealth]);

  // Trigger detection from quick-run button
  const handleQuickRun = (datasetId: string) => {
    setTargetedDatasetId(datasetId);
    setActiveTab("detection");
  };

  const handleDetectionComplete = (result: DetectionResult) => {
    setRecentRuns((prev) => [result, ...prev.filter((r) => r.job_id !== result.job_id)]);
    // Re-fetch alerts and summary to reflect new alerts in SQLite
    fetchAlerts();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Cybersecurity Navigation */}
      <Navigation
        activeTab={activeTab}
        onTabChange={(tab) => {
          setActiveTab(tab);
          setTargetedDatasetId(null);
        }}
        health={health}
        healthLoading={healthLoading}
        onRefresh={refreshAll}
        alertsCount={alertsSummary?.total ?? alerts.length}
        detectionMode={models.find((model) => model.id === "stage2_classifier")?.status_label ?? "unknown"}
      />

      {/* Main Content Area */}
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
        {activeTab === "dashboard" && (
          <DashboardView
            health={health}
            healthLoading={healthLoading}
            datasets={datasets}
            datasetsLoading={datasetsLoading}
            models={models}
            modelsLoading={modelsLoading}
            alerts={alerts}
            alertsSummary={alertsSummary}
            alertsLoading={alertsLoading}
            recentRuns={recentRuns}
            onNavigate={(tab) => {
              setActiveTab(tab);
              setTargetedDatasetId(null);
            }}
            onQuickRun={handleQuickRun}
          />
        )}

        {activeTab === "datasets" && (
          <DatasetView
            datasets={datasets}
            loading={datasetsLoading}
            onRefresh={fetchDatasets}
            onRunDetection={handleQuickRun}
          />
        )}

        {activeTab === "detection" && (
          <DetectionView
            datasets={datasets}
            recentRuns={recentRuns}
            onDetectionComplete={handleDetectionComplete}
            initialDatasetId={targetedDatasetId}
          />
        )}

        {activeTab === "models" && (
          <MLView models={models} loading={modelsLoading} onRefresh={fetchModels} />
        )}

        {activeTab === "alerts" && (
          <AlertsView
            alerts={alerts}
            alertsSummary={alertsSummary}
            loading={alertsLoading}
            onRefresh={fetchAlerts}
            severityFilter={severityFilter}
            onSeverityFilterChange={setSeverityFilter}
            runIdFilter={runIdFilter}
            onRunIdFilterChange={setRunIdFilter}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-6 text-center text-xs text-slate-500">
        <div className="mx-auto max-w-7xl px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p>
            STARF &bull; Smart Traffic Anomaly Recognition Framework &bull; Intra-Vehicular CAN Security
          </p>
          <p className="font-mono text-slate-600">
            Phase-II Engineering Review &bull; Two-Stage Hybrid IDS (Deterministic Rules + Multi-Class ML)
          </p>
        </div>
      </footer>
    </div>
  );
}