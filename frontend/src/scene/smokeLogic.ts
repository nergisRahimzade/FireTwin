/* FE-06: how a SimulateOut drives the smoke. Pure, so it's unit-tested; Smoke.tsx applies it in
   useFrame. Smoke drifts along flow_dir at flow_speed_cm_s, with no buoyancy (microgravity), so with
   the fans off it only creeps outward from the fire. */
import type { SimulateOut, Vec3 } from "../api/types";

// The demo clock runs 10x real time (plan, FE-06: "time scaled for demo, e.g. 10x").
export const SCENE_TIME_SCALE = 10;
// Simulated seconds a particle lives: long enough to cross the 8.5 m module at slow airflow.
export const SMOKE_LIFE_S = 60;
// Particles per simulated second while burning, scaled by the burn probability.
const MAX_RATE = 30;

export interface SmokeSettings {
  emitting: boolean; // only while the model says the fire is burning
  rate: number; // particles per simulated second
  dir: Vec3; // unit airflow direction
  speedMS: number; // airflow speed, m/s
  fans: boolean; // false = still air: diffusion only
}

export const NO_SMOKE: SmokeSettings = { emitting: false, rate: 0, dir: [1, 0, 0], speedMS: 0, fans: false };

export function smokeSettings(sim: SimulateOut | null): SmokeSettings {
  if (!sim) return NO_SMOKE;
  const [x, y, z] = sim.inputs.flow_dir;
  const len = Math.hypot(x, y, z);
  const speedCmS = len > 0 ? Math.max(0, sim.inputs.flow_speed_cm_s) : 0;
  const emitting = sim.state === "burning";
  return {
    emitting,
    rate: emitting ? MAX_RATE * (0.4 + 0.6 * Math.min(1, Math.max(0, sim.burn_probability))) : 0,
    dir: len > 0 ? [x / len, y / len, z / len] : [1, 0, 0],
    speedMS: speedCmS / 100,
    fans: speedCmS > 0,
  };
}
