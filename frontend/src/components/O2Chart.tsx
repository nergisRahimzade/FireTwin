/* The O2 chart from the FE-09 dashboard, as a component that takes its data (Compare uses it for
   the video's test). The model's burn probability across O2 at one set of conditions: solid where
   NASA tested that fuel's O2 range, dashed where the model extrapolates, the threshold crossing,
   the subject's own point and, if given, the nearest NASA tests in a strip under the O2 axis.
   Follow-up: the dashboard still has its own copy; switch it to this one after the open PDF
   branch (which edits Dashboard.tsx) merges. */
import { type KeyboardEvent, type PointerEvent, useState } from "react";
import type { ScenarioIn, TestRef } from "../api/types";
import type { Range } from "./controlPanel.logic";
import {
  BURN_THRESHOLD, type Point, chartTakeaway, groupTests, nearestPoint, pointLabel, splitCurve, testGroupLabel,
  thresholdCrossing, withSample,
} from "./dashboard.logic";

export interface O2ChartProps {
  inputs: ScenarioIn; // the conditions the curve was computed at
  recorded: number; // the subject's own burn probability at inputs.o2_pct (drawn as the white dot)
  sweep: Point[]; // the model across O2 at those conditions
  tested: Range | null; // O2 range with NASA tests behind it; null = all model only
  scope: string; // whose tests, e.g. "droplet fuels"
  subject: string; // the white dot's label, e.g. "this session", "video's test"
  tests?: TestRef[]; // nearest NASA tests; undefined = no strip
}

export function O2Chart({ inputs, recorded, sweep, tested, scope, subject, tests }: O2ChartProps) {
  const [hover, setHover] = useState<number | null>(null); // index into the curve; null = no crosshair
  // The drawn line includes the subject's exact sample, so it passes through the dot.
  const curve = withSample(sweep, [inputs.o2_pct, recorded]);
  const boundary = thresholdCrossing(curve);
  const groups = tests ? groupTests(tests) : [];
  const takeaway = chartTakeaway(curve, boundary, inputs, tested);

  // Plot: 10-40 % O2 across, burn probability 0-100 % up; the tests strip (if any) under the ticks.
  const W = 480, L = 60, R = W - 12, T = 24, B = 150, TICKS_Y = B + 16;
  const ROWS = { burned: B + 62, extinguished: B + 80 }, H = tests ? B + 92 : B + 40;
  const x = (o2: number) => L + ((o2 - 10) / 30) * (R - L);
  const y = (p: number) => B - p * (B - T);
  const shown = hover != null ? curve[hover] : null;
  const track = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect(); // the SVG scales with the page
    setHover(nearestPoint(curve, 10 + ((((e.clientX - box.left) / box.width) * W - L) / (R - L)) * 30));
  };
  const key = (e: KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const from = hover ?? curve.findIndex(([o2]) => o2 === inputs.o2_pct);
    setHover(Math.max(0, Math.min(curve.length - 1, from + (e.key === "ArrowRight" ? 1 : -1))));
  };
  const dotRight = x(inputs.o2_pct) > R - 130; // keep the dot's label inside the plot
  const lo = tested ? Math.max(10, tested.min) : 10, hi = tested ? Math.min(40, tested.max) : 10;

  return (
    <figure className="m-0 o2-figure">
      <p className="chart-takeaway">{takeaway}</p>
      <svg
        viewBox={`0 0 ${W} ${H}`} className="o2-chart" role="img" tabIndex={0} onKeyDown={key} onBlur={() => setHover(null)}
        aria-label={`Model burn probability across oxygen. ${takeaway} Use the arrow keys to read values.`}
      >
        <text x={L} y={12} className="axis-title">Burn probability</text>
        {tested && (
          <g>
            <rect x={x(lo)} y={T} width={Math.max(2, x(hi) - x(lo))} height={B - T} className="tested-band" />
            <text x={x(lo) + 4} y={T + 11} className="band-label">NASA-tested</text>
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
        {/* Below-right of the dot: the line rises with O2, so that side is clear of it. */}
        <text x={x(inputs.o2_pct) + (dotRight ? -9 : 9)} y={y(recorded) + (recorded < 0.15 ? -9 : 17)} className="mark-label" textAnchor={dotRight ? "end" : "start"}>
          {subject}: {inputs.o2_pct}% → {Math.round(recorded * 100)}%
        </text>
        {tests && (
          <g>
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
          </g>
        )}
        {shown && (
          <g className="crosshair" pointerEvents="none">
            <line x1={x(shown[0])} y1={T} x2={x(shown[0])} y2={B} />
            <circle cx={x(shown[0])} cy={y(shown[1])} r={4} />
            <text x={R} y={T - 8} textAnchor="end" className="readout">{pointLabel(shown, tested)}</text>
          </g>
        )}
        <rect x={L} y={T} width={R - L} height={B - T} fill="transparent" onPointerMove={track} onPointerLeave={() => setHover(null)} />
      </svg>
      <figcaption className="chart-legend note">
        <span><i className="key key-line" /> model, NASA-tested O₂ ({tested ? `${tested.min}–${tested.max}% for ${scope}` : `none at ${inputs.flow_speed_cm_s} cm/s`})</span>
        <span><i className="key key-line-dashed" /> model only, no NASA data</span>
        <span><i className="key key-session" /> {subject}</span>
        {tests && <span><i className="key key-burned" /> NASA test burned</span>}
        {tests && <span><i className="key key-out" /> NASA test went out</span>}
      </figcaption>
    </figure>
  );
}
