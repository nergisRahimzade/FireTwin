import { describe, expect, it } from "vitest";
import type { ResultsRow } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import { changeText, o2Sweep, resultText, sourceId, stampRows } from "./dashboard.logic";

const row = (patch: Partial<ResultsRow>): ResultsRow => ({
  step: "simulate", inputs: { ...DEFAULT_SCENARIO, material: "PMMA", o2_pct: 21, flow_speed_cm_s: 10 },
  state: "burning", probability: 0.93, trust: "medium", detection_s: null, action: null, sources: [], ...patch,
});

describe("dashboard rows", () => {
  it("describes a prediction, a detection and an applied action", () => {
    expect(resultText(row({}))).toBe("burning · 93% burn · trust medium");
    expect(resultText(row({ step: "detect", state: null, probability: null, trust: null, detection_s: 40 }))).toBe("alarm after 40 s");
    expect(resultText(row({ step: "detect", state: null, probability: null, trust: null }))).toBe("not detected");
    expect(changeText(row({}))).toBe("PMMA, 21% O₂, 10 cm/s");
    expect(changeText(row({ step: "apply", action: "fans_off" }))).toBe("action: fans_off");
  });

  it("reads sources sent as ids or as test refs", () => {
    expect(sourceId("SYN-1")).toBe("SYN-1");
    expect(sourceId({ test_id: "T-2" } as never)).toBe("T-2");
  });

  it("sweeps O2 from 10 to 40 %", () => {
    expect(o2Sweep()).toEqual([10, 15, 20, 25, 30, 35, 40]);
  });

  it("keeps old time stamps and stamps new rows", () => {
    expect(stampRows(["a"], 3, "b")).toEqual(["a", "b", "b"]);
    expect(stampRows(["a", "b"], 0, "c")).toEqual([]);
  });
});
