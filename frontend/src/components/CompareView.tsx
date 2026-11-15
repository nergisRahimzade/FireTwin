/* One-page layout: Compare mode, a full-screen view (no route change) with the 3D twin next to a
   reference example. Layout shell: the reference side is a placeholder until the team picks the
   footage or example (and how it works offline). Esc or "Back" returns to the simulation. */
import { Suspense, useEffect } from "react";
import { useScenario } from "../store/useScenario";
import { IssScene } from "./SceneView";

export function CompareView({ onClose }: { onClose: () => void }) {
  const detect = useScenario(s => s.detect);
  const simulate = useScenario(s => s.simulate);
  // Same ignition, clock and alarm as the main view (FE-06), so a tripped detector stays red here
  // and the smoke shows where the fire is now, not from the start.
  const ignition = useScenario(s => s.ignitions);
  const ignitedAt = useScenario(s => s.ignitedAt);
  const alarmId = useScenario(s => s.alarmId);
  const inputs = useScenario(s => s.inputs);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rows: [string, string][] = [
    ["Material", inputs.material || "—"],
    ["Oxygen", `${inputs.o2_pct} %`],
    ["Airflow", `${inputs.flow_speed_cm_s} cm/s`],
    ["Pressure", `${inputs.pressure_kpa} kPa`],
  ];
  return (
    <section className="compare-view" role="dialog" aria-modal="true" aria-label="Compare">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">Compare</h2>
        <button type="button" className="btn-ghost" onClick={onClose}>Back to simulation</button>
      </header>
      <div className="compare-panes">
        <div className="glass lab3d">
          <div className="lab3d-view">
            <div className="lab3d-canvas">
              <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
                <IssScene detect={detect} simulate={simulate} alarmId={alarmId} ignition={ignition} ignitedAt={ignitedAt} />
              </Suspense>
            </div>
          </div>
        </div>
        <div className="glass compare-reference">
          <p className="label">Reference example</p>
          <p className="note m-0">NASA footage or a reference test goes here, for side-by-side comparison.</p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Variable</th><th>Your scenario</th><th>Reference</th></tr></thead>
          <tbody>
            {rows.map(([name, value]) => (
              <tr key={name}><td>{name}</td><td className="mono">{value}</td><td className="na">—</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
