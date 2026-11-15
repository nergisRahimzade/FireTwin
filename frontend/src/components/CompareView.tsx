/* Compare mode: the 3D simulation (left) beside the FLEX-2 reference video (right). */
import { Suspense, useEffect } from "react";
import { useLiveScene } from "../scene/livePreview";
import { useScenario } from "../store/useScenario";
import { IssScene } from "./SceneView";
import { ValidationReference } from "./ValidationReference";

export function CompareView({ onClose }: { onClose: () => void }) {
  const detect = useScenario(s => s.detect);
  const simulate = useScenario(s => s.simulate);
  // Same ignition, clock and alarm as the main view (FE-06), so a tripped detector stays red here
  // and the smoke shows where the fire is now, not from the start.
  const ignition = useScenario(s => s.ignitions);
  const ignitedAt = useScenario(s => s.ignitedAt);
  const alarmId = useScenario(s => s.alarmId);
  const inputs = useScenario(s => s.inputs);
  const { scene, previewing } = useLiveScene(simulate, inputs);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rows: [string, string][] = [
    ["Material", inputs?.material || "—"],
    ["Oxygen", `${inputs?.o2_pct ?? "—"} %`],
    ["Airflow", `${inputs?.flow_speed_cm_s ?? "—"} cm/s`],
    ["Pressure", `${inputs?.pressure_kpa ?? "—"} kPa`],
  ];
  return (
    <section className="compare-view" role="dialog" aria-modal="true" aria-label="Compare">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">Compare</h2>
        <button type="button" className="btn-ghost" onClick={onClose}>Back to simulation</button>
      </header>
      {previewing && (
        <p className="note" role="status">
          Preview of new settings · Ignite again to record. The alarm belongs to the recorded scenario.
        </p>
      )}
      <div className="compare-panes">
        <div className="glass lab3d">
          <div className="lab3d-view">
            <div className="lab3d-canvas">
              <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
                <IssScene detect={detect} simulate={scene} alarmId={alarmId} ignition={ignition} ignitedAt={ignitedAt} />
              </Suspense>
            </div>
          </div>
        </div>
        <ValidationReference />
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Variable</th><th>Your scenario</th></tr></thead>
          <tbody>
            {rows.map(([name, value]) => (
              <tr key={name}><td>{name}</td><td className="mono">{value}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
