/* FE-06: how a SimulateOut drives the smoke. Pure, so it's unit-tested; Smoke.tsx applies it in
   useFrame. Smoke drifts along flow_dir at flow_speed_cm_s, with no buoyancy (microgravity), so with
   the fans off it only creeps outward from the fire. */
import * as THREE from "three";
import type { SimulateOut, Vec3 } from "../api/types";
import { FIRE_POS } from "../lab/config.js";
import { Smoke as CoreSmoke } from "../lab/core.js";

import { SCENE_TIME_SCALE } from "./clock";

export { SCENE_TIME_SCALE };
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

// Each simulation substep covers at most this much simulated time (0.05 s of real time at 10x).
export const MAX_SUBSTEP_SIM_S = 0.5;
// A frame gap longer than this (a hidden tab, a debugger pause) is capped, so returning to the page
// doesn't run hundreds of catch-up steps at once. Below it, every real second is simulated in full.
export const MAX_FRAME_GAP_S = 1;

/* Owns the particle system for Smoke.tsx (and runs headless in tests):
   - sync(ignition): a new ignition (the store's counter changed) clears the old cloud, even when the
     backend reuses the same scenario_id; /apply doesn't change the counter, so its smoke stays.
   - advance(realSeconds): the full elapsed time x 10, in bounded substeps, so smoke moves and fades
     at the same 10x pace as the alarm's wall clock, at 120 fps or 5 fps. */
export class SmokeDriver {
  readonly smoke: CoreSmoke;
  simElapsed = 0; // simulated seconds since this ignition
  private lastAdvanceAt: number | null = null; // Date.now() at the last advance()
  private ignition: number | null = null;
  private readonly params = {
    rate: 0, g: 0, flow: { dir: [1, 0, 0] as Vec3, fans: false }, speed: 0,
    src: new THREE.Vector3(...(FIRE_POS as [number, number, number])), radius: 0.12, life: SMOKE_LIFE_S,
  };

  constructor(count = 1600) {
    this.smoke = new CoreSmoke(count);
  }

  /** Returns true when this is a new ignition and the cloud was cleared. */
  sync(ignition: number): boolean {
    if (ignition === this.ignition) return false;
    this.ignition = ignition;
    this.smoke.reset();
    this.simElapsed = 0;
    return true;
  }

  /** Clears the cloud (e.g. Reset: there is no scenario any more). */
  clear(): void {
    this.smoke.reset();
    this.simElapsed = 0;
    this.lastAdvanceAt = null;
  }

  /** Advances the time since this driver last moved (e.g. the instant between closing one view and
      opening the other). Gaps over MAX_FRAME_GAP_S are capped, as in advance(). */
  resume(s: SmokeSettings, now = Date.now()): void {
    if (this.lastAdvanceAt !== null) this.advance((now - this.lastAdvanceAt) / 1000, s, now);
  }

  /** Frees the GPU buffers; called when a new ignition replaces this driver. */
  dispose(): void {
    this.smoke.geometry.dispose();
    this.smoke.material.dispose();
  }

  advance(realSeconds: number, s: SmokeSettings, now = Date.now()): void {
    this.lastAdvanceAt = now;
    const p = this.params;
    p.rate = s.rate; // 0 once extinguished: the last smoke drifts on and fades
    p.flow.dir = s.dir;
    p.flow.fans = s.fans;
    p.speed = s.speedMS;
    let remaining = Math.min(Math.max(0, realSeconds), MAX_FRAME_GAP_S) * SCENE_TIME_SCALE;
    while (remaining > 1e-9) {
      const step = Math.min(remaining, MAX_SUBSTEP_SIM_S);
      this.smoke.step(step, p, [], () => {});
      this.simElapsed += step;
      remaining -= step;
    }
  }

  /** Number of live particles (for tests and debugging). */
  liveCount(): number {
    let n = 0;
    for (let i = 0; i < this.smoke.n; i++) if (this.smoke.age[i] >= 0) n++;
    return n;
  }
}

/* One SmokeDriver per ignition, shared by every 3D view (main page and Compare), so switching views
   keeps the cloud exactly as it is: still fading after an extinguish, still bent by a fans-off
   /apply. A new ignition replaces (and disposes) the previous driver. */
let shared: { ignition: number; driver: SmokeDriver } | null = null;

export function smokeDriverFor(ignition: number): SmokeDriver {
  if (shared?.ignition !== ignition) {
    shared?.driver.dispose();
    const driver = new SmokeDriver(1600);
    driver.sync(ignition);
    shared = { ignition, driver };
  }
  return shared.driver;
}

/* What Smoke.tsx does when the scenario changes: with no scenario (before ignition, or after Reset)
   the cloud is cleared, so nothing is left frozen; /apply (a new prediction) keeps it. */
export function syncSmoke(driver: SmokeDriver, sim: SimulateOut | null): void {
  if (!sim) driver.clear();
}
