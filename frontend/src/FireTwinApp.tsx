/* FireTwin on one page (team whiteboard, 2026-11-14), replacing the plan's three tabs:
   desktop: 3D view (left/centre) | variables panel (right); under the 3D view, the suppression
   recommendations, the dashboard and the chat (FE-10). Mobile stacks 3D, variables (collapsible), recommendations,
   dashboard. Compare is a full-screen mode on the same page, not a route. */
import { useCallback, useState } from "react";
import { ApiStatus } from "./components/ApiStatus";
import { ChatPanel } from "./components/ChatPanel";
import { CompareView } from "./components/CompareView";
import { Dashboard } from "./components/Dashboard";
import { SceneView } from "./components/SceneView";
import { SuppressionPanel } from "./components/SuppressionPanel";
import { VariablesPanel } from "./components/VariablesPanel";

export default function FireTwinApp() {
  const [comparing, setComparing] = useState(false);
  const closeCompare = useCallback(() => setComparing(false), []);
  return (
    <main className="page page-wide">
      <header className="grid gap-2">
        <span className="label">NASA Space Apps 2026 · Flame in Freefall</span>
        <h1 className="text-4xl font-bold tracking-tight">FireTwin</h1>
        <p className="muted m-0">A fire-safety digital twin of an ISS lab module: set up a fire, detect it, suppress it, and see why.</p>
      </header>
      <ApiStatus />
      {comparing ? (
        <CompareView onClose={closeCompare} />
      ) : (
        <div className="one-page">
          <SceneView onCompare={() => setComparing(true)} />
          <VariablesPanel />
          <SuppressionPanel />
          <Dashboard />
          <ChatPanel />
        </div>
      )}
      <footer className="foot-note">Flame is illustrative. Verdicts come from NASA PSI data.</footer>
    </main>
  );
}
