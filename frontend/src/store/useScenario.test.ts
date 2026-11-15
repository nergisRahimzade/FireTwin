// FE-02: the store's state machine and its calls to the API (the API client is faked).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DetectOut, SimulateOut, SuppressOut } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";

const fake = vi.hoisted(() => ({
  health: vi.fn(), meta: vi.fn(), simulate: vi.fn(), detect: vi.fn(), suppress: vi.fn(),
  apply: vi.fn(), results: vi.fn(), chat: vi.fn(), exportUrl: vi.fn(),
}));
vi.mock("../api/client", () => ({ api: fake, API_BASE: "http://test" }));

import { inputsDiffer } from "../scene/livePreview";
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

  it("Apply moves the controls to the applied settings, so the live 3D preview stays off", async () => {
    fake.simulate.mockResolvedValue(sim("burning"));
    fake.detect.mockResolvedValue(det(true));
    await store().ignite();
    const applied = { ...sim("extinguished"), inputs: { ...DEFAULT_SCENARIO, o2_pct: 15, flow_speed_cm_s: 0 } };
    fake.apply.mockResolvedValueOnce(applied);
    await store().runApply("fans_off_co2");
    expect(store().inputs).toEqual(applied.inputs);
    expect(inputsDiffer(store().simulate!.inputs, store().inputs)).toBe(false);
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

  it("counts ignitions, not backend ids: Ignite again with the same scenario_id is a new ignition", async () => {
    fake.simulate.mockResolvedValue(sim("burning", "synthetic-scenario-001"));
    fake.detect.mockResolvedValue(det(true));
    await store().ignite();
    expect(store().ignitions).toBe(1);
    await store().ignite();
    expect(store().ignitions).toBe(2);
    expect(store().simulate?.scenario_id).toBe("synthetic-scenario-001");
    fake.suppress.mockResolvedValue(ranked);
    fake.apply.mockResolvedValue(sim("extinguished", "synthetic-scenario-001"));
    await store().runApply("fans_off");
    expect(store().ignitions).toBe(2); // /apply is not a new ignition
    store().reset();
    expect(store().ignitions).toBe(2); // keeps counting, so the next Ignite is new
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

  it("records variable edits, use during Ignite, and removal from the active run on Reset", async () => {
    store().setInputs({ material: "Cotton", o2_pct: 30 });
    expect(store().timeline).toContainEqual(expect.objectContaining({
      variable: "Oxygen", action: "modified", from: "21", value: "30",
    }));

    const inputs = { ...DEFAULT_SCENARIO, material: "Cotton", o2_pct: 30 };
    fake.simulate.mockResolvedValue({ ...sim("burning"), inputs });
    fake.detect.mockResolvedValue(det(false));
    await store().ignite();
    expect(store().timeline).toContainEqual(expect.objectContaining({
      variable: "Oxygen", action: "used", value: "30", context: "Ignite",
    }));

    store().reset();
    expect(store().timeline).toContainEqual(expect.objectContaining({
      variable: "Oxygen", action: "removed", value: "30", context: "Scenario reset; removed from active run",
    }));
  });
});

describe("FE-06 alarm in the store (second review)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  async function igniteDetectedAt(seconds: number) {
    fake.simulate.mockResolvedValue(sim("burning", "synthetic-scenario-001"));
    fake.detect.mockResolvedValue({ ...det(true), detector_id: "vent_fwd", time_to_detect_s: seconds });
    await store().ignite();
  }

  it("fires once at time_to_detect_s on the 10x clock, and not again after Compare and back", async () => {
    let trips = 0;
    const unsubscribe = useScenario.subscribe((s, prev) => { if (s.alarmId && !prev.alarmId) trips++; });
    await igniteDetectedAt(40); // 40 s simulated = 4 s real
    const ignitedAt = store().ignitedAt;
    expect(ignitedAt).not.toBeNull();
    vi.advanceTimersByTime(3_900);
    expect(store().alarmId).toBeNull();
    vi.advanceTimersByTime(200);
    expect(store().alarmId).toBe("vent_fwd");
    expect(trips).toBe(1);
    // Compare and back unmounts and remounts the views. They only read the store and schedule
    // nothing, so the clock and alarm are untouched and nothing fires again.
    vi.advanceTimersByTime(20_000);
    expect(trips).toBe(1);
    expect(store().alarmId).toBe("vent_fwd");
    expect(store().ignitedAt).toBe(ignitedAt);
    unsubscribe();
  });

  it("Reset clears the alarm and the clock, and cancels a pending alarm", async () => {
    await igniteDetectedAt(40);
    store().reset();
    expect(store().ignitedAt).toBeNull();
    vi.advanceTimersByTime(10_000);
    expect(store().alarmId).toBeNull();
  });

  it("Ignite again before the alarm drops the earlier ignition's alarm", async () => {
    await igniteDetectedAt(40);
    vi.advanceTimersByTime(2_000);
    await igniteDetectedAt(40); // same mock scenario_id, new ignition: the clock restarts
    vi.advanceTimersByTime(2_500); // 4.5 s after the first ignition, 2.5 s after the second
    expect(store().alarmId).toBeNull();
    vi.advanceTimersByTime(1_600);
    expect(store().alarmId).toBe("vent_fwd");
  });

  it("never alarms when nothing is detected", async () => {
    fake.simulate.mockResolvedValue(sim("burning"));
    fake.detect.mockResolvedValue(det(false));
    await store().ignite();
    vi.advanceTimersByTime(60_000);
    expect(store().alarmId).toBeNull();
  });
});

describe("views read the alarm from the store", () => {
  it("SceneView and CompareView keep no timers or alarm state of their own", () => {
    const files = import.meta.glob(["../components/SceneView.tsx", "../components/CompareView.tsx"], {
      query: "?raw", import: "default", eager: true,
    }) as Record<string, string>;
    expect(Object.keys(files)).toHaveLength(2);
    for (const source of Object.values(files)) {
      expect(source).not.toMatch(/setTimeout|useState|performance\.now/);
      expect(source).toMatch(/useScenario\(s => s\.alarmId\)/);
      expect(source).toMatch(/useScenario\(s => s\.ignitedAt\)/);
    }
  });
});

describe("late replies after Reset are ignored (third review)", () => {
  // A promise the test resolves by hand, to deliver a reply after Reset.
  function deferred<T>() {
    let resolve!: (v: T) => void;
    const promise = new Promise<T>(r => { resolve = r; });
    return { promise, resolve };
  }
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("a /detect reply that arrives after Reset is dropped, and no alarm comes back", async () => {
    fake.simulate.mockResolvedValue(sim("burning", "synthetic-scenario-001"));
    const late = deferred<DetectOut>();
    fake.detect.mockReturnValue(late.promise);
    const igniting = store().ignite(); // /simulate answers, /detect is still in flight
    await vi.waitFor(() => expect(fake.detect).toHaveBeenCalled());
    expect(store().phase).toBe("burning"); // Reset is on screen from here
    store().reset();
    late.resolve({ ...det(true), detector_id: "vent_fwd", time_to_detect_s: 12.5 });
    await igniting;
    expect(store().detect).toBeNull();
    expect(store().phase).toBe("idle");
    vi.advanceTimersByTime(60_000);
    expect(store().alarmId).toBeNull();
  });

  it("late /suppress, /apply and /simulate replies after Reset are dropped too", async () => {
    fake.simulate.mockResolvedValue(sim("burning"));
    fake.detect.mockResolvedValue(det(true));
    await store().ignite();
    const sup = deferred<SuppressOut>(), app = deferred<SimulateOut>();
    fake.suppress.mockReturnValue(sup.promise);
    fake.apply.mockReturnValue(app.promise);
    const s1 = store().runSuppress(), a1 = store().runApply("fans_off");
    store().reset();
    sup.resolve(ranked);
    app.resolve(sim("burning"));
    expect(await s1).toBeNull();
    expect(await a1).toBeNull();
    expect(store().suppress).toBeNull();
    expect(store().simulate).toBeNull(); // the fire doesn't come back on screen

    const simLate = deferred<SimulateOut>();
    fake.simulate.mockReturnValue(simLate.promise);
    const igniting = store().ignite();
    store().reset();
    simLate.resolve(sim("burning", "late"));
    await igniting;
    expect(store().simulate).toBeNull();
    expect(store().phase).toBe("idle");
  });

  it("a /detect reply from an earlier ignition is dropped once the next ignition has started", async () => {
    fake.simulate.mockResolvedValue(sim("burning", "synthetic-scenario-001"));
    const first = deferred<DetectOut>();
    fake.detect.mockReturnValueOnce(first.promise).mockResolvedValueOnce(det(false));
    const one = store().ignite();
    await vi.waitFor(() => expect(fake.detect).toHaveBeenCalledTimes(1));
    await store().ignite(); // Ignite again: its own /detect says "not detected"
    first.resolve({ ...det(true), detector_id: "vent_fwd", time_to_detect_s: 12.5 });
    await one;
    expect(store().detect?.detected).toBe(false);
    vi.advanceTimersByTime(60_000);
    expect(store().alarmId).toBeNull();
  });

  it("a stale request that fails doesn't show its error after Reset", async () => {
    fake.simulate.mockResolvedValue(sim("burning"));
    const late = deferred<DetectOut>();
    fake.detect.mockReturnValue(late.promise.then(() => { throw new Error("detect failed"); }));
    const igniting = store().ignite();
    await vi.waitFor(() => expect(fake.detect).toHaveBeenCalled());
    store().reset();
    late.resolve(det(true));
    await igniting;
    expect(store().error).toBeNull();
  });
});

describe("auto-ranking sends one /suppress per alarm", () => {
  it("the ranking is saved before loading clears, so the auto-rank rule can't fire twice", async () => {
    // SuppressionPanel auto-ranks while there's an alarm, no ranking yet and nothing loading.
    // React re-renders on every store change, so run that rule on every change here.
    const { shouldAutoRank } = await import("../components/suppression.logic");
    fake.suppress.mockImplementation(() => new Promise(r => setTimeout(() => r(ranked), 5)));
    useScenario.setState({ simulate: sim("burning"), alarmId: null, suppress: null });
    const unsubscribe = useScenario.subscribe(s => {
      if (shouldAutoRank(s.alarmId, s.suppress != null, s.loading.suppress)) void s.runSuppress();
    });
    useScenario.setState({ alarmId: "vent_1" });
    await new Promise(r => setTimeout(r, 50));
    unsubscribe();
    expect(fake.suppress).toHaveBeenCalledTimes(1);
    expect(store().suppress).toEqual(ranked);
  });
});
