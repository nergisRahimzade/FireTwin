// FE-06 alarm: timing on the 10x demo clock and the banner text.
import { describe, expect, it } from "vitest";
import type { DetectOut } from "../api/types";
import { alarmAfterS, alarmBanner } from "./alarmLogic";

const det = (over: Partial<DetectOut> = {}): DetectOut => ({
  detected: true, detector_id: "vent_fwd", time_to_detect_s: 40, note: "",
  detectors: [{ id: "vent_fwd", position: [4, 1.37, 0], peak_concentration: 0.8 }], ...over,
});
const fansOff = det({ detected: false, detector_id: null, time_to_detect_s: null, note: "fans off: smoke cannot reach vents" });

describe("alarmAfterS", () => {
  it("trips at time_to_detect_s, shown 10x faster", () => {
    expect(alarmAfterS(det())).toBe(4);
    expect(alarmAfterS(det({ time_to_detect_s: 12.5 }))).toBe(1.25);
  });
  it("never trips when nothing is detected or before /detect", () => {
    expect(alarmAfterS(null)).toBeNull();
    expect(alarmAfterS(fansOff)).toBeNull();
    expect(alarmAfterS(det({ detector_id: null }))).toBeNull();
  });
});

describe("alarmBanner", () => {
  it("says nothing before /detect, or until the clock reaches the alarm", () => {
    expect(alarmBanner(null, false)).toBeNull();
    expect(alarmBanner(det(), false)).toBeNull();
  });
  it("announces the tripped detector and its detection time", () => {
    expect(alarmBanner(det(), true)).toEqual({ kind: "alarm", text: "Alarm: vent_fwd detected smoke 40.0 s after ignition." });
  });
  it("shows the API's note when no detector sees the smoke", () => {
    expect(alarmBanner(fansOff, false)).toEqual({ kind: "note", text: "fans off: smoke cannot reach vents" });
  });
});
