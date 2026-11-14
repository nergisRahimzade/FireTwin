/* FE-04/05/06: how API results map onto the 3D twin. Pure functions, unit-tested.
   The model decides; the scene only illustrates (honesty rule). */
import type { DetectOut, ScenarioIn, SimulateOut, Vec3 } from "../api/types";

// FE-06: the demo clock runs 10x real time (plan: "time scaled for demo, e.g. 10x").
export const SCENE_TIME_SCALE = 10;
// BE-03 puts the fire at the module centre by default; the contract has no fire position field.
export const FIRE_POSITION: Vec3 = [0, 0, 0];
export const MAX_FLOW_CM_S = 40; // ScenarioIn: flow_speed_cm_s is 0-40

export interface Flow { dir: Vec3; speedMS: number; fans: boolean }

// flow_dir is normalized (any length the API sends); cm/s -> m/s.
export function flowOf(inputs: ScenarioIn | undefined | null): Flow {
  const [x, y, z] = inputs?.flow_dir ?? [1, 0, 0];
  const len = Math.hypot(x, y, z);
  const speed = Math.max(0, inputs?.flow_speed_cm_s ?? 0);
  const dir: Vec3 = len > 0 ? [x / len, y / len, z / len] : [0, 0, 0];
  return { dir, speedMS: speed / 100, fans: speed > 0 && len > 0 };
}

export interface FlameTarget {
  alive: 0 | 1; // 0 = fade out (extinguished, or nothing ignited yet)
  burnP: number; // 0-1, sets size with oxygen
  o2: number;
  stretch: number; // 0 = microgravity sphere, 1 = fully stretched along the flow
  spreadScale: number; // a little larger when the model predicts faster spread
  extrapolated: boolean; // grey stripes + "outside tested range" tag
}

// FE-05: size from burn_probability and spread_rate_mm_s; stretched along flow_dir as flow rises.
export function flameTarget(sim: SimulateOut | null): FlameTarget {
  if (!sim) return { alive: 0, burnP: 0, o2: 21, stretch: 0, spreadScale: 1, extrapolated: false };
  const flow = flowOf(sim.inputs);
  const spread = sim.spread_rate_mm_s ?? 0;
  return {
    alive: sim.state === "burning" ? 1 : 0,
    burnP: Math.min(1, Math.max(0, sim.burn_probability)),
    o2: sim.inputs.o2_pct,
    stretch: flow.fans ? Math.min(1, (flow.speedMS * 100) / MAX_FLOW_CM_S) * 0.85 : 0,
    spreadScale: 1 + Math.min(1, Math.max(0, spread) / 2) * 0.35,
    extrapolated: sim.extrapolated,
  };
}

// FE-06: real seconds after ignition when the alarm should show, or null if it never trips.
export function alarmAfterS(detect: DetectOut | null, scale = SCENE_TIME_SCALE): number | null {
  if (!detect?.detected || detect.time_to_detect_s == null || !detect.detector_id) return null;
  return Math.max(0, detect.time_to_detect_s) / scale;
}

export interface DetectorMark { id: string; position: Vec3; synthetic: boolean }

// FE-04: detectors exactly where /detect says. Malformed entries are skipped, not guessed.
export function detectorMarks(detect: DetectOut | null): DetectorMark[] {
  return (detect?.detectors ?? []).flatMap(d => {
    const p = d.position;
    if (!Array.isArray(p) || p.length !== 3 || !p.every(Number.isFinite) || typeof d.id !== "string") return [];
    return [{ id: d.id, position: [p[0], p[1], p[2]] as Vec3, synthetic: !!d.is_synthetic }];
  });
}

// The banner under the scene, by phase of the alarm.
export function alarmMessage(detect: DetectOut | null, tripped: boolean): { kind: "alarm" | "note"; text: string } | null {
  if (!detect) return null;
  if (!detect.detected) return { kind: "note", text: detect.note || "No detector sees the smoke." };
  if (!tripped) return null;
  const t = detect.time_to_detect_s?.toFixed(1);
  return { kind: "alarm", text: `Alarm: ${detect.detector_id} detected smoke ${t} s after ignition.` };
}
