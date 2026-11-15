// FE-03: the controls survive a page reload (saved in this browser's localStorage).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_SCENARIO } from "../api/types";
import { SAVED_INPUTS_KEY, loadSavedInputs, saveInputs } from "./savedInputs";

// A Map-backed stand-in for localStorage (the test environment has none).
function fakeStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}
let store: ReturnType<typeof fakeStorage>;
const saved = (value: unknown) => store.setItem(SAVED_INPUTS_KEY, JSON.stringify(value));

beforeEach(() => {
  store = fakeStorage();
  vi.stubGlobal("localStorage", store);
});
afterEach(() => vi.unstubAllGlobals());

describe("saved controls", () => {
  it("come back exactly as saved", () => {
    const setup = { ...DEFAULT_SCENARIO, material: "Black rod", o2_pct: 26, flow_speed_cm_s: 16, flow_dir: [0, 1, 0] as [number, number, number] };
    saveInputs(setup);
    expect(loadSavedInputs()).toEqual(setup);
  });
  it("start from the defaults when nothing is saved", () => {
    expect(loadSavedInputs()).toEqual(DEFAULT_SCENARIO);
  });
  it("start from the defaults when the saved text isn't JSON", () => {
    store.setItem(SAVED_INPUTS_KEY, "{not json");
    expect(loadSavedInputs()).toEqual(DEFAULT_SCENARIO);
  });
  it("replace only the invalid fields with their defaults", () => {
    saved({ material: 42, o2_pct: "26", flow_speed_cm_s: 16, flow_dir: [1, 0] });
    expect(loadSavedInputs()).toEqual({ ...DEFAULT_SCENARIO, flow_speed_cm_s: 16 });
  });
  it("snap out-of-range numbers onto the sliders", () => {
    saved({ o2_pct: 90, flow_speed_cm_s: -3 });
    expect(loadSavedInputs()).toMatchObject({ o2_pct: 40, flow_speed_cm_s: 0 });
  });
  it("accept only the six axis directions the panel offers", () => {
    saved({ flow_dir: [0.6, 0.8, 0] });
    expect(loadSavedInputs().flow_dir).toEqual(DEFAULT_SCENARIO.flow_dir);
  });
  it("keep the app working when storage is blocked", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
    });
    expect(() => saveInputs(DEFAULT_SCENARIO)).not.toThrow();
    expect(loadSavedInputs()).toEqual(DEFAULT_SCENARIO);
  });
});
