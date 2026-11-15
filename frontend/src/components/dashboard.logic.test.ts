import { describe, expect, it } from "vitest";
import type { ResultsRow } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import {
  changeText, o2Sweep, resultText, sessionInputs, sessionOutcome, sourceId, stackIndex, stampRows, testDotLabel,
  thresholdCrossing, withSample,
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

  it("stacks dots that share an O2 value instead of moving them", () => {
    expect(stackIndex([30, 30, 30, 21, 30])).toEqual([0, 1, 2, 0, 3]);
  });
});
