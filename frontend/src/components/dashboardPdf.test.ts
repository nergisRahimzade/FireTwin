import { describe, expect, it } from "vitest";
import type { SimulateOut, SuppressOut, TestRef } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import type { Session } from "../store/useScenario";
import { createResearchPdf } from "./dashboardPdf";
import { buildResearchReport, reportTimestamp } from "./sessionReport";

const start = Date.parse("2026-11-15T12:00:00.000Z");
const ref: TestRef = {
  test_id: "synthetic-test", investigation: "Synthetic investigation", fuel_type: "solid",
  o2_pct: 21, pressure_kpa: null, flow_cm_s: null, outcome: "burned",
  source_url: "https://example.test/synthetic-evidence", is_synthetic: true,
};
const initial: SimulateOut = {
  scenario_id: "synthetic-session", inputs: { ...DEFAULT_SCENARIO, material: "Synthetic material" },
  state: "burning", burn_probability: 0.9, spread_rate_mm_s: null, trust: "weak", extrapolated: true,
  nearest_tests: [ref], explanation: "Synthetic prediction fixture.",
};
const final: SimulateOut = {
  ...initial, inputs: { ...initial.inputs, flow_speed_cm_s: 0 }, state: "extinguished", burn_probability: 0.1,
};
const ranking: SuppressOut = {
  scenario_id: initial.scenario_id, recommended: "fans_off",
  actions: ["fans_off", "co2", "fans_off_co2", "cut_power", "water_mist"].map((action, i) => ({
    action: action as SuppressOut["actions"][number]["action"], label: action, new_inputs: final.inputs,
    extinction_probability: 0.9 - i * 0.1, crew_risk: i * 0.1, score: 0.8 - i * 0.1,
    data_support: "none", sources: [ref], explanation: "Synthetic ranking fixture, not a measurement.",
  })),
};
const session = (): Session => ({
  id: 1, startedAt: start, inputs: initial.inputs, history: [initial, final],
  detect: null, suppress: ranking, results: null, phase: "out", curve: null,
  events: [
    { kind: "simulate", at: start, result: initial },
    { kind: "suppress", at: start + 1000, inputs: initial.inputs, result: ranking },
    { kind: "apply", at: start + 2000, action: "fans_off", result: final },
    { kind: "suppress", at: start + 3000, inputs: final.inputs, result: { ...ranking, recommended: "co2" } },
  ],
});

describe("saved session research data", () => {
  it("freezes every session, all assessments and the exact results without mutating the store", () => {
    const saved = structuredClone([session(), { ...session(), id: 2 }]);
    const report = buildResearchReport(saved, start + 5000);
    saved[0].history[0].inputs.material = "Edited after export";
    saved[0].events = [];
    expect(report.sessions.map(s => s.id)).toEqual([1, 2]);
    expect(report.sessions[0].initial.inputs.material).toBe("Synthetic material");
    expect(report.sessions[0].rankings.map(r => r.result.recommended)).toEqual(["fans_off", "co2"]);
    expect(report.sessions[0].rankings[0].result.actions).toHaveLength(5);
    expect(report.sessions[0].rankings[0].inputs?.flow_speed_cm_s).toBe(10);
    expect(report.sessions[0].rankings[1].inputs?.flow_speed_cm_s).toBe(0);
    expect(report.sessions[0].final.burn_probability).toBe(0.1);
    expect(report.sessions[0].steps[report.sessions[0].steps.length - 1].at).toBe(start + 2000);
    expect(report.sessions[0].synthetic).toBe(true);
    expect(report.sessions[0].evidence).toEqual([ref]);
  });

  it("keeps older saved data and explicitly leaves unknown times and action names missing", () => {
    const old = session(); delete old.events;
    const report = buildResearchReport([old], start);
    expect(report.sessions[0].rankings[0].at).toBeNull();
    expect(report.sessions[0].rankings[0].inputs).toBeNull();
    expect(report.sessions[0].steps[1].at).toBeNull();
    expect(report.sessions[0].steps[1].action).toBeNull();
    expect(reportTimestamp(null)).toBe("Timestamp not recorded");
  });

  it("does not invent suppression options or evidence when none were saved", () => {
    const empty = { ...session(), events: undefined, suppress: null, history: [{ ...initial, nearest_tests: [] }] };
    const [report] = buildResearchReport([empty], start).sessions;
    expect(report.rankings).toEqual([]);
    expect(report.evidence).toEqual([]);
    expect(() => buildResearchReport([])).toThrow("Ignite a session");
  });
});

describe("research PDF", () => {
  it("contains selectable per-session values, outcomes, all suppression probabilities and linked evidence", async () => {
    const pdf = await createResearchPdf(buildResearchReport([session(), { ...session(), id: 2 }], start));
    const output = pdf.output();
    expect(output).toMatch(/^%PDF/);
    for (const text of ["SESSION 1", "SESSION 2", "Synthetic material", "90.0%", "10.0%", "water_mist", "co2", "SYNTHETIC", "OUTSIDE TESTED RANGE", "12:00:02.000 UTC", "EXTINGUISHED"]) {
      expect(output).toContain(text);
    }
    expect(output).toContain("/URI (https://example.test/synthetic-evidence)");
    expect(output).toContain("Crew risk");
    expect(output).toContain("Not recorded"); // missing measurement is not printed as zero
  });

  it("paginates long source text without dropping the final session or its footer", async () => {
    const long = structuredClone(session());
    long.history[0].explanation = "Long synthetic explanation. ".repeat(1500) + "END OF LONG EXPLANATION";
    const pdf = await createResearchPdf(buildResearchReport([long, { ...session(), id: 99 }], start));
    expect(pdf.getNumberOfPages()).toBeGreaterThan(4);
    expect(pdf.output()).toContain("END OF LONG EXPLANATION");
    expect(pdf.output()).toContain("SESSION 99");
    const pages = (pdf.internal as unknown as { pages: string[][] }).pages.slice(1);
    expect(pages.every(page => page.join("\n").includes("Flame is illustrative"))).toBe(true);
  });
});
