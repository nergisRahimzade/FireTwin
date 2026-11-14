import { useState } from "react";
import { ApiStatus } from "./components/ApiStatus";
import { ChatTab } from "./tabs/ChatTab";
import { ResultsTab } from "./tabs/ResultsTab";
import { SimulationTab } from "./tabs/SimulationTab";

const TABS = [
  ["simulation", "Simulation"],
  ["results", "Results"],
  ["chat", "Chat"],
] as const;
type TabId = (typeof TABS)[number][0];

export default function FireTwinApp() {
  const [tab, setTab] = useState<TabId>("simulation");
  return (
    <main className="page">
      <header className="grid gap-2">
        <span className="label">NASA Space Apps 2026 · Flame in Freefall</span>
        <h1 className="text-4xl font-bold tracking-tight">FireTwin</h1>
        <p className="muted m-0">A fire-safety digital twin of an ISS lab module: set up a fire, detect it, suppress it, and see why.</p>
      </header>
      <ApiStatus />
      <div className="grid gap-6">
        <nav className="tabs" role="tablist" aria-label="FireTwin">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
        {tab === "simulation" && <SimulationTab />}
        {tab === "results" && <ResultsTab />}
        {tab === "chat" && <ChatTab />}
      </div>
      <footer className="foot-note">Flame is illustrative. Verdicts come from NASA PSI data.</footer>
    </main>
  );
}
