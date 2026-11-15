import { describe, expect, it } from "vitest";
import type { ResultsRow } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import type { MetaOut, TestRef } from "../api/types";
import {
  changeText, chartSweep, chartTakeaway, chartTested, groupTests, nearestPoint, o2Sweep, pointLabel, resultText,
  sessionInputs, sessionOutcome, sourceId, splitCurve, stampRows, testDotLabel, thresholdCrossing, withSample,
} from "./dashboard.logic";

const row = (patch: Partial<ResultsRow>): ResultsRow => ({
  step: "simulate", inputs: { ...DEFAULT_SCENARIO, material: "PMMA", o2_pct: 21, flow_speed_cm_s: 10 },
  state: "burning", probability: 0.93, trust: "medium", detection_s: null, action: null, sources: [], ...patch,
});

describe("dashboard rows", () => {
  it("describes a prediction, a detection and an applied action", () => {
    expect(resultText(row({}))).toBe("burning · 93% burn · trust medium");
    expect(resultText(row({ step: "detect", state: null, probability: null, trust: null, detection_s: 40 }))).toBe("alarm after 40 s");
    expect(resultText(row({ step: "detect", state: null, probability: null, trust: null }))).toBe("not detected");
    expect(changeText(row({}))).toBe("PMMA, 21% O₂, 10 cm/s");
    expect(changeText(row({ step: "apply", action: "fans_off" }))).toBe("action: fans_off");
  });

  it("reads sources sent as ids or as test refs", () => {
    expect(sourceId("SYN-1")).toBe("SYN-1");
    expect(sourceId({ test_id: "T-2" } as never)).toBe("T-2");
  });

  it("sweeps O2 from 10 to 40 %", () => {
    expect(o2Sweep()).toEqual([10, 15, 20, 25, 30, 35, 40]);
  });

  it("keeps old time stamps and stamps new rows", () => {
    expect(stampRows(["a"], 3, "b")).toEqual(["a", "b", "b"]);
    expect(stampRows(["a", "b"], 0, "c")).toEqual([]);
  });
});

describe("session rows", () => {
  const base = {
    id: 1, startedAt: 0, detect: null, suppress: null, results: null, phase: "out" as const, curve: null,
    inputs: { ...DEFAULT_SCENARIO, material: "Methanol", o2_pct: 30, flow_speed_cm_s: 26 },
  };
  const pred = (state: "burning" | "extinguished", p: number) => ({
    scenario_id: "s1", state, burn_probability: p, spread_rate_mm_s: null, trust: "weak" as const,
    extrapolated: false, nearest_tests: [], explanation: "", inputs: base.inputs,
  });

  it("shows the values a session was ignited with", () => {
    expect(sessionInputs({ ...base, history: [pred("burning", 0.9)] })).toBe("Methanol, 30% O₂, 26 cm/s");
  });

  it("shows where it ended and how many actions it took", () => {
    expect(sessionOutcome({ ...base, history: [pred("extinguished", 0.35)] })).toBe("extinguished · 35% burn");
    expect(sessionOutcome({ ...base, history: [pred("burning", 0.9), pred("extinguished", 0.1)] }))
      .toBe("extinguished · 10% burn · after 1 action");
  });
});

describe("chart helpers", () => {
  const curve: [number, number][] = [[10, 0.02], [15, 0.05], [20, 0.1], [25, 0.2], [30, 0.4], [35, 0.6], [40, 0.8]];

  it("finds the O2 where the curve crosses the 50% burn threshold", () => {
    expect(thresholdCrossing(curve)).toBeCloseTo(32.5);
    expect(thresholdCrossing([[10, 0.9], [40, 0.95]])).toBeNull(); // burns everywhere: no boundary
  });

  it("adds the recorded session sample to the curve, replacing a sweep point at the same O2", () => {
    expect(withSample([[25, 0.17], [30, 0.34]], [27.5, 0.241])).toEqual([[25, 0.17], [27.5, 0.241], [30, 0.34]]);
    expect(withSample([[25, 0.17], [30, 0.34]], [30, 0.33])).toEqual([[25, 0.17], [30, 0.33]]);
  });

  it("explains a test dot, including a different airflow", () => {
    const t = { test_id: "FLEX-29", investigation: "FLEX", fuel_type: "droplet", o2_pct: 30, pressure_kpa: null,
      flow_cm_s: 0, outcome: "burned" as const, source_url: "", is_synthetic: false };
    expect(testDotLabel(t, 26)).toBe("FLEX-29 (FLEX, droplet): kept burning at 30% O₂, 0 cm/s (this session: 26 cm/s)");
    expect(testDotLabel({ ...t, flow_cm_s: 26, outcome: "extinguished" }, 26)).toBe("FLEX-29 (FLEX, droplet): went out at 30% O₂, 26 cm/s");
  });

});

// The real solid-fuel numbers: Black rod at 26 % O2 is outside the 14.2-22.2 % solid tests.
const meta: MetaOut = {
  materials: [{ name: "Black rod", fuel_type: "solid", n_tests: 37 }],
  ranges: { o2_pct: { min: 12, max: 34 }, pressure_kpa: { min: 70.17, max: 309.27 }, flow_cm_s: { min: 0, max: 28 } },
  ranges_by_fuel_type: {
    solid: { o2_pct: { min: 14.2, max: 22.2 }, pressure_kpa: { min: 101.3, max: 101.3 }, flow_cm_s: { min: 0, max: 28 } },
  },
  investigations: [],
};
const blackRod = { ...DEFAULT_SCENARIO, material: "Black rod", o2_pct: 26, flow_speed_cm_s: 16 };
const test = (id: string, o2: number, outcome: TestRef["outcome"]): TestRef => ({
  test_id: id, investigation: "BASS-II", fuel_type: "solid", o2_pct: o2, pressure_kpa: null, flow_cm_s: 20,
  outcome, source_url: "", is_synthetic: false,
});

describe("O2 chart: what has NASA data behind it", () => {
  it("uses the material's own tested O2 range", () => {
    expect(chartTested(meta, blackRod)).toEqual({ range: { min: 14.2, max: 22.2 }, scope: "solid fuels" });
  });
  it("has no tested range when the airflow itself is outside the tests", () => {
    expect(chartTested(meta, { ...blackRod, flow_speed_cm_s: 35 }).range).toBeNull();
  });
  it("samples the tested range's edges so the solid part starts and ends on them", () => {
    const sweep = chartSweep({ min: 14.2, max: 22.2 });
    expect(sweep).toContain(14.2);
    expect(sweep).toContain(22.2);
    expect(sweep[0]).toBe(10);
    expect(sweep[sweep.length - 1]).toBe(40);
    expect(chartSweep(null)).toEqual(o2Sweep(2.5));
  });
  it("splits the line into tested and model-only runs that share their edge points", () => {
    const runs = splitCurve([[10, 0.3], [14.2, 0.5], [20, 0.8], [22.2, 0.85], [30, 0.95]], { min: 14.2, max: 22.2 });
    expect(runs.map(r => r.tested)).toEqual([false, true, false]);
    expect(runs[0].points).toEqual([[10, 0.3], [14.2, 0.5]]); // 10 -> 14.2 is mostly untested: dashed
    expect(runs[1].points).toEqual([[14.2, 0.5], [20, 0.8], [22.2, 0.85]]);
    expect(runs[2].points).toEqual([[22.2, 0.85], [30, 0.95]]);
  });
  it("draws everything as model-only when nothing is tested", () => {
    expect(splitCurve([[10, 0.3], [40, 0.9]], null)).toEqual([{ points: [[10, 0.3], [40, 0.9]], tested: false }]);
  });
});

describe("O2 chart: NASA test markers", () => {
  it("groups tests at the same O2 and outcome into one marker with a count", () => {
    const groups = groupTests([test("M2", 22.2, "burned"), test("M5", 22.2, "burned"), test("01", 22.2, "burned")]);
    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({ o2: 22.2, outcome: "burned" });
    expect(groups[0].tests.map(t => t.test_id)).toEqual(["M2", "M5", "01"]);
  });
  it("keeps burned and went-out tests apart and skips tests with no outcome or no O2", () => {
    const groups = groupTests([test("a", 18, "extinguished"), test("b", 18, "burned"), test("c", 19, "unknown"), { ...test("d", 0, "burned"), o2_pct: null }]);
    expect(groups.map(g => [g.o2, g.outcome])).toEqual([[18, "extinguished"], [18, "burned"]]);
  });
});

describe("O2 chart: words", () => {
  it("says where the fire goes out and whether NASA tests back that point", () => {
    expect(chartTakeaway([[10, 0.3], [20, 0.8]], 13.3, blackRod, { min: 14.2, max: 22.2 })).toBe(
      "Black rod at 16 cm/s: the model says it goes out below about 13.3% O₂ (outside the NASA-tested range, so model only).",
    );
    expect(chartTakeaway([[10, 0.3], [20, 0.8]], 16, blackRod, { min: 14.2, max: 22.2 })).toMatch(/inside the NASA-tested range\)\.$/);
  });
  it("says so when the line never crosses 50%", () => {
    expect(chartTakeaway([[10, 0.6], [40, 0.99]], null, blackRod, null)).toMatch(/keeps burning at every O₂ from 10% to 40%/);
  });
  it("labels each hovered point as tested or model only", () => {
    expect(pointLabel([20, 0.754], { min: 14.2, max: 22.2 })).toBe("20% O₂ → 75% burn · NASA-tested");
    expect(pointLabel([30, 0.95], { min: 14.2, max: 22.2 })).toBe("30% O₂ → 95% burn · model only");
  });
  it("finds the curve point nearest the pointer", () => {
    expect(nearestPoint([[10, 0], [12.5, 0], [15, 0]], 13.4)).toBe(1);
  });
});
