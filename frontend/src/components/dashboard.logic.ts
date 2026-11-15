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
