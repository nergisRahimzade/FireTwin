import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { ControlPanel } from "../components/ControlPanel";
import { SCENE_TIME_SCALE, alarmMessage } from "../scene/sceneLogic";
import { useScenario } from "../store/useScenario";

// three.js loads only when this tab renders.
const IssScene = lazy(() => import("../scene/IssScene").then(m => ({ default: m.IssScene })));

export function SimulationTab() {
  const simulate = useScenario(s => s.simulate);
  const detect = useScenario(s => s.detect);
  const clockEl = useRef<HTMLSpanElement | null>(null);
  const [alarmId, setAlarmId] = useState<string | null>(null);

  // A new scenario or a new /detect result clears the alarm until the clock reaches it again.
  const scenarioId = simulate?.scenario_id ?? null;
  useEffect(() => setAlarmId(null), [scenarioId, detect]);
  const banner = alarmMessage(detect, alarmId != null);

  return (
    <section className="sim-layout">
      <ControlPanel />
      <div className="grid gap-3 content-start">
        <div className="glass lab3d">
          <div className="lab3d-view">
            <div className="lab3d-canvas">
              <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
                <IssScene simulate={simulate} detect={detect} alarmId={alarmId} clockEl={clockEl} onAlarm={setAlarmId} />
              </Suspense>
            </div>
            {simulate && (
              <div className="lab3d-hud">
                <span className="clock mono">t = <span ref={clockEl}>0.0</span> s · {SCENE_TIME_SCALE}× speed</span>
              </div>
            )}
          </div>
        </div>
        {banner && (
          <p role={banner.kind === "alarm" ? "alert" : "status"} className={banner.kind === "alarm" ? "alarm-banner" : "warn"}>
            {banner.text}
          </p>
        )}
        <p className="note">
          The ISS lab module (8.5 m × 4.2 m). The model decides what the fire does and when the alarm trips; the 3D
          view only illustrates it. Detectors appear where the API places them.
        </p>
      </div>
    </section>
  );
}
