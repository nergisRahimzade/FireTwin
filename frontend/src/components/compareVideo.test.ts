// Compare video view: the video's facts, its timeline, and how a moment in it maps to the 3D flame.
import { describe, expect, it } from "vitest";
import type { PreviewOut } from "../api/types";
import { LIMITS } from "./controlPanel.logic";
import {
  IGNITION_S, MODEL_INPUTS, PHASES, VIDEO, VIDEO_CONDITIONS, flameAt, formatTime, phaseAt, phaseEnd, sceneVerdict,
} from "./compareVideo";

const preview: PreviewOut = {
  state: "extinguished", burn_probability: 0.298, trust: "strong", extrapolated: false, is_synthetic: false,
  inputs: MODEL_INPUTS,
};

describe("the video's test", () => {
  it("is the requested NASA video", () => {
    expect(VIDEO.id).toBe("qQQ1OHW1_F4");
  });
  it("gives every condition a source", () => {
    for (const c of VIDEO_CONDITIONS) expect(c.source.length).toBeGreaterThan(0);
  });
  it("runs the model at the description's oxygen and pressure, in still gas", () => {
    expect(MODEL_INPUTS).toMatchObject({ material: "Heptane", o2_pct: 21, pressure_kpa: 101.3, flow_speed_cm_s: 0 });
    expect(MODEL_INPUTS.pressure_kpa).toBeLessThanOrEqual(LIMITS.pressure_kpa.max); // fits the sliders too
  });
});

describe("the timeline the team read off the video", () => {
  it("has the phases in time order, starting at 0:00", () => {
    expect(PHASES[0].from).toBe(0);
    for (let i = 1; i < PHASES.length; i++) expect(PHASES[i].from).toBeGreaterThan(PHASES[i - 1].from);
    expect(IGNITION_S).toBe(43);
  });
  it("finds the phase at any moment, including the exact second a phase starts", () => {
    expect([0, 42.9, 43, 45.9, 46, 62.9, 63, 500].map(phaseAt)).toEqual([0, 0, 1, 1, 2, 2, 3, 3]);
    expect(phaseAt(-1)).toBe(0);
  });
  it("lights the 3D flame at 0:43 and puts it out at 1:03", () => {
    expect([10, 43, 50, 62.9, 63, 80].map(flameAt)).toEqual(["none", "burning", "burning", "burning", "out", "out"]);
  });
  it("ends each phase where the next starts, and the last at the video's end", () => {
    expect(phaseEnd(0, 95)).toBe(43);
    expect(phaseEnd(PHASES.length - 1, 95)).toBe(95);
    expect(phaseEnd(PHASES.length - 1, null)).toBeNull();
  });
  it("formats times like the video player", () => {
    expect([0, 9.9, 43, 63, 125].map(formatTime)).toEqual(["0:00", "0:09", "0:43", "1:03", "2:05"]);
  });
});

describe("what the 3D draws", () => {
  it("draws nothing before ignition, or without a model result", () => {
    expect(sceneVerdict(preview, "none")).toBeNull();
    expect(sceneVerdict(null, "burning")).toBeNull();
  });
  it("burns while the video's flame burns and goes out when it does, sized by the model", () => {
    expect(sceneVerdict(preview, "burning")).toMatchObject({ state: "burning", burn_probability: 0.298, inputs: MODEL_INPUTS });
    expect(sceneVerdict(preview, "out")?.state).toBe("extinguished");
  });
});
