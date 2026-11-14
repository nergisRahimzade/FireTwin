// FE-02: the store's state machine and its calls to the API (the API client is faked).
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DetectOut, SimulateOut, SuppressOut } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";

const fake = vi.hoisted(() => ({
  health: vi.fn(), meta: vi.fn(), simulate: vi.fn(), detect: vi.fn(), suppress: vi.fn(),
  apply: vi.fn(), results: vi.fn(), chat: vi.fn(), exportUrl: vi.fn(),
}));
vi.mock("../api/client", () => ({ api: fake, API_BASE: "http://test" }));

import { initialScenario, nextPhase, useScenario } from "./useScenario";

const sim = (state: SimulateOut["state"], id = "s1"): SimulateOut => ({
  scenario_id: id, state, burn_probability: state === "burning" ? 0.8 : 0.2, spread_rate_mm_s: null,
  trust: "medium", extrapolated: false, nearest_tests: [], explanation: "", inputs: DEFAULT_SCENARIO,
});
const det = (detected: boolean): DetectOut => ({
  detected, detector_id: detected ? "vent_1" : null, time_to_detect_s: detected ? 42 : null, detectors: [],
  note: detected ? "" : "fans off: smoke cannot reach vents",
});
const ranked: SuppressOut = { scenario_id: "s1", recommended: "fans_off", actions: [] };
const store = () => useScenario.getState();

beforeEach(() => {
  vi.clearAllMocks();
  useScenario.setState(initialScenario);
});

describe("nextPhase", () => {
  it("follows the loop: idle -> burning -> detected -> suppressing -> out", () => {
    let p = nextPhase("idle", { type: "simulated", state: "burning" });
    expect(p).toBe("burning");
    p = nextPhase(p, { type: "detected", detected: true });
    expect(p).toBe("detected");
    p = nextPhase(p, { type: "suppress_ranked" });
    expect(p).toBe("suppressing");
    expect(nextPhase(p, { type: "applied", state: "extinguished" })).toBe("out");
    expect(nextPhase(p, { type: "applied", state: "burning" })).toBe("still_burning");
  });
  it("keeps an undetected fire burning", () => {
    expect(nextPhase("burning", { type: "detected", detected: false })).toBe("burning");
  });
  it("a fire that never takes hold is out at once", () => {
    expect(nextPhase("idle", { type: "simulated", state: "extinguished" })).toBe("out");
  });
  it("can try another action after one fails", () => {
    expect(nextPhase("still_burning", { type: "suppress_ranked" })).toBe("suppressing");
  });
});

describe("useScenario store", () => {
  it("ignite calls /simulate with the inputs, then /detect", async () => {
    fake.simulate.mockResolvedValue(sim("burning"));
    fake.detect.mockResolvedValue(det(true));
    store().setInputs({ material: "Cotton", o2_pct: 30 });
    await store().ignite();
    expect(fake.simulate).toHaveBeenCalledWith({ ...DEFAULT_SCENARIO, material: "Cotton", o2_pct: 30 });
    expect(fake.detect).toHaveBeenCalledWith("s1");
    expect(store().phase).toBe("detected");
    expect(store().history).toHaveLength(1);
    expect(store().loading.simulate).toBe(false);
  });

  it("skips /detect when the model says the fire goes out", async () => {
    fake.simulate.mockResolvedValue(sim("extinguished"));
    await store().ignite();
    expect(fake.detect).not.toHaveBeenCalled();
    expect(store().phase).toBe("out");
  });

  it("runs the full loop down to a failed action and a second try", async () => {
    fake.simulate.mockResolvedValue(sim("burning"));
    fake.detect.mockResolvedValue(det(true));
    fake.suppress.mockResolvedValue(ranked);
    await store().ignite();
    await store().runSuppress();
    expect(store().phase).toBe("suppressing");
    fake.apply.mockResolvedValueOnce(sim("burning"));
    await store().runApply("water_mist");
    expect(fake.apply).toHaveBeenCalledWith("s1", "water_mist");
    expect(store().phase).toBe("still_burning");
    await store().runSuppress();
    fake.apply.mockResolvedValueOnce(sim("extinguished"));
    await store().runApply("fans_off");
    expect(store().phase).toBe("out");
    expect(store().history.map(h => h.state)).toEqual(["burning", "burning", "extinguished"]);
  });

  it("records API errors without throwing or changing the phase", async () => {
    fake.simulate.mockRejectedValue(new Error("Can't reach the FireTwin API at http://test."));
    await store().ignite();
    expect(store().error).toMatch(/Can't reach/);
    expect(store().phase).toBe("idle");
    expect(store().loading.simulate).toBe(false);
  });

  it("asks for a scenario before scenario-only calls", async () => {
    expect(await store().runDetect()).toBeNull();
    expect(fake.detect).not.toHaveBeenCalled();
    expect(store().error).toBe("Ignite a scenario first.");
  });

  it("loadMeta fills /meta and picks the first material", async () => {
    fake.meta.mockResolvedValue({ materials: [{ name: "Nomex", fuel_type: "solid", n_tests: 12 }], ranges: {}, investigations: [] });
    await store().loadMeta();
    expect(store().inputs.material).toBe("Nomex");
  });

  it("reset keeps the inputs so the loop can rerun", async () => {
    fake.simulate.mockResolvedValue(sim("burning"));
    fake.detect.mockResolvedValue(det(false));
    store().setInputs({ o2_pct: 34 });
    await store().ignite();
    expect(store().phase).toBe("burning");
    store().reset();
    expect(store().phase).toBe("idle");
    expect(store().simulate).toBeNull();
    expect(store().inputs.o2_pct).toBe(34);
  });
});
