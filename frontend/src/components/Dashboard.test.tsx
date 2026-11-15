// FE-09 chart, rendered: the plotted coordinates match the measured and recorded values.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import { DEFAULT_SCENARIO, type SimulateOut, type TestRef } from "../api/types";
import type { Session } from "../store/useScenario";
import { Dashboard } from "./Dashboard";

const view = vi.hoisted(() => ({ state: {} as Record<string, unknown> }));
vi.mock("../store/useScenario", () => ({
  useScenario: (select: (state: Record<string, unknown>) => unknown) => select(view.state),
}));
vi.mock("./dashboardPdf", () => ({ downloadDashboardPdf: () => Promise.resolve() }));

const inputs = { ...DEFAULT_SCENARIO, material: "Methanol", o2_pct: 27.5, flow_speed_cm_s: 0 };
const test = (id: string, o2: number, outcome: "burned" | "extinguished"): TestRef => ({
  test_id: id, investigation: "FLEX", fuel_type: "droplet", o2_pct: o2, pressure_kpa: null, flow_cm_s: 0,
  outcome, source_url: "", is_synthetic: false,
});
// Recorded at ignition: 24.108 %. The coarse sweep would interpolate 25.45 % at 27.5 % O2.
const recorded: SimulateOut = {
  scenario_id: "s1", state: "extinguished", burn_probability: 0.24108, spread_rate_mm_s: null, trust: "weak",
  extrapolated: false, explanation: "", inputs,
  nearest_tests: [test("A", 30, "burned"), test("B", 30, "burned"), test("C", 30, "burned"), test("D", 30, "extinguished")],
};
const session: Session = {
  id: 1, startedAt: 0, inputs, history: [recorded], detect: null, suppress: null, results: null, phase: "out",
  curve: [[10, 0.01], [15, 0.03], [20, 0.08], [25, 0.17], [30, 0.3373], [35, 0.6], [40, 0.8]],
};

beforeEach(() => {
  view.state = {
    simulate: recorded, history: [recorded], detect: null, results: null, timeline: [], sessions: [session],
    viewing: null, liveSession: 1, loading: { results: false },
    loadResults: () => {}, viewSession: () => {}, viewLive: () => {}, clearHistory: () => {}, setSessionCurve: () => {},
  };
});

const circles = (html: string, cls: string) =>
  [...html.matchAll(new RegExp(`<circle cx="([\\d.]+)" cy="([\\d.]+)" r="[\\d.]+" class="${cls}"`, "g"))]
    .map(m => ({ cx: Number(m[1]), cy: Number(m[2]) }));

it("keeps every NASA test at its measured O2 and stacks repeats vertically", () => {
  const html = renderToStaticMarkup(<Dashboard />);
  const burned = circles(html, "pt-burned");
  const out = circles(html, "pt-out");
  expect(burned).toHaveLength(3);
  expect(new Set(burned.map(c => c.cx)).size).toBe(1); // all at exactly 30 % O2
  expect(new Set(burned.map(c => c.cy)).size).toBe(3); // stacked, not overlapping
  expect(out[0].cx).toBe(burned[0].cx); // the extinguished test at 30 % lines up too
});

it("plots this session at its recorded ignition probability, not an interpolated one", () => {
  const html = renderToStaticMarkup(<Dashboard />);
  const [point] = circles(html, "pt-session");
  const [testAt30] = circles(html, "pt-out");
  // Chart frame from Dashboard: y(p) = 156 - p * 142, x(o2) = 34 + (o2 - 10) / 30 * 290.
  expect(point.cy).toBeCloseTo(156 - 0.24108 * 142, 1);
  expect(point.cx).toBeCloseTo(34 + ((27.5 - 10) / 30) * 290, 1);
  expect(point.cx).toBeLessThan(testAt30.cx);
  expect(html).toContain("24% burn probability (recorded at ignition)");
});
