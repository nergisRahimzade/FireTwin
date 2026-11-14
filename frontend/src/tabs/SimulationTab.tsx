import { Suspense, lazy, useRef } from "react";
import { ControlPanel } from "../components/ControlPanel";

// three.js loads only when this tab renders.
const IssLabScene = lazy(() => import("../lab/IssLabScene.jsx").then(m => ({ default: m.IssLabScene })));
const IDLE = { g: 0, o2: 21, flow: "fore", burnP: 0 };
const noop = () => {};

export function SimulationTab() {
  const api = useRef(null), clock = useRef(null);
  return (
    <section className="sim-layout">
      <ControlPanel />
      <div className="grid gap-3 content-start">
        <div className="glass lab3d">
          <div className="lab3d-view">
            <div className="lab3d-canvas">
              <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
                <IssLabScene params={IDLE} api={api} clockEl={clock} onEvent={noop} onReady={noop} />
              </Suspense>
            </div>
          </div>
        </div>
        <p className="note">
          The ISS lab module (8.5 m × 4.2 m) with its three air-return vent detectors. The model decides what the
          fire does; the 3D view only illustrates it.
        </p>
      </div>
    </section>
  );
}
