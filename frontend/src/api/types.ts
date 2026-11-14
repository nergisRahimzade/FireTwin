/* FireTwin API contract. Source of truth: backend/app/schemas.py (BE-05).
   src/api/schema.d.ts is generated from the backend's /openapi.json (`npm run gen:api`).
   These hand-written types add detail the schema leaves as plain dicts (detectors, results rows,
   materials, citations); contract.check.ts makes `tsc` fail if their fields drift from it.
   Synthetic data (rule 5) carries is_synthetic=true and must show a "synthetic" badge. */

export type Vec3 = [number, number, number];
export type Outcome = "burned" | "extinguished" | "unknown";
export type Trust = "strong" | "medium" | "weak";
export type DataSupport = "direct" | "indirect" | "none";
export type ActionName = "fans_off" | "cut_power" | "co2" | "water_mist" | "fans_off_co2";

export interface TestRef {
  test_id: string;
  investigation: string;
  fuel_type: string;
  o2_pct: number | null;
  pressure_kpa: number | null;
  flow_cm_s: number | null;
  outcome: Outcome;
  source_url: string;
  is_synthetic: boolean;
}

export interface ScenarioIn {
  module: "iss_lab";
  material: string; // from MetaOut.materials
  o2_pct: number; // 10-40
  pressure_kpa: number; // default 101.3
  flow_speed_cm_s: number; // 0-40
  flow_dir: Vec3; // default [1, 0, 0]
}

export interface SimulateOut {
  scenario_id: string;
  state: "burning" | "extinguished";
  burn_probability: number; // 0-1
  spread_rate_mm_s: number | null;
  trust: Trust;
  extrapolated: boolean; // outside tested ranges
  nearest_tests: TestRef[]; // top 3
  explanation: string; // one grounded sentence
  inputs: ScenarioIn;
}

export interface DetectorReading {
  id: string;
  position: Vec3; // metres, origin at the module centre
  peak_concentration: number;
  is_synthetic?: boolean;
}

export interface DetectOut {
  detected: boolean;
  detector_id: string | null;
  time_to_detect_s: number | null; // null = never reaches a detector
  detectors: DetectorReading[];
  note: string; // e.g. "fans off: smoke cannot reach vents"
}

export interface ActionResult {
  action: ActionName;
  label: string;
  new_inputs: ScenarioIn;
  extinction_probability: number;
  crew_risk: number;
  score: number;
  data_support: DataSupport;
  sources: TestRef[];
  explanation: string;
}

export interface SuppressOut {
  scenario_id: string;
  recommended: string;
  actions: ActionResult[]; // sorted by score
}

export interface ResultsRow {
  step: number; // 1, 2, ... in the order the scenario ran
  inputs: ScenarioIn;
  state: SimulateOut["state"] | null; // null on rows without a new verdict (e.g. detect)
  probability: number | null;
  trust: Trust | null;
  detection_s: number | null;
  action: string | null;
  sources: TestRef[];
}

export interface ResultsOut {
  scenario_id: string;
  rows: ResultsRow[];
}

export interface Citation {
  title: string;
  investigation: string;
  source_url: string;
  snippet: string;
}

export interface ChatOut {
  answer: string;
  citations: Citation[];
}

export interface MaterialOption {
  name: string;
  fuel_type: string;
  n_tests: number;
  is_synthetic?: boolean;
}

export interface HealthOut {
  status: string;
}

export interface MetaOut {
  materials: MaterialOption[];
  ranges: Record<string, { min: number; max: number; is_synthetic?: boolean }>; // per feature, training data
  investigations: Record<string, unknown>[];
}

export const DEFAULT_SCENARIO: ScenarioIn = {
  module: "iss_lab",
  material: "",
  o2_pct: 21,
  pressure_kpa: 101.3,
  flow_speed_cm_s: 10,
  flow_dir: [1, 0, 0],
};
