/* Compare: the NASA FLEX-2 droplet-flame video and what this view knows about it. Pure, so it's
   unit-tested; CompareView draws it. Rule 5: every value says where it came from. The video's
   conditions come from its YouTube description; the phase times were read off the video by the
   team; the model's inputs are the closest it can take, and say how they differ. */
import type { PreviewOut, ScenarioIn, SimulateOut } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";

export const VIDEO = {
  id: "qQQ1OHW1_F4",
  title: "Amazing Flame Comes to Life in Space Station Microgravity Combustion Science",
  channel: "NASA Johnson",
  watch: "https://www.youtube.com/watch?v=qQQ1OHW1_F4",
};

// Where each value below comes from.
export const SOURCES = {
  description: "The video's YouTube description (NASA Johnson)",
  flexSheet: "NASA FLEX experiment sheet",
  team: "Timed by the team from the video",
} as const;
export const FLEX_SHEET_URL = "https://www.nasa.gov/wp-content/uploads/2025/07/flame-extinguishment-experiment-flex.pdf";

export interface Condition {
  name: string;
  value: string;
  source: string;
}

/** The test in the video, as NASA describes it. */
export const VIDEO_CONDITIONS: Condition[] = [
  { name: "Experiment", value: "FLEX-2 (Flame Extinguishment-2) on the ISS", source: SOURCES.description },
  { name: "Fuel", value: "50/50 mixture of iso-octane and heptane", source: SOURCES.description },
  { name: "Droplet", value: "3 mm", source: SOURCES.description },
  { name: "Oxygen", value: "21 %", source: SOURCES.description },
  { name: "Rest of the gas", value: "79 % nitrogen", source: SOURCES.description },
  { name: "Pressure", value: "1 atm (101.3 kPa)", source: SOURCES.description },
  // Not in the description: the FLEX sheet says FLEX-2 droplets burn in still gas, apart from a
  // separate set of tethered convective-flow tests, which this video isn't described as.
  { name: "Airflow", value: "none (still gas)", source: `Not in the description; ${SOURCES.flexSheet}: FLEX-2 droplets burn "in a quiescent ambient"` },
  {
    name: "What NASA saw", value: "Flame oscillations: a hole in the flame shell repeatedly opens and closes",
    source: SOURCES.description,
  },
];

// The model knows heptane (FLEX tests) but has no iso-octane, so it runs on heptane, the
// mixture's other half, at the video's oxygen, pressure and airflow.
export const MODEL_INPUTS: ScenarioIn = {
  ...DEFAULT_SCENARIO, material: "Heptane", o2_pct: 21, pressure_kpa: 101.3, flow_speed_cm_s: 0,
};
export const MODEL_FUEL_NOTE =
  "Our NASA test table has no iso-octane, so the model runs on heptane, the mixture's other half.";

/** One stretch of the video. `flame` is what the 3D flame shows during it. */
export interface Phase {
  from: number; // seconds into the video
  label: string;
  short: string; // for the timeline bar, where the full label may not fit
  flame: "none" | "burning" | "out";
}

// Timed by the team from the video (mm:ss): 0:00-0:42 before ignition, 0:43-0:45 ignition,
// 0:46-1:02 the ball of flame, 1:03 to the end the flame is out.
export const PHASES: Phase[] = [
  { from: 0, label: "Before ignition", short: "Not lit", flame: "none" },
  { from: 43, label: "Ignition", short: "Lit", flame: "burning" },
  { from: 46, label: "Flame ball burning", short: "Burning", flame: "burning" },
  { from: 63, label: "Flame out", short: "Out", flame: "out" },
];
export const IGNITION_S = 43;

/** Index of the phase playing at `t` seconds (before 0 counts as the first). */
export function phaseAt(t: number): number {
  let index = 0;
  PHASES.forEach((phase, i) => { if (t >= phase.from) index = i; });
  return index;
}

/** What the 3D flame shows at `t` seconds into the video. */
export const flameAt = (t: number): Phase["flame"] => PHASES[phaseAt(t)].flame;

/** The verdict the 3D scene draws for one flame state: the model's prediction for the video's
    conditions (it sets the flame's size), with burning/out following the video's timeline.
    null = no flame yet (before ignition), or no model result (API offline): nothing is drawn. */
export function sceneVerdict(preview: PreviewOut | null, flame: Phase["flame"]): SimulateOut | null {
  if (!preview || flame === "none") return null;
  return {
    scenario_id: "video-reference", // not a server scenario: nothing here calls /detect or /apply
    state: flame === "burning" ? "burning" : "extinguished",
    burn_probability: preview.burn_probability, spread_rate_mm_s: null, trust: preview.trust,
    extrapolated: preview.extrapolated, nearest_tests: [], explanation: "", inputs: preview.inputs,
  };
}

/** 83.4 -> "1:23". */
export function formatTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Where on the timeline a phase ends: the next phase's start, or the video's end (null while the
    player hasn't reported its length). */
export function phaseEnd(index: number, duration: number | null): number | null {
  return PHASES[index + 1]?.from ?? duration;
}
