/* FE-09: the results dashboard under the 3D view.
   Sessions: every Ignite adds a row under the earlier ones (values, result, start time). Clicking a
   past session shows it read-only: its saved results, its values in the controls and a 3D replay;
   Ignite then runs those values again as a new session. "Clear history" drops past sessions.
   Steps: the shown session's rows from GET /results (live) or its saved copy (past), with the
   whiteboard's columns. The chart shows burn probability across O2 for the shown session, fetched
   once per session with /preview (no scenario or history row is created on the server).
   Export PDF downloads the dashboard. */
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { TestRef } from "../api/types";
import { type Session, useScenario } from "../store/useScenario";
import { downloadDashboardPdf } from "./dashboardPdf";
import {
  BURN_THRESHOLD, changeText, o2Sweep, resultText, sessionInputs, sessionOutcome, sourceId, stackIndex,
  stampRows, testDotLabel, thresholdCrossing, withSample,
} from "./dashboard.logic";

function O2Chart({ session }: { session: Session }) {
  const setSessionCurve = useScenario(s => s.setSessionCurve);

  useEffect(() => {
    if (session.curve) return; // fetched once per session, then kept with it
    let live = true;
    Promise.all(
      o2Sweep().map(o2 => api.preview({ ...session.inputs, o2_pct: o2 }).then(r => [o2, r.burn_probability] as [number, number])),
    )
      .then(points => { if (live) setSessionCurve(session.id, points); })
      .catch(() => { /* no curve this time; the next render of this session tries again */ });
    return () => { live = false; };
  }, [session.id, session.curve, session.inputs, setSessionCurve]);

  const sweep = session.curve ?? [];
  if (!sweep.length) return null;
  const { inputs } = session;
  // This session's own point is its recorded ignition probability (not read off the coarse sweep),
  // and the drawn curve includes that exact sample so the line passes through it.
  const recorded = session.history[0].burn_probability;
  const curve = withSample(sweep, [inputs.o2_pct, recorded]);
  // Plot area: 10-40 % O2 across, probability 0-1 up. Room on the right for the zone labels.
  const W = 420, H = 190, L = 34, R = W - 96, T = 14, B = H - 34;
  const x = (o2: number) => L + ((o2 - 10) / 30) * (R - L);
  const y = (p: number) => B - p * (B - T);
  const boundary = thresholdCrossing(curve);
  // NASA tests nearest to this session's settings, drawn at their own O2 in two labelled rows.
  const tested: TestRef[] = session.history[0].nearest_tests.filter(t => t.o2_pct != null && t.outcome !== "unknown");
  const rows = { burned: y(0.93), extinguished: y(0.07) };
  // Every dot stays at its measured O2. Tests sharing an O2 in the same row stack vertically
  // towards the middle of the chart (burned row downwards, extinguished row upwards).
  const STACK_PX = 10;
  const dotY = new Map<string, number>();
  for (const outcome of ["burned", "extinguished"] as const) {
    const row = tested.filter(t => t.outcome === outcome);
    const step = outcome === "burned" ? STACK_PX : -STACK_PX;
    stackIndex(row.map(t => t.o2_pct!)).forEach((n, i) => dotY.set(row[i].test_id, rows[outcome] + n * step));
  }
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="o2-chart" role="img" aria-label={`Burn probability across oxygen, session ${session.id}`}>
        {/* Zones split by the model's threshold: above keeps burning, below goes out. */}
        <rect x={L} y={T} width={R - L} height={y(BURN_THRESHOLD) - T} className="zone-burn" />
        <rect x={L} y={y(BURN_THRESHOLD)} width={R - L} height={B - y(BURN_THRESHOLD)} className="zone-out" />
        <line x1={L} y1={y(BURN_THRESHOLD)} x2={R} y2={y(BURN_THRESHOLD)} className="threshold" />
        <text x={R + 6} y={y(0.75)} className="tick">keeps burning</text>
        <text x={R + 6} y={y(0.25)} className="tick">goes out</text>
        <text x={R + 6} y={y(BURN_THRESHOLD) + 4} className="tick">50%</text>
        <line x1={L} y1={B} x2={R} y2={B} className="axis" />
        <line x1={L} y1={T} x2={L} y2={B} className="axis" />
        <polyline points={curve.map(([o, p]) => `${x(o)},${y(p)}`).join(" ")} className="curve" />
        {boundary != null && (
          <g>
            <line x1={x(boundary)} y1={T} x2={x(boundary)} y2={B} className="boundary" />
            <title>{`About ${boundary.toFixed(1)}% O₂: below this the model says the fire goes out at ${inputs.flow_speed_cm_s} cm/s`}</title>
          </g>
        )}
        {tested.map(t => (
          <circle key={t.test_id} cx={x(t.o2_pct!)} cy={dotY.get(t.test_id)!} r={4}
            className={t.outcome === "burned" ? "pt-burned" : "pt-out"}>
            <title>{testDotLabel(t, inputs.flow_speed_cm_s)}</title>
          </circle>
        ))}
        <circle cx={x(inputs.o2_pct)} cy={y(recorded)} r={5} className="pt-session">
          <title>{`This session: ${inputs.o2_pct}% O₂ → ${Math.round(recorded * 100)}% burn probability (recorded at ignition)`}</title>
        </circle>
        <text x={L} y={H - 18} className="tick">10% O₂</text>
        <text x={R - 34} y={H - 18} className="tick">40% O₂</text>
        <text x={2} y={T + 4} className="tick">100%</text>
        <text x={8} y={B} className="tick">0%</text>
      </svg>
      <figcaption className="note">
        Session {session.id}: the model's burn probability across O₂ at {inputs.flow_speed_cm_s} cm/s ({inputs.material}).
        Above the dashed 50% line the model says the fire keeps burning; below it, the fire goes out.
        {boundary != null
          ? ` At this airflow the line is crossed near ${boundary.toFixed(1)}% O₂ (dotted marker).`
          : ` At this airflow the curve stays on one side of the line between 10% and 40% O₂.`}
        {" "}The white dot is this session: {inputs.o2_pct}% O₂, {Math.round(recorded * 100)}% burn probability (recorded at ignition).
        Coloured dots are the NASA tests closest to these settings, each at its measured O₂ (tests at the same O₂ are stacked): <span className="pt-burned-text">top row = the test fire kept burning</span>,{" "}
        <span className="pt-out-text">bottom row = it went out</span>. They can come from other airflows or fuels; hover a dot for its details.
      </figcaption>
    </figure>
  );
}

export function Dashboard() {
  const dashboardRef = useRef<HTMLElement>(null);
  const scenarioId = useScenario(s => s.simulate?.scenario_id ?? null);
  const historyLen = useScenario(s => s.history.length);
  const detect = useScenario(s => s.detect);
  const results = useScenario(s => s.results);
  const loadingResults = useScenario(s => s.loading.results);
  const loadResults = useScenario(s => s.loadResults);
  const timeline = useScenario(s => s.timeline);
  const sessions = useScenario(s => s.sessions);
  const viewing = useScenario(s => s.viewing);
  const liveSession = useScenario(s => s.liveSession);
  const viewSession = useScenario(s => s.viewSession);
  const viewLive = useScenario(s => s.viewLive);
  const clearHistory = useScenario(s => s.clearHistory);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  // Step time stamps per session, so a past session keeps the times it was recorded at.
  const stamps = useRef<Record<number, string[]>>({});

  const shownId = viewing ?? liveSession;
  const shownSession = sessions.find(s => s.id === shownId) ?? null;

  useEffect(() => {
    if (scenarioId && viewing === null) void loadResults(); // past sessions show their saved rows
  }, [scenarioId, historyLen, detect, viewing, loadResults]);

  const rows = shownSession && results?.scenario_id === scenarioId ? results?.rows ?? [] : [];
  if (shownId !== null) {
    stamps.current[shownId] = stampRows(stamps.current[shownId] ?? [], rows.length, new Date().toLocaleString());
  }
  const stepStamps = shownId !== null ? stamps.current[shownId] ?? [] : [];
  const hasPast = sessions.some(s => s.id !== liveSession);

  return (
    <section ref={dashboardRef} className="area-dash glass panel" aria-label="Results dashboard">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="panel-title">Dashboard</h2>
        <div className="export-menu" role="group" aria-label="Dashboard actions">
          <button type="button" className="btn-ghost" disabled={!hasPast} onClick={clearHistory}>
            Clear history
          </button>
          <button
            type="button" className="btn-ghost" disabled={exporting}
            onClick={async () => {
              if (!dashboardRef.current) return;
              setExporting(true);
              setExportError(null);
              try { await downloadDashboardPdf(dashboardRef.current, timeline); }
              catch { setExportError("Could not export the dashboard PDF."); }
              finally { setExporting(false); }
            }}
          >
            {exporting ? "Creating PDF…" : "Export to PDF"}
          </button>
        </div>
      </div>
      {exportError && <p className="error" role="alert">{exportError}</p>}
      {viewing !== null && (
        <p className="warn" role="status">
          Showing saved session {viewing} (read-only), replaying in 3D. The controls now hold its values: Ignite runs them
          again as a new session.{" "}
          <button type="button" className="textbtn" onClick={viewLive}>
            {liveSession !== null ? "Back to live" : "Close"}
          </button>
        </p>
      )}

      <div className="table-wrap">
        <table aria-label="Sessions">
          <thead>
            <tr><th>Session</th><th>Values</th><th>Result</th><th>Started</th></tr>
          </thead>
          <tbody>
            {sessions.length ? sessions.map(s => (
              <tr key={s.id} className={`session-row ${s.id === shownId ? "selected" : ""}`} onClick={() => viewSession(s.id)}>
                <td className="mono">
                  <button type="button" className="textbtn" aria-pressed={s.id === shownId} onClick={e => { e.stopPropagation(); viewSession(s.id); }}>
                    {s.id}{s.id === liveSession ? " · live" : " · saved"}
                  </button>
                </td>
                <td>{sessionInputs(s)}</td>
                <td>{sessionOutcome(s)}</td>
                <td className="mono">{new Date(s.startedAt).toLocaleString()}</td>
              </tr>
            )) : (
              <tr><td colSpan={4} className="na">Every Ignite adds a session here; click one to see and replay it.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {shownSession && (
        <div className="table-wrap mt-3">
          <table aria-label={`Steps of session ${shownSession.id}`}>
            <thead>
              <tr><th>Step</th><th>Variable changed</th><th>Result</th><th>Sources</th><th>Date &amp; time</th></tr>
            </thead>
            <tbody>
              {rows.length ? rows.map((r, i) => (
                <tr key={i}>
                  <td className="mono">{i + 1}. {r.step}</td>
                  <td>{changeText(r)}</td>
                  <td>{resultText(r)}</td>
                  <td className="mono">{r.sources.map(sourceId).join(", ") || "—"}</td>
                  <td className="mono">{stepStamps[i]}</td>
                </tr>
              )) : loadingResults ? (
                <tr><td colSpan={5} className="na">Loading results...</td></tr>
              ) : (
                <tr><td colSpan={5} className="na">No steps recorded for this session.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {shownSession && <O2Chart session={shownSession} />}
    </section>
  );
}
