/* FE-09: pure helpers for the results dashboard. */
import type { ResultsRow, TestRef } from "../api/types";
import type { Session } from "../store/useScenario";

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

/** Burn probability on the curve at an O2 value (linear between points; clamped to the ends). */
export function curveAt(curve: [number, number][], o2: number): number | null {
  if (!curve.length) return null;
  if (o2 <= curve[0][0]) return curve[0][1];
  for (let i = 1; i < curve.length; i++) {
    const [o0, p0] = curve[i - 1];
    const [o1, p1] = curve[i];
    if (o2 <= o1) return p0 + ((o2 - o0) / (o1 - o0)) * (p1 - p0);
  }
  return curve[curve.length - 1][1];
}

/** Hover text for a NASA test dot: what the test was, and how it differs from this session. */
export function testDotLabel(t: TestRef, sessionFlow: number): string {
  const outcome = t.outcome === "burned" ? "kept burning" : t.outcome === "extinguished" ? "went out" : "no recorded outcome";
  const flow = t.flow_cm_s == null ? "airflow not recorded" : `${t.flow_cm_s} cm/s`;
  const differs = t.flow_cm_s != null && t.flow_cm_s !== sessionFlow ? ` (this session: ${sessionFlow} cm/s)` : "";
  return `${t.test_id} (${t.investigation}, ${t.fuel_type}): ${outcome} at ${t.o2_pct}% O₂, ${flow}${differs}`;
}

/** Small x offsets so dots at the same O2 in the same row don't hide each other. */
export function spreadDots(o2s: number[], gap = 1.2): number[] {
  const seen = new Map<number, number>();
  return o2s.map(o => {
    const n = seen.get(o) ?? 0;
    seen.set(o, n + 1);
    return o + (n % 2 ? -1 : 1) * Math.ceil(n / 2) * gap;
  });
}
