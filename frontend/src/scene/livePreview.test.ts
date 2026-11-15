import { describe, expect, it } from "vitest";
import { DEFAULT_SCENARIO } from "../api/types";
import type { PreviewOut, SimulateOut } from "../api/types";
import { flameTarget } from "./flameLogic";
import { inputsDiffer, liveScenario } from "./livePreview";

const ignited: SimulateOut = {
  scenario_id: "s1", state: "burning", burn_probability: 0.9, spread_rate_mm_s: null, trust: "strong",
  extrapolated: false, nearest_tests: [], explanation: "", inputs: { ...DEFAULT_SCENARIO, material: "PMMA rod" },
};

describe("inputsDiffer", () => {
  it("is false for the ignited inputs and true when any control moved", () => {
    const base = ignited.inputs;
    expect(inputsDiffer(base, { ...base })).toBe(false);
    expect(inputsDiffer(base, { ...base, o2_pct: base.o2_pct + 1 })).toBe(true);
    expect(inputsDiffer(base, { ...base, flow_speed_cm_s: 0 })).toBe(true);
    expect(inputsDiffer(base, { ...base, flow_dir: [0, 0, -1] })).toBe(true);
    expect(inputsDiffer(base, { ...base, material: "Nomex" })).toBe(true);
  });
});

describe("liveScenario", () => {
  const moved = { ...ignited.inputs, flow_speed_cm_s: 0, o2_pct: 15 };

  it("shows the new airflow and oxygen at once, keeping the old verdict until the preview arrives", () => {
    const scene = liveScenario(ignited, moved, null);
    expect(scene.inputs).toEqual(moved);
    expect(scene.state).toBe("burning");
    expect(scene.scenario_id).toBe("s1"); // still the ignited scenario: nothing is recorded
  });

  it("takes the state and probability from the preview, so the flame can go out live", () => {
    const preview: PreviewOut = {
      state: "extinguished", burn_probability: 0.2, trust: "weak", extrapolated: false, is_synthetic: false,
      inputs: moved,
    };
    const scene = liveScenario(ignited, moved, preview);
    expect(scene.state).toBe("extinguished");
    expect(scene.burn_probability).toBe(0.2);
    expect(scene.explanation).toBe(ignited.explanation); // the verdict text stays the recorded one
  });

  it.each([
    [false, true, "weak"],
    [true, false, "strong"],
  ] as const)("updates the flame's outside-range flag from %s to %s", (before, after, trust) => {
    const recorded = { ...ignited, extrapolated: before };
    const inputs = { ...recorded.inputs, o2_pct: after ? 40 : 21 };
    const preview: PreviewOut = {
      state: "burning", burn_probability: 0.9, trust, extrapolated: after,
      is_synthetic: false, inputs,
    };
    const scene = liveScenario(recorded, inputs, preview);
    expect(scene.extrapolated).toBe(after);
    expect(scene.trust).toBe(trust);
    expect(flameTarget(scene).extrapolated).toBe(after);
    expect(recorded.extrapolated).toBe(before); // the recorded verdict stays unchanged
  });
});
