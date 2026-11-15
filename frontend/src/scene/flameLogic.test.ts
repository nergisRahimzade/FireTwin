// FE-05: SimulateOut -> flame, plus a guard on the "no React state per frame" rule.
import { describe, expect, it } from "vitest";
import type { SimulateOut } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import { Flame as CoreFlame } from "../lab/core.js";
import { FADE_OUT_S, NO_FLAME, flameTarget, flowOf, stepLife } from "./flameLogic";

const sim = (over: Partial<SimulateOut> = {}, inputs: Partial<SimulateOut["inputs"]> = {}): SimulateOut => ({
  scenario_id: "s1", state: "burning", burn_probability: 0.8, spread_rate_mm_s: null, trust: "weak",
  extrapolated: false, nearest_tests: [], explanation: "", inputs: { ...DEFAULT_SCENARIO, ...inputs }, ...over,
});

describe("flameTarget", () => {
  it("shows no flame before ignition", () => {
    expect(flameTarget(null)).toEqual(NO_FLAME);
  });

  it("burns while the model says burning, and fades out when extinguished", () => {
    expect(flameTarget(sim()).alive).toBe(1);
    expect(flameTarget(sim({ state: "extinguished" })).alive).toBe(0);
  });

  it("passes burn_probability through, clamped to 0-1", () => {
    expect(flameTarget(sim({ burn_probability: 0.42 })).burnP).toBe(0.42);
    expect(flameTarget(sim({ burn_probability: 1.7 })).burnP).toBe(1);
  });

  it("grows with predicted spread, and stays normal size when spread is unknown", () => {
    expect(flameTarget(sim()).spreadScale).toBe(1);
    const slow = flameTarget(sim({ spread_rate_mm_s: 0.5 })).spreadScale;
    const fast = flameTarget(sim({ spread_rate_mm_s: 3 })).spreadScale;
    expect(slow).toBeGreaterThan(1);
    expect(fast).toBeGreaterThan(slow);
    expect(fast).toBeLessThanOrEqual(1.35);
  });

  it("is a sphere in still air and stretches along flow_dir as airflow rises", () => {
    expect(flameTarget(sim({}, { flow_speed_cm_s: 0 })).stretch).toBe(0);
    const t10 = flameTarget(sim({}, { flow_speed_cm_s: 10, flow_dir: [0, 0, -2] }));
    const t40 = flameTarget(sim({}, { flow_speed_cm_s: 40 }));
    expect(t10.stretch).toBeGreaterThan(0);
    expect(t40.stretch).toBeGreaterThan(t10.stretch);
    expect(t10.flowDir).toEqual([0, 0, -1]); // normalized
  });

  it("carries the extrapolation flag for the stripes and tag", () => {
    expect(flameTarget(sim({ extrapolated: true })).extrapolated).toBe(true);
  });
});

describe("flowOf", () => {
  it("treats a zero-length flow_dir as still air", () => {
    expect(flowOf({ ...DEFAULT_SCENARIO, flow_dir: [0, 0, 0], flow_speed_cm_s: 20 })).toEqual({ dir: [1, 0, 0], speedCmS: 0 });
  });
});

describe("stepLife and the 3D flame over time", () => {
  // Drives the real lab/core.js Flame at 60 fps the way Flame.tsx does in useFrame.
  function burnThenExtinguish() {
    const f = new CoreFlame(), dt = 1 / 60;
    let life = 0, t = 0;
    const step = (alive: 0 | 1) => { life = stepLife(life, alive, dt); t += dt; f.update(dt, t, { g: 0, o2: 21, burnP: 0.8, alive: life }); };
    for (let i = 0; i < 60; i++) step(1); // 1 s burning
    const burning = f.size;
    const sizes: Record<string, number> = {};
    for (let i = 1; i <= 180; i++) { step(0); if (i % 30 === 0) sizes[(i / 60).toFixed(1)] = f.size; }
    return { burning, sizes };
  }

  it("appears in well under a second", () => {
    expect(stepLife(0, 1, 0.4)).toBe(1);
  });

  it("shrinks steadily over ~2 s after extinguished, then is gone", () => {
    const { burning, sizes } = burnThenExtinguish();
    expect(burning).toBeGreaterThan(0.1);
    expect(sizes["0.5"]).toBeGreaterThan(burning * 0.5); // still clearly visible after 0.5 s
    expect(sizes["1.0"]).toBeLessThan(sizes["0.5"]);
    expect(sizes["1.5"]).toBeLessThan(sizes["1.0"]);
    expect(sizes["2.0"]).toBeLessThan(burning * 0.15); // essentially out at ~2 s
    expect(sizes["3.0"]).toBeLessThan(0.005);
    expect(FADE_OUT_S).toBe(2);
  });
});

describe("Flame.tsx performance rule", () => {
  it("never sets React state (all per-frame changes go through refs)", () => {
    const files = import.meta.glob("./Flame.tsx", { query: "?raw", import: "default", eager: true });
    const source = files["./Flame.tsx"] as string;
    expect(source).not.toMatch(/useState|setState|useReducer/);
    expect(source).toMatch(/useFrame\(/);
  });
});
