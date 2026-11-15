/* One-page layout: the large 3D simulation window (left / centre on desktop, top on mobile),
   with the Compare button the whiteboard puts above it. */
import { Suspense, lazy } from "react";
import { useScenario } from "../store/useScenario";

// three.js loads only when the scene renders.
export const IssScene = lazy(() => import("../scene/IssScene").then(m => ({ default: m.IssScene })));

export function SceneView({ onCompare }: { onCompare: () => void }) {
  const detect = useScenario(s => s.detect);
  const simulate = useScenario(s => s.simulate);
  return (
    <section className="area-scene" aria-label="3D simulation">
      <div className="glass lab3d">
        <div className="lab3d-view scene-large">
          <div className="lab3d-canvas">
            <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
              <IssScene detect={detect} simulate={simulate} />
            </Suspense>
          </div>
          <div className="lab3d-hud">
            <button type="button" className="btn-ghost" onClick={onCompare}>Compare</button>
          </div>
        </div>
      </div>
      <p className="note mt-2">
        ISS lab module, 8.5 m × 4.2 m. The model decides what the fire does; the 3D view only illustrates it.
      </p>
    </section>
  );
}
