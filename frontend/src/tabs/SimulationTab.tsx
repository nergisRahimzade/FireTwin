import { Suspense, lazy } from "react";
import { ControlPanel } from "../components/ControlPanel";
import { useScenario } from "../store/useScenario";

// three.js loads only when this tab renders.
const IssScene = lazy(() => import("../scene/IssScene").then(m => ({ default: m.IssScene })));

export function SimulationTab() {
  const detect = useScenario(s => s.detect);
  const simulate = useScenario(s => s.simulate);
  return (
    <section className="sim-layout">
      <ControlPanel />
      <div className="grid gap-3 content-start">
        <div className="glass lab3d">
          <div className="lab3d-view">
            <div className="lab3d-canvas">
              <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
                <IssScene detect={detect} simulate={simulate} />
              </Suspense>
            </div>
          </div>
        </div>
        <p className="note">
          The ISS lab module (8.5 m × 4.2 m). Detectors appear where the API places them after Ignite. The model
          decides what the fire does; the 3D view only illustrates it.
        </p>
      </div>
    </section>
  );
}
