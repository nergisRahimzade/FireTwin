/* One-page layout: the large 3D simulation window (left / centre on desktop, top on mobile),
   with the Compare button the whiteboard puts above it.
   FE-06 alarm: when /detect says a detector trips, one timer fires at time_to_detect_s on the 10x
   demo clock; then that detector turns red in the scene and the alarm banner appears. With no
   detection, the banner shows DetectOut.note at once. No React state changes inside the 3D frame
   loop: the timer sets the alarm once, and the clock readout is plain DOM text. */
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { alarmAfterS, alarmBanner } from "../scene/alarmLogic";
import { SCENE_TIME_SCALE } from "../scene/smokeLogic";
import { useScenario } from "../store/useScenario";

// three.js loads only when the scene renders.
export const IssScene = lazy(() => import("../scene/IssScene").then(m => ({ default: m.IssScene })));

export function SceneView({ onCompare }: { onCompare: () => void }) {
  const detect = useScenario(s => s.detect);
  const simulate = useScenario(s => s.simulate);
  const ignition = useScenario(s => s.ignitions);
  const [alarmId, setAlarmId] = useState<string | null>(null);
  const clockEl = useRef<HTMLSpanElement | null>(null);
  const startedAt = useRef<number | null>(null);

  // Each new ignition (the store's counter, not the backend's scenario_id, which the mock reuses)
  // restarts the demo clock and clears the alarm. /apply keeps the clock running.
  const burning = simulate !== null;
  useEffect(() => {
    startedAt.current = burning ? performance.now() : null;
    setAlarmId(null);
  }, [ignition, burning]);

  // Each /detect result schedules (or cancels) the alarm.
  useEffect(() => {
    setAlarmId(null);
    const at = alarmAfterS(detect);
    if (at == null || !detect?.detector_id) return;
    const elapsed = startedAt.current == null ? 0 : (performance.now() - startedAt.current) / 1000;
    const id = detect.detector_id;
    const timer = window.setTimeout(() => setAlarmId(id), Math.max(0, (at - elapsed) * 1000));
    return () => window.clearTimeout(timer);
  }, [detect]);

  const banner = alarmBanner(detect, alarmId != null);
  return (
    <section className="area-scene" aria-label="3D simulation">
      <div className="glass lab3d">
        <div className="lab3d-view scene-large">
          <div className="lab3d-canvas">
            <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
              <IssScene detect={detect} simulate={simulate} alarmId={alarmId} clock={{ el: clockEl, startedAt }} ignition={ignition} />
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
