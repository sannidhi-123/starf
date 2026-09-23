import { Activity, Database, Radar, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Card } from "./shared/components/Card";
import { getAlerts, getDatasets, getHealth, getModels, type Health } from "./shared/api/client";

const cards = [
  { label: "Datasets", icon: Database },
  { label: "Detections", icon: Radar },
  { label: "Models", icon: Activity },
  { label: "Alerts", icon: ShieldAlert },
];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [counts, setCounts] = useState({ datasets: 0, models: 0, alerts: 0 });

  useEffect(() => {
    Promise.all([getHealth(), getDatasets(), getModels(), getAlerts()])
      .then(([healthResponse, datasets, models, alerts]) => {
        setHealth(healthResponse);
        setCounts({ datasets: datasets.length, models: models.length, alerts: alerts.length });
      })
      .catch(() => setHealth(null));
  }, []);

  const values = { Datasets: String(counts.datasets), Detections: "0", Models: String(counts.models), Alerts: String(counts.alerts) };
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <div className="mx-auto max-w-6xl">
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.25em] text-cyan-400">STARK</p>
        <h1 className="text-4xl font-bold tracking-tight">Dataset intelligence workspace</h1>
        <p className="mt-3 max-w-2xl text-slate-400">Hybrid CAN-bus anomaly detection with a transparent rule filter and an explainable ML stage.</p>
        <section className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {cards.map(({ label, icon: Icon }) => <Card key={label} label={label} value={values[label as keyof typeof values]} icon={<Icon size={20} />} />)}
        </section>
        <div className="mt-8 rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
          {health ? `API connected · ${health.pipeline} · ${health.model}` : "Connecting to the detection API…"}
        </div>
      </div>
    </main>
  );
}
