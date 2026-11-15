/* The 3D demo clock, shared by the store (alarm timer), the smoke and the clock readout.
   Plain constants with no three.js import, so the store can use them without pulling three.js
   into the main bundle. */

// The demo clock runs 10x real time (plan, FE-06: "time scaled for demo, e.g. 10x").
export const SCENE_TIME_SCALE = 10;

// Simulated seconds since the current ignition, from the store's ignitedAt (Date.now() ms).
export function simSecondsSince(ignitedAt: number | null, now = Date.now()): number {
  return ignitedAt == null ? 0 : (Math.max(0, now - ignitedAt) / 1000) * SCENE_TIME_SCALE;
}
