// FE-04/05/06: API results -> what the 3D twin shows.
import { describe, expect, it } from "vitest";
import type { DetectOut, SimulateOut } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import { alarmAfterS, alarmMessage, detectorMarks, flameTarget, flowOf } from "./sceneLogic";

const sim = (over: Partial<SimulateOut> = {}): SimulateOut => ({
  scenario_id: "s1", state: "burning", burn_probability: 0.8, spread_rate_mm_s: null, trust: "weak",
  extrapolated: false, nearest_tests: [], explanation: "", inputs: DEFAULT_SCENARIO, ...over,
});
const det = (over: Partial<DetectOut> = {}): DetectOut => ({
  detected: true, detector_id: "vent_aft", time_to_detect_s: 40, note: "",
  detectors: [{ id: "vent_aft", position: [4, 1.5, 0], peak_concentration: 0.8 }], ...over,
});

describe("flowOf", () => {
  it("normalizes flow_dir and converts cm/s to m/s", () => {
    const f = flowOf({ ...DEFAULT_SCENARIO, flow_dir: [0, 2, 0], flow_speed_cm_s: 20 });
    expect(f.dir).toEqual([0, 1, 0]);
    expect(f.speedMS).toBeCloseTo(0.2);
    expect(f.fans).toBe(true);
  });
  it("treats 0 cm/s as fans off", () => {
    expect(flowOf({ ...DEFAULT_SCENARIO, flow_speed_cm_s: 0 }).fans).toBe(false);
  });
});

describe("flameTarget (FE-05)", () => {
  it("shows nothing before ignition and fades out when extinguished", () => {
    expect(flameTarget(null).alive).toBe(0);
    expect(flameTarget(sim({ state: "extinguished" })).alive).toBe(0);
    expect(flameTarget(sim()).alive).toBe(1);
  });
  it("stays a sphere with the fans off and stretches as airflow rises", () => {
    expect(flameTarget(sim({ inputs: { ...DEFAULT_SCENARIO, flow_speed_cm_s: 0 } })).stretch).toBe(0);
    const slow = flameTarget(sim({ inputs: { ...DEFAULT_SCENARIO, flow_speed_cm_s: 10 } })).stretch;
    const fast = flameTarget(sim({ inputs: { ...DEFAULT_SCENARIO, flow_speed_cm_s: 40 } })).stretch;
    expect(slow).toBeGreaterThan(0);
    expect(fast).toBeGreaterThan(slow);
  });
  it("grows with predicted spread and carries the extrapolation flag", () => {
    expect(flameTarget(sim()).spreadScale).toBe(1);
    expect(flameTarget(sim({ spread_rate_mm_s: 2 })).spreadScale).toBeGreaterThan(1);
    expect(flameTarget(sim({ extrapolated: true })).extrapolated).toBe(true);
  });
});

describe("alarm (FE-06)", () => {
  it("trips at time_to_detect_s shown 10x faster", () => {
    expect(alarmAfterS(det())).toBe(4);
    expect(alarmAfterS(det({ detected: false, detector_id: null, time_to_detect_s: null }))).toBeNull();
  });
  it("shows the API's note when no detector sees the smoke", () => {
    const fansOff = det({ detected: false, detector_id: null, time_to_detect_s: null, note: "fans off: smoke cannot reach vents" });
    expect(alarmMessage(fansOff, false)).toEqual({ kind: "note", text: "fans off: smoke cannot reach vents" });
  });
  it("waits for the clock before announcing the alarm", () => {
    expect(alarmMessage(det(), false)).toBeNull();
    expect(alarmMessage(det(), true)?.text).toBe("Alarm: vent_aft detected smoke 40.0 s after ignition.");
  });
});

describe("detectorMarks (FE-04)", () => {
  it("uses the positions /detect returns and skips malformed entries", () => {
    const marks = detectorMarks(det({
      detectors: [
        { id: "vent_aft", position: [4, 1.5, 0], peak_concentration: 0.8, is_synthetic: true },
        { id: "broken", position: [1, 2] as unknown as [number, number, number], peak_concentration: 0 },
      ],
    }));
    expect(marks).toEqual([{ id: "vent_aft", position: [4, 1.5, 0], synthetic: true }]);
  });
});
