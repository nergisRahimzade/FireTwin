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

// Chart frame from Dashboard: x(o2) = 60 + (o2 - 10) / 30 * 408, y(p) = 150 - p * 126; the NASA
// strip's rows sit under the plot at y 212 (burned) and 230 (went out).
const x = (o2: number) => 60 + ((o2 - 10) / 30) * 408;
const y = (p: number) => 150 - p * 126;

it("keeps every NASA test at its measured O2; repeats are one marker with a count", () => {
  const html = renderToStaticMarkup(<Dashboard />);
  const burned = circles(html, "pt-burned");
  const out = circles(html, "pt-out");
  expect(burned).toEqual([{ cx: x(30), cy: 212 }]); // A, B and C: one marker at exactly 30 % O2...
  expect(html).toContain("×3"); // ...that says how many tests it stands for
  expect(out).toEqual([{ cx: x(30), cy: 230 }]); // D went out at 30 %: same x, its own row
});

it("plots this session at its recorded ignition probability, not an interpolated one", () => {
  const html = renderToStaticMarkup(<Dashboard />);
  const [point] = circles(html, "pt-session");
  expect(point.cy).toBeCloseTo(y(0.24108), 1);
  expect(point.cx).toBeCloseTo(x(27.5), 1);
  expect(html).toContain("this session: 27.5% → 24%");
});

it("says where the fire goes out, and draws untested O2 as model only", () => {
  // No /meta in this view, so no tested range is known: the whole line is drawn as model only.
  const html = renderToStaticMarkup(<Dashboard />);
  expect(html).toMatch(/Methanol at 0 cm\/s: the model says it goes out below about 3\d\.\d% O₂ \(outside the NASA-tested range, so model only\)/);
  expect(html).not.toContain('class="curve"');
  expect(html).toContain('class="curve curve-model-only"');
});
