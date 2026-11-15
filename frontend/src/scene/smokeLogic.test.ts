// FE-06: SimulateOut -> smoke, a headless run of the real particle model, and the
// "no React state per frame" guard for Smoke.tsx.
import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { SimulateOut } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import { Smoke as CoreSmoke } from "../lab/core.js";
import {
  MAX_FRAME_GAP_S, NO_SMOKE, SCENE_TIME_SCALE, SMOKE_LIFE_S, SmokeDriver, smokeSettings,
} from "./smokeLogic";

const sim = (over: Partial<SimulateOut> = {}, inputs: Partial<SimulateOut["inputs"]> = {}): SimulateOut => ({
  scenario_id: "s1", state: "burning", burn_probability: 0.8, spread_rate_mm_s: null, trust: "weak",
  extrapolated: false, nearest_tests: [], explanation: "", inputs: { ...DEFAULT_SCENARIO, ...inputs }, ...over,
});

describe("smokeSettings", () => {
  it("makes no smoke before ignition, and stops new smoke once extinguished", () => {
    expect(smokeSettings(null)).toEqual(NO_SMOKE);
    expect(smokeSettings(sim({ state: "extinguished" })).rate).toBe(0);
    expect(smokeSettings(sim()).rate).toBeGreaterThan(0);
  });

  it("follows flow_dir (normalized) at flow_speed_cm_s in m/s", () => {
    const s = smokeSettings(sim({}, { flow_dir: [0, 0, -3], flow_speed_cm_s: 20 }));
    expect(s.dir).toEqual([0, 0, -1]);
    expect(s.speedMS).toBeCloseTo(0.2);
    expect(s.fans).toBe(true);
  });

  it("treats 0 cm/s as fans off", () => {
    expect(smokeSettings(sim({}, { flow_speed_cm_s: 0 })).fans).toBe(false);
  });
});

// Run the real lab/core.js particle model the way Smoke.tsx does, then measure where the smoke went.
function drift(settings: ReturnType<typeof smokeSettings>, seconds = 3) {
  const smoke = new CoreSmoke(1600);
  const p = { rate: settings.rate, g: 0, flow: { dir: settings.dir, fans: settings.fans }, speed: settings.speedMS,
    src: new THREE.Vector3(0, 0, 0), radius: 0.12, life: SMOKE_LIFE_S };
  for (let t = 0; t < seconds; t += 1 / 60) smoke.step((1 / 60) * SCENE_TIME_SCALE, p, [], () => {});
  const mean = [0, 0, 0];
  let n = 0;
  for (let i = 0; i < smoke.n; i++) {
    if (smoke.age[i] < 0) continue;
    for (let k = 0; k < 3; k++) mean[k] += smoke.pos[i * 3 + k];
    n++;
  }
  return { n, mean: mean.map(v => v / Math.max(1, n)) };
}

describe("smoke drift (headless)", () => {
  it("drifts from the fire along +X with the default fore airflow", () => {
    const { n, mean } = drift(smokeSettings(sim({}, { flow_dir: [1, 0, 0], flow_speed_cm_s: 10 })));
    expect(n).toBeGreaterThan(100);
    expect(mean[0]).toBeGreaterThan(0.5); // carried fore
    expect(Math.abs(mean[2])).toBeLessThan(0.2);
  });

  it("follows other directions too (starboard, -Z)", () => {
    const { mean } = drift(smokeSettings(sim({}, { flow_dir: [0, 0, -1], flow_speed_cm_s: 10 })));
    expect(mean[2]).toBeLessThan(-0.5);
    expect(Math.abs(mean[0])).toBeLessThan(0.2);
  });

  it("stays near the fire with the fans off (no buoyancy in microgravity)", () => {
    const { mean } = drift(smokeSettings(sim({}, { flow_speed_cm_s: 0 })));
    expect(Math.hypot(mean[0], mean[1], mean[2])).toBeLessThan(0.3);
  });
});

describe("SmokeDriver: a new ignition, not the backend id, resets the smoke (review fix)", () => {
  const burning = smokeSettings(sim({ scenario_id: "synthetic-scenario-001" }));
  const runFor = (d: SmokeDriver, seconds: number, s = burning) => { for (let t = 0; t < seconds; t += 1 / 60) d.advance(1 / 60, s); };

  it("clears the cloud on a second ignition with the same backend scenario_id", () => {
    const d = new SmokeDriver();
    expect(d.sync(1)).toBe(true);
    runFor(d, 2);
    expect(d.liveCount()).toBeGreaterThan(100);
    // Ignite again: the BE-06 mock returns the same scenario_id, but the store's counter moves on.
    expect(d.sync(2)).toBe(true);
    expect(d.liveCount()).toBe(0);
    expect(d.simElapsed).toBe(0);
  });

  it("keeps the existing cloud through /apply (same ignition)", () => {
    const d = new SmokeDriver();
    d.sync(1);
    runFor(d, 2);
    const before = d.liveCount();
    expect(d.sync(1)).toBe(false); // /apply re-renders with the same ignition counter
    const out = smokeSettings(sim({ scenario_id: "synthetic-scenario-001", state: "extinguished" }));
    d.advance(1 / 60, out);
    expect(d.liveCount()).toBeGreaterThanOrEqual(before - 5); // still there, only fading
  });
});

describe("SmokeDriver: the 10x clock holds at any frame rate (review fix)", () => {
  // The same 2 real seconds at 120, 10 and 4 fps (and one long 0.8 s frame).
  const elapsedAt = (frameS: number) => {
    const d = new SmokeDriver();
    d.sync(1);
    for (let t = 0; t < 2 - 1e-9; t += frameS) d.advance(frameS, smokeSettings(sim()));
    return d.simElapsed;
  };

  it("simulates 10 s per real second, however long the frames are", () => {
    for (const frameS of [1 / 120, 0.1, 0.25]) expect(elapsedAt(frameS)).toBeCloseTo(2 * SCENE_TIME_SCALE, 6);
    const d = new SmokeDriver();
    d.sync(1);
    d.advance(0.8, smokeSettings(sim()));
    expect(d.simElapsed).toBeCloseTo(8, 6);
  });

  it("drifts about as far at 10 fps as at 120 fps", () => {
    const meanX = (frameS: number) => {
      const d = new SmokeDriver();
      d.sync(1);
      for (let t = 0; t < 2 - 1e-9; t += frameS) d.advance(frameS, smokeSettings(sim({}, { flow_speed_cm_s: 10 })));
      let x = 0, n = 0;
      for (let i = 0; i < d.smoke.n; i++) if (d.smoke.age[i] >= 0) { x += d.smoke.pos[i * 3]; n++; }
      return x / n;
    };
    const fast = meanX(1 / 120), slow = meanX(0.1);
    expect(slow).toBeGreaterThan(fast * 0.75);
    expect(slow).toBeLessThan(fast * 1.25);
  });

  it("caps a very long gap (e.g. a hidden tab) instead of running hundreds of catch-up steps", () => {
    const d = new SmokeDriver();
    d.sync(1);
    d.advance(30, smokeSettings(sim()));
    expect(d.simElapsed).toBeCloseTo(MAX_FRAME_GAP_S * SCENE_TIME_SCALE, 6);
  });
});

describe("Smoke.tsx performance rule", () => {
  it("never sets React state (particles change in useFrame through refs)", () => {
    const files = import.meta.glob("./Smoke.tsx", { query: "?raw", import: "default", eager: true });
    const source = files["./Smoke.tsx"] as string;
    expect(source).not.toMatch(/useState|setState|useReducer/);
    expect(source).toMatch(/useFrame\(/);
  });
});
