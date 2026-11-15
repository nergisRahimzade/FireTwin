/* FE-09: pure helpers for the results dashboard. */
import type { MetaOut, ResultsRow, ScenarioIn, TestRef } from "../api/types";
import type { Session } from "../store/useScenario";
import { type Range, outsideKeys, testedRange, testedScope } from "./controlPanel.logic";

export const sourceId = (s: TestRef | string) => (typeof s === "string" ? s : s.test_id);

/** The "result" column: what this step found. */
export function resultText(r: ResultsRow): string {
  if (r.step === "detect") return r.detection_s == null ? "not detected" : `alarm after ${r.detection_s} s`;
  const p = r.probability == null ? "" : ` · ${Math.round(r.probability * 100)}% burn`;
  return `${r.state ?? "—"}${p}${r.trust ? ` · trust ${r.trust}` : ""}`;
}

/** The "variable changed" column: the action applied, or the inputs for the first prediction. */
export function changeText(r: ResultsRow): string {
  if (r.action) return `action: ${r.action}`;
  const i = r.inputs;
  return `${i.material}, ${i.o2_pct}% O₂, ${i.flow_speed_cm_s} cm/s`;
}

/** O2 values to sweep for the chart: 10 to 40 % in steps. */
export function o2Sweep(step = 5, lo = 10, hi = 40): number[] {
  const out: number[] = [];
  for (let v = lo; v <= hi + 1e-9; v += step) out.push(v);
  return out;
}

/** Keeps a time stamp for every row: rows seen before keep theirs, new rows get `now`. */
export function stampRows(prev: string[], count: number, now: string): string[] {
  return Array.from({ length: count }, (_, i) => prev[i] ?? now);
}

/** A session row's "values" column: what it was ignited with. */
export function sessionInputs(s: Session): string {
  const i = s.inputs;
  return `${i.material}, ${i.o2_pct}% O₂, ${i.flow_speed_cm_s} cm/s`;
}

/** A session row's "result" column: where it ended, and after how many actions. */
export function sessionOutcome(s: Session): string {
  const last = s.history[s.history.length - 1];
  const actions = s.history.length - 1;
  const after = actions ? ` · after ${actions} action${actions > 1 ? "s" : ""}` : "";
  return `${last.state} · ${Math.round(last.burn_probability * 100)}% burn${after}`;
}

// The model's burn threshold: P >= this means "keeps burning" (same as BURN_THRESHOLD in
// ml/pipeline/config.py). The chart draws it so readers see where burning turns into going out.
export const BURN_THRESHOLD = 0.5;

/** The O2 where the curve crosses the threshold (linear between points), or null if it never does. */
export function thresholdCrossing(curve: [number, number][], threshold = BURN_THRESHOLD): number | null {
  for (let i = 1; i < curve.length; i++) {
    const [o0, p0] = curve[i - 1];
    const [o1, p1] = curve[i];
    if ((p0 - threshold) * (p1 - threshold) <= 0 && p0 !== p1) {
      return o0 + ((threshold - p0) / (p1 - p0)) * (o1 - o0);
    }
  }
  return null;
}

/** Hover text for a NASA test dot: what the test was, and how it differs from this session. */
export function testDotLabel(t: TestRef, sessionFlow: number): string {
  const outcome = t.outcome === "burned" ? "kept burning" : t.outcome === "extinguished" ? "went out" : "no recorded outcome";
  const flow = t.flow_cm_s == null ? "airflow not recorded" : `${t.flow_cm_s} cm/s`;
  const differs = t.flow_cm_s != null && t.flow_cm_s !== sessionFlow ? ` (this session: ${sessionFlow} cm/s)` : "";
  return `${t.test_id} (${t.investigation}, ${t.fuel_type}): ${outcome} at ${t.o2_pct}% O₂, ${flow}${differs}`;
}

/** The recorded session sample merged into the sweep curve (replacing a point at the same O2),
    so the drawn line passes through the dot that shows this session's recorded probability. */
export function withSample(curve: [number, number][], sample: [number, number]): [number, number][] {
  return [...curve.filter(([o2]) => o2 !== sample[0]), sample].sort((a, b) => a[0] - b[0]);
}

export type Point = [number, number]; // [O2 %, burn probability]

/** Where the chart's line has NASA data behind it: the O2 range tested for this material's fuel
    type, or null when none of the line has (its airflow or pressure is already outside the tests,
    so every O2 on it is extrapolated). `scope` says whose tests, e.g. "solid fuels". */
export function chartTested(meta: MetaOut | null, inputs: ScenarioIn): { range: Range | null; scope: string } {
  const scope = testedScope(meta, inputs.material);
  const otherOutside = outsideKeys(inputs, meta).some(k => k !== "o2_pct");
  return { range: otherOutside ? null : testedRange(meta, "o2_pct", inputs.material), scope };
}

/** O2 values the chart asks the model about: every 2.5 % from 10 to 40, plus the edges of the
    tested range, so the solid (tested) part of the line starts and ends exactly on them. */
export function chartSweep(tested: Range | null): number[] {
  const edges = tested ? [tested.min, tested.max].filter(v => v > 10 && v < 40) : [];
  return [...new Set([...o2Sweep(2.5), ...edges])].sort((a, b) => a - b);
}

/** The line cut into runs: inside the tested O2 range (NASA data) or outside it (model only).
    A piece between two samples counts as tested only if both ends are inside the range, and
    neighbouring runs share their edge point so the drawn line has no gaps. */
export function splitCurve(curve: Point[], tested: Range | null): { points: Point[]; tested: boolean }[] {
  const inside = ([o2]: Point) => !!tested && o2 >= tested.min && o2 <= tested.max;
  if (curve.length === 1) return [{ points: curve, tested: inside(curve[0]) }];
  const runs: { points: Point[]; tested: boolean }[] = [];
  for (let i = 1; i < curve.length; i++) {
    const [a, b] = [curve[i - 1], curve[i]];
    const both = inside(a) && inside(b);
    const last = runs[runs.length - 1];
    if (last && last.tested === both) last.points.push(b);
    else runs.push({ points: [a, b], tested: both });
  }
  return runs;
}

/** NASA tests with a known outcome, one group per (O2, outcome): tests at the same O2 are one
    marker with a count instead of a stack of dots whose height would mean nothing. */
export function groupTests(tests: TestRef[]): { o2: number; outcome: "burned" | "extinguished"; tests: TestRef[] }[] {
  const groups = new Map<string, { o2: number; outcome: "burned" | "extinguished"; tests: TestRef[] }>();
  for (const t of tests) {
    if (t.o2_pct == null || (t.outcome !== "burned" && t.outcome !== "extinguished")) continue;
    const key = `${t.o2_pct}|${t.outcome}`;
    const group = groups.get(key) ?? { o2: t.o2_pct, outcome: t.outcome, tests: [] };
    group.tests.push(t);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => a.o2 - b.o2);
}

const pct = (p: number) => `${Math.round(p * 100)}%`;
const inRange = (o2: number, tested: Range | null) => !!tested && o2 >= tested.min && o2 <= tested.max;

/** The chart's one-line answer: where the model says this fire goes out, and whether NASA tests
    back that point. `boundary` is the threshold crossing (null = the line never crosses it). */
export function chartTakeaway(curve: Point[], boundary: number | null, inputs: ScenarioIn, tested: Range | null): string {
  const at = `${inputs.material} at ${inputs.flow_speed_cm_s} cm/s`;
  if (boundary == null) {
    const burns = curve.length > 0 && curve[0][1] >= BURN_THRESHOLD;
    return `${at}: the model says it ${burns ? "keeps burning" : "goes out"} at every O₂ from 10% to 40%.`;
  }
  const backed = inRange(boundary, tested) ? "inside the NASA-tested range" : "outside the NASA-tested range, so model only";
  return `${at}: the model says it goes out below about ${boundary.toFixed(1)}% O₂ (${backed}).`;
}

/** Hover text for one point of the line. */
export function pointLabel([o2, p]: Point, tested: Range | null): string {
  return `${o2}% O₂ → ${pct(p)} burn · ${inRange(o2, tested) ? "NASA-tested" : "model only"}`;
}

/** Hover text for a NASA test marker: every test in it, with how each differs from this session. */
export function testGroupLabel(group: { o2: number; outcome: string; tests: TestRef[] }, sessionFlow: number): string {
  return group.tests.map(t => testDotLabel(t, sessionFlow)).join("\n");
}

/** The curve point nearest an O2 value (for the hover crosshair). */
export function nearestPoint(curve: Point[], o2: number): number {
  let best = 0;
  curve.forEach(([x], i) => { if (Math.abs(x - o2) < Math.abs(curve[best][0] - o2)) best = i; });
  return best;
}
