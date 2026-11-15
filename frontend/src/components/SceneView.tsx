/* One-page layout: the large 3D simulation window (left / centre on desktop, top on mobile),
   with the Compare button the whiteboard puts above it.
   FE-06 alarm: the store sets ignitedAt once per ignition and fires the alarm once (alarmId) at
   time_to_detect_s on the 10x demo clock. This view only reads them, so unmounting it (Compare)
   neither restarts the clock nor fires the alarm again. With no detection, the banner shows
   DetectOut.note at once. The clock readout is plain DOM text updated by the scene. */
import { Suspense, lazy, useRef } from "react";
import { alarmBanner } from "../scene/alarmLogic";
import { SCENE_TIME_SCALE } from "../scene/clock";
import { useScenario } from "../store/useScenario";

// three.js loads only when the scene renders.
export const IssScene = lazy(() => import("../scene/IssScene").then(m => ({ default: m.IssScene })));

export function SceneView({ onCompare }: { onCompare: () => void }) {
  const detect = useScenario(s => s.detect);
  const simulate = useScenario(s => s.simulate);
  const ignition = useScenario(s => s.ignitions);
  const ignitedAt = useScenario(s => s.ignitedAt);
  const alarmId = useScenario(s => s.alarmId);
  const clockEl = useRef<HTMLSpanElement | null>(null);

  const banner = alarmBanner(detect, alarmId != null);
  return (
    <section className="area-scene" aria-label="3D simulation">
      <div className="glass lab3d">
        <div className="lab3d-view scene-large">
          <div className="lab3d-canvas">
            <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
              <IssScene
                detect={detect} simulate={simulate} alarmId={alarmId}
                ignition={ignition} ignitedAt={ignitedAt} clockEl={clockEl}
              />
            </Suspense>
          </div>
          <div className="lab3d-hud">
            <button type="button" className="btn-ghost" onClick={onCompare}>Compare</button>
            {simulate && (
              <span className="clock mono">t = <span ref={clockEl}>0.0</span> s · {SCENE_TIME_SCALE}× speed</span>
            )}
          </div>
        </div>
      </div>
      {banner && (
        <div className="mt-3">
          <p role={banner.kind === "alarm" ? "alert" : "status"} className={banner.kind === "alarm" ? "alarm-banner" : "warn"}>
            {banner.text}
          </p>
        </div>
      )}
      <p className="note mt-2">
        ISS lab module, 8.5 m × 4.2 m. The model decides what the fire does and when the alarm trips; the 3D view
        only illustrates it.
      </p>
    </section>
  );
}
