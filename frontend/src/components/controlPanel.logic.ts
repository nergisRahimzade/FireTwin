/* FE-03: the control panel's rules, kept free of React so they're unit-tested. */
import type { MetaOut, ScenarioIn, Vec3 } from "../api/types";

// Slider limits from the contract (ScenarioIn: O2 10-40 %, flow 0-40 cm/s). The plan gives no
// pressure range; 30-110 kPa spans habitat ideas (10.2 psi = 70.3 kPa) up to ISS sea-level air.
export const LIMITS = {
  o2_pct: { min: 10, max: 40, step: 0.5, unit: "%" },
  flow_speed_cm_s: { min: 0, max: 40, step: 1, unit: "cm/s" },
  pressure_kpa: { min: 30, max: 110, step: 0.1, unit: "kPa" },
} as const;
export type SliderKey = keyof typeof LIMITS;

// Module axes from the 3D lab (+x fore, +y overhead, +z port).
export const FLOW_DIRS: { label: string; hint: string; dir: Vec3 }[] = [
  { label: "+X", hint: "fore", dir: [1, 0, 0] },
  { label: "−X", hint: "aft", dir: [-1, 0, 0] },
  { label: "+Y", hint: "overhead", dir: [0, 1, 0] },
  { label: "−Y", hint: "deck", dir: [0, -1, 0] },
  { label: "+Z", hint: "port", dir: [0, 0, 1] },
  { label: "−Z", hint: "starboard", dir: [0, 0, -1] },
];
export const sameDir = (a: Vec3, b: Vec3) => a.every((v, i) => v === b[i]);

// MetaOut.ranges holds min/max per feature in the training data. The model's flow feature is
// flow_cm_s (ML-01) while ScenarioIn calls it flow_speed_cm_s, so accept either key.
const RANGE_KEYS: Record<SliderKey, string[]> = {
  o2_pct: ["o2_pct"],
  flow_speed_cm_s: ["flow_cm_s", "flow_speed_cm_s"],
  pressure_kpa: ["pressure_kpa"],
};
export interface Range { min: number; max: number; synthetic?: boolean }

export function testedRange(meta: MetaOut | null, key: SliderKey): Range | null {
  if (!meta?.ranges) return null;
  for (const k of RANGE_KEYS[key]) {
    const r = meta.ranges[k];
    if (r && Number.isFinite(r.min) && Number.isFinite(r.max) && r.max >= r.min) {
      return { min: r.min, max: r.max, ...(r.is_synthetic ? { synthetic: true } : {}) };
    }
  }
  return null;
}

export const isOutside = (value: number, range: Range | null) => !!range && (value < range.min || value > range.max);

// Left/right offsets (in % of the slider) for the shaded tested band, clipped to the slider.
export function bandPercent(range: Range, key: SliderKey) {
  const { min, max } = LIMITS[key];
  const pct = (v: number) => ((Math.min(max, Math.max(min, v)) - min) / (max - min)) * 100;
  return { left: pct(range.min), right: 100 - pct(range.max) };
}

// Inputs outside the tested range for the current material's data, by slider.
export function outsideKeys(inputs: ScenarioIn, meta: MetaOut | null): SliderKey[] {
  return (Object.keys(LIMITS) as SliderKey[]).filter(k => isOutside(inputs[k], testedRange(meta, k)));
}

// Dropdown text for a material. Synthetic rows (rule 5) never claim to be NASA tests.
export const materialLabel = (m: { name: string; fuel_type: string; n_tests: number; is_synthetic?: boolean }) =>
  `${m.name} · ${m.fuel_type} · ${m.n_tests} ${m.is_synthetic ? "synthetic test rows (not NASA data)" : "NASA tests"}`;

export function igniteBlocker(inputs: ScenarioIn, meta: MetaOut | null, busy: boolean): string | null {
  if (busy) return "Running…";
  if (!meta) return "Waiting for the API to list materials.";
  if (!inputs.material) return "Choose a material.";
  return null;
}
