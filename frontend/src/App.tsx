import { Activity, Database, Radar, ShieldAlert } from "lucide-react";
import { Card } from "./shared/components/Card";

const cards = [
  { label: "Datasets", value: "1", icon: Database },
  { label: "Detections", value: "0", icon: Radar },
  { label: "Models", value: "1", icon: Activity },
  { label: "Alerts", value: "0", icon: ShieldAlert },
];

export default function App() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <div className="mx-auto max-w-6xl">
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.25em] text-cyan-400">STARK</p>
        <h1 className="text-4xl font-bold tracking-tight">Dataset intelligence workspace</h1>
        <p className="mt-3 max-w-2xl text-slate-400">A runnable foundation for dataset discovery, detection, ML workflows, and alerting.</p>
        <section className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {cards.map(({ label, value, icon: Icon }) => <Card key={label} label={label} value={value} icon={<Icon size={20} />} />)}
        </section>
      </div>
    </main>
  );
}
