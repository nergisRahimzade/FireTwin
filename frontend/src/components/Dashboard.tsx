/* FE-09: the results dashboard under the 3D view.
   Sessions: every Ignite adds a row under the earlier ones (values, result, start time). Clicking a
   past session shows it read-only: its saved results, its values in the controls and a 3D replay;
   Ignite then runs those values again as a new session. "Clear history" drops past sessions.
   Steps: the shown session's rows from GET /results (live) or its saved copy (past), with the
   whiteboard's columns. The chart shows the model's burn probability across O2 for the shown
   session, fetched once per session with /preview (no scenario or history row is created on the
   server): solid where NASA tested that fuel's O2 range, dashed where the model extrapolates, and
   the nearest NASA tests in their own strip under the O2 axis.
   Export PDF downloads the dashboard. */
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { type Session, useScenario } from "../store/useScenario";
import { downloadDashboardPdf } from "./dashboardPdf";
import {
  BURN_THRESHOLD, type Point, changeText, chartSweep, chartTakeaway, chartTested, groupTests, nearestPoint, pointLabel,
  resultText, sessionInputs, sessionOutcome, sourceId, splitCurve, stampRows, testGroupLabel, thresholdCrossing, withSample,
} from "./dashboard.logic";

function O2Chart({ session }: { session: Session }) {
  const setSessionCurve = useScenario(s => s.setSessionCurve);
  const meta = useScenario(s => s.meta);
  const [hover, setHover] = useState<number | null>(null); // index into the curve; null = no crosshair
  const { inputs } = session;
  const { range: tested, scope } = chartTested(meta, inputs);

  useEffect(() => {
    if (session.curve) return; // fetched once per session, then kept with it
    let live = true;
    Promise.all(
      chartSweep(tested).map(o2 => api.preview({ ...inputs, o2_pct: o2 }).then(r => [o2, r.burn_probability] as Point)),
    )
      .then(points => { if (live) setSessionCurve(session.id, points); })
      .catch(() => { /* no curve this time; the next render of this session tries again */ });
    return () => { live = false; };
  }, [session.id, session.curve, inputs, tested?.min, tested?.max, setSessionCurve]); // tested?.min/max: the range object is rebuilt every render, its numbers aren't

  const sweep = session.curve ?? [];
  if (!sweep.length) return null;
  // This session's own point is its recorded ignition probability (not read off the sweep), and
  // the drawn line includes that exact sample so it passes through the dot.
  const recorded = session.history[0].burn_probability;
  const curve = withSample(sweep, [inputs.o2_pct, recorded]);
  const boundary = thresholdCrossing(curve);
  const groups = groupTests(session.history[0].nearest_tests);

  // Plot: 10-40 % O2 across, burn probability 0-100 % up. Below it: the O2 ticks, then a strip for
  // the nearest NASA tests, one row per outcome (their height on the plot would mean nothing).
  const W = 480, L = 60, R = W - 12, T = 24, B = 150, TICKS_Y = B + 16;
  const ROWS = { burned: B + 62, extinguished: B + 80 }, H = B + 92;
  const x = (o2: number) => L + ((o2 - 10) / 30) * (R - L);
  const y = (p: number) => B - p * (B - T);
  const shown = hover != null ? curve[hover] : null;
  // Pointer -> nearest curve point. The SVG scales with the page, so convert to viewBox units.
  const track = (e: React.PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    const vx = ((e.clientX - box.left) / box.width) * W;
    setHover(nearestPoint(curve, 10 + ((vx - L) / (R - L)) * 30));
  };
  // Arrow keys move the crosshair too, so keyboard users get the same readout.
  const key = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const from = hover ?? curve.findIndex(([o2]) => o2 === inputs.o2_pct);
    setHover(Math.max(0, Math.min(curve.length - 1, from + (e.key === "ArrowRight" ? 1 : -1))));
  };
  const youRight = x(inputs.o2_pct) > R - 110; // keep the "this session" label inside the plot

  return (
    <figure className="m-0 o2-figure">
      <p className="chart-takeaway">{chartTakeaway(curve, boundary, inputs, tested)}</p>
      <svg
        viewBox={`0 0 ${W} ${H}`} className="o2-chart" role="img" tabIndex={0} onKeyDown={key} onBlur={() => setHover(null)}
        aria-label={`Session ${session.id}: model burn probability across oxygen. ${chartTakeaway(curve, boundary, inputs, tested)} Use the arrow keys to read values.`}
      >
        <text x={L} y={12} className="axis-title">Burn probability</text>
        {/* The O2 range NASA tested for this fuel type: inside it the line has data behind it. */}
        {tested && (
          <g>
            <rect x={x(Math.max(10, tested.min))} y={T} width={Math.max(2, x(Math.min(40, tested.max)) - x(Math.max(10, tested.min)))} height={B - T} className="tested-band" />
            <text x={x(Math.max(10, tested.min)) + 4} y={T + 11} className="band-label">NASA-tested</text>
          </g>
        )}
        {[0, 0.5, 1].map(p => (
          <g key={p}>
            <line x1={L} y1={y(p)} x2={R} y2={y(p)} className={p === BURN_THRESHOLD ? "threshold" : "grid"} />
            <text x={L - 6} y={y(p) + 3} className="tick" textAnchor="end">{p * 100}%</text>
          </g>
        ))}
        <text x={R - 4} y={y(BURN_THRESHOLD) - 6} className="zone-label" textAnchor="end">↑ keeps burning</text>
        <text x={R - 4} y={y(BURN_THRESHOLD) + 14} className="zone-label" textAnchor="end">↓ goes out</text>
        {[10, 15, 20, 25, 30, 35, 40].map(o2 => (
          <text key={o2} x={x(o2)} y={TICKS_Y} className="tick" textAnchor="middle">{o2}</text>
        ))}
        <text x={R} y={TICKS_Y + 16} className="axis-title" textAnchor="end">O₂ (%)</text>
        {/* The model's line: solid where NASA tested this fuel, dashed where it extrapolates. */}
        {splitCurve(curve, tested).map((run, i) => (
          <polyline key={i} points={run.points.map(([o, p]) => `${x(o)},${y(p)}`).join(" ")} className={run.tested ? "curve" : "curve curve-model-only"} />
        ))}
        {boundary != null && (
          <g>
            <circle cx={x(boundary)} cy={y(BURN_THRESHOLD)} r={4} className="pt-boundary" />
            <text x={x(boundary) + (x(boundary) > R - 90 ? -6 : 6)} y={y(BURN_THRESHOLD) + 14} className="mark-label" textAnchor={x(boundary) > R - 90 ? "end" : "start"}>
              goes out below ≈{boundary.toFixed(1)}%
            </text>
          </g>
        )}
        <circle cx={x(inputs.o2_pct)} cy={y(recorded)} r={5} className="pt-session" />
        {/* Label below-right of the dot: the line rises with O2, so that side is clear of it
            (above it near the bottom of the plot, so the label stays inside). */}
        <text x={x(inputs.o2_pct) + (youRight ? -9 : 9)} y={y(recorded) + (recorded < 0.15 ? -9 : 17)} className="mark-label" textAnchor={youRight ? "end" : "start"}>
          this session: {inputs.o2_pct}% → {Math.round(recorded * 100)}%
        </text>
        {/* Nearest NASA tests at their measured O2: one row per outcome, filled = burned, ring =
            went out, and tests at the same O2 are one marker with a count. */}
        <text x={L} y={B + 46} className="axis-title">Nearest NASA tests</text>
        {(["burned", "extinguished"] as const).map(outcome => (
          <g key={outcome}>
            <text x={L - 6} y={ROWS[outcome] + 3} className="tick" textAnchor="end">{outcome === "burned" ? "burned" : "went out"}</text>
            <line x1={L} y1={ROWS[outcome]} x2={R} y2={ROWS[outcome]} className="grid" />
          </g>
        ))}
        {groups.map(g => (
          <g key={`${g.o2}-${g.outcome}`} className="test-group">
            <title>{testGroupLabel(g, inputs.flow_speed_cm_s)}</title>
            <circle cx={x(g.o2)} cy={ROWS[g.outcome]} r={4.5} className={g.outcome === "burned" ? "pt-burned" : "pt-out"} />
            {g.tests.length > 1 && <text x={x(g.o2) + 8} y={ROWS[g.outcome] + 3} className="tick">×{g.tests.length}</text>}
          </g>
        ))}
        {!groups.length && <text x={x(25)} y={ROWS.burned + 10} className="band-label" textAnchor="middle">no nearby test with a recorded outcome</text>}
        {/* Hover layer: crosshair + readout at the nearest point of the line. */}
        {shown && (
          <g className="crosshair" pointerEvents="none">
            <line x1={x(shown[0])} y1={T} x2={x(shown[0])} y2={B} />
            <circle cx={x(shown[0])} cy={y(shown[1])} r={4} />
            {/* Readout pinned top-right, clear of the "Burn probability" title on the left. */}
            <text x={R} y={T - 8} textAnchor="end" className="readout">
              {pointLabel(shown, tested)}
            </text>
          </g>
        )}
        <rect x={L} y={T} width={R - L} height={B - T} fill="transparent" onPointerMove={track} onPointerLeave={() => setHover(null)} />
      </svg>
      <figcaption className="chart-legend note">
        <span><i className="key key-line" /> model, NASA-tested O₂ ({tested ? `${tested.min}–${tested.max}% for ${scope}` : `none at ${inputs.flow_speed_cm_s} cm/s`})</span>
        <span><i className="key key-line-dashed" /> model only, no NASA data</span>
        <span><i className="key key-session" /> this session (recorded at ignition)</span>
        <span><i className="key key-burned" /> NASA test burned</span>
        <span><i className="key key-out" /> NASA test went out</span>
        <span className="muted">NASA markers are the 3 tests nearest this session; they may use another airflow or material (hover for details).</span>
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
