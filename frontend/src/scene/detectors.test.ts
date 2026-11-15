// FE-04: detector markers use the exact positions /detect returns.
import { describe, expect, it } from "vitest";
import type { DetectOut } from "../api/types";
import { detectorMarks } from "./detectors";

const detect = (detectors: unknown[]): DetectOut => ({
  detected: true, detector_id: "vent_aft", time_to_detect_s: 40, note: "",
  detectors: detectors as DetectOut["detectors"],
});

describe("detectorMarks", () => {
  it("returns nothing before /detect has run", () => {
    expect(detectorMarks(null)).toEqual([]);
  });

  it("keeps each detector's id and exact [x, y, z]", () => {
    expect(detectorMarks(detect([
      { id: "vent_aft", position: [4, 1.5, 0], peak_concentration: 0.8 },
      { id: "vent_mid", position: [0, 2, 0], peak_concentration: 0.1 },
    ]))).toEqual([
      { id: "vent_aft", position: [4, 1.5, 0], synthetic: false },
      { id: "vent_mid", position: [0, 2, 0], synthetic: false },
    ]);
  });

  it("labels synthetic placeholders (BE-06 mock mode)", () => {
    const [mark] = detectorMarks(detect([{ id: "synthetic-vent-1", position: [4, 0, 0], peak_concentration: 0.8, is_synthetic: true }]));
    expect(mark.synthetic).toBe(true);
  });

  it("skips malformed entries instead of guessing a position", () => {
    expect(detectorMarks(detect([
      { id: "no-position", peak_concentration: 0 },
      { id: "short", position: [1, 2], peak_concentration: 0 },
      { id: "nan", position: [1, Number.NaN, 0], peak_concentration: 0 },
      { position: [1, 1, 1], peak_concentration: 0 },
    ]))).toEqual([]);
  });
});
