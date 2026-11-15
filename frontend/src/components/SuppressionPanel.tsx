/* FE-08 (core feature): ranked suppression actions. Calls /suppress as soon as the alarm trips (or
   on "Rank actions" for a fire no vent detects), then lists each action: label, extinction
   probability bar, crew risk, data-support badge, explanation and NASA sources. "Apply" calls
   /apply; the new verdict replaces the old one, and the 3D flame fades out if the fire goes out.
   The recommended action is highlighted. */
import { useEffect, useState } from "react";
import type { ActionName } from "../api/types";
import { useScenario } from "../store/useScenario";
import { Sources } from "./Sources";
import { canAct, shouldAutoRank } from "./suppression.logic";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export function SuppressionPanel() {
  const suppress = useScenario(s => s.suppress);
  const simulate = useScenario(s => s.simulate);
  const alarmId = useScenario(s => s.alarmId);
  const phase = useScenario(s => s.phase);
  const loading = useScenario(s => s.loading);
  const runSuppress = useScenario(s => s.runSuppress);
  const runApply = useScenario(s => s.runApply);
  const [applyingAction, setApplyingAction] = useState<ActionName | null>(null);

  const viewingPast = useScenario(s => s.viewing !== null);

  useEffect(() => {
    if (shouldAutoRank(alarmId, suppress != null, loading.suppress, viewingPast)) void runSuppress();
  }, [alarmId, suppress, loading.suppress, viewingPast, runSuppress]);

  // A saved session is read-only: its ranking is shown, but Rank and Apply act on the live fire only.
  const actable = canAct(phase) && !viewingPast;
  return (
    <section className="area-recs glass panel" aria-label="Suppression recommendations">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="panel-title m-0">Suppression recommendations</h2>
        {simulate && actable && !suppress && (
          <button type="button" className="btn-ghost" disabled={loading.suppress} onClick={() => void runSuppress()}>
            {loading.suppress ? "Ranking…" : "Rank actions"}
          </button>
        )}
      </div>
      {suppress?.actions.length ? (
        <ol className="recs-list">
          {suppress.actions.map(a => (
            <li key={a.action} className={`rec ${a.action === suppress.recommended ? "recommended" : ""}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <strong>{a.label}{a.action === suppress.recommended ? " · recommended" : ""}</strong>
                <button
                  type="button" className="btn-primary" disabled={!actable || loading.apply}
                  onClick={async () => {
                    setApplyingAction(a.action);
                    try { await runApply(a.action); }
                    finally { setApplyingAction(null); }
                  }}
                >
                  {loading.apply && applyingAction === a.action ? "Applying..." : "Apply"}
                </button>
              </div>
              <div className="bar" aria-label={`Extinction probability ${pct(a.extinction_probability)}`}>
                <i style={{ width: pct(a.extinction_probability) }} />
              </div>
              <div className="flex flex-wrap gap-3 mono">
                <span>{pct(a.extinction_probability)} extinction</span>
                <span>crew risk {pct(a.crew_risk)}</span>
                <span className={`badge support-${a.data_support}`}>data: {a.data_support}</span>
              </div>
              <p className="note">{a.explanation}</p>
              <Sources sources={a.sources} />
            </li>
          ))}
        </ol>
      ) : (
        <p className="note m-0">
          {loading.suppress ? "Ranking actions…" : "Ranked actions (fans off, cut power, CO₂, water mist) appear here once the alarm trips."}
        </p>
      )}
    </section>
  );
}
