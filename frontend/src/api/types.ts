/* FireTwin API contract, typed by hand from the Implementation Tasks doc ("Shared API contract").
   The source of truth is backend/app/schemas.py (BE-05). Once the backend serves /openapi.json,
   run `npm run gen:api` to generate src/api/schema.d.ts and switch these types to it. */

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
  position: Vec3;
  peak_concentration: number;
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
  // Best first, as BE-04 ranks them (docs/contract.md): data-backed actions by score, then no-data
  // actions, water_mist always last. recommended is the first data-backed action.
  actions: ActionResult[];
}

export interface ResultsRow {
  step: string;
  inputs: ScenarioIn;
  state: string;
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
}

export interface MetaOut {
  materials: MaterialOption[];
  ranges: Record<string, { min: number; max: number }>; // min/max per feature in the training data
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
