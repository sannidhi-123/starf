import React from "react";
import {
  Activity,
  AlertTriangle,
  Database,
  LayoutDashboard,
  Radar,
  RefreshCw,
  Shield,
  Wifi,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import type { SystemHealth } from "../types";

export type NavTab = "dashboard" | "datasets" | "detection" | "models" | "alerts";

interface NavigationProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  health: SystemHealth | null;
  healthLoading: boolean;
  onRefresh: () => void;
  alertsCount?: number;
  detectionMode?: string;
}

export function Navigation({
  activeTab,
  onTabChange,
  health,
  healthLoading,
  onRefresh,
  alertsCount = 0,
  detectionMode = "unknown",
}: NavigationProps) {
  interface TabItem {
    id: NavTab;
    label: string;
    icon: LucideIcon;
    badge?: number;
  }

  const tabs: TabItem[] = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "datasets", label: "Datasets", icon: Database },
    { id: "detection", label: "CAN Detection", icon: Radar },
    { id: "models", label: "ML & Rules", icon: Activity },
    {
      id: "alerts",
      label: "Alerts",
      icon: AlertTriangle,
      badge: alertsCount > 0 ? alertsCount : undefined,
    },
  ];

  const isOnline = health?.status === "ok";

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
        {/* Brand / Logo */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 shadow-lg shadow-cyan-500/20">
            <Shield className="h-6 w-6 text-slate-950" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold tracking-tight text-white">STARF</span>
              <span className="rounded bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-400 border border-cyan-500/20">
                Phase-II IDS
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">
              Intra-Vehicular CAN-Bus Anomaly Recognition
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 sm:gap-2">
          {tabs.map(({ id, label, icon: Icon, badge }) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                onClick={() => onTabChange(id as NavTab)}
                className={`relative flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                  isActive
                    ? "bg-slate-800/90 text-cyan-400 shadow-sm border border-slate-700/60"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                }`}
              >
                <Icon size={16} />
                <span className="hidden md:inline">{label}</span>
                {badge !== undefined && (
                  <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500/20 px-1 text-[10px] font-bold text-rose-400 border border-rose-500/30">
                    {badge > 99 ? "99+" : badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* System Status & Refresh */}
        <div className="flex items-center gap-2">
          <span className="hidden xl:inline rounded border border-slate-800 bg-slate-900 px-2.5 py-1 text-[10px] font-mono text-slate-300">Stage 2: {detectionMode}</span>
          <div
            className={`flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
              isOnline
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                : "border-rose-500/30 bg-rose-500/10 text-rose-400"
            }`}
          >
            {isOnline ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
                </span>
                <span className="hidden sm:inline">Backend</span>
                <span className="font-semibold">Online</span>
                {health?.latencyMs !== undefined && (
                  <span className="text-[10px] text-emerald-500/80">({health.latencyMs}ms)</span>
                )}
              </>
            ) : (
              <>
                <WifiOff size={12} className="animate-pulse" />
                <span className="font-semibold">Offline</span>
              </>
            )}
          </div>

          <button
            onClick={onRefresh}
            title="Refresh All Data"
            disabled={healthLoading}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 bg-slate-900 text-slate-400 transition-colors hover:border-slate-700 hover:text-slate-200 disabled:opacity-50"
          >
            <RefreshCw size={14} className={healthLoading ? "animate-spin text-cyan-400" : ""} />
          </button>
        </div>
      </div>
    </header>
  );
}
