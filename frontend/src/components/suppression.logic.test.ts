import { describe, expect, it } from "vitest";
import { canAct, shouldAutoRank } from "./suppression.logic";

describe("shouldAutoRank", () => {
  it("ranks once the alarm trips", () => {
    expect(shouldAutoRank("vent_aft", false, false)).toBe(true);
  });
  it("waits for the alarm, and never asks twice", () => {
    expect(shouldAutoRank(null, false, false)).toBe(false);
    expect(shouldAutoRank("vent_aft", true, false)).toBe(false);
    expect(shouldAutoRank("vent_aft", false, true)).toBe(false);
  });
});

describe("canAct", () => {
  it("allows Apply while a fire burns, also after a failed action", () => {
    for (const p of ["burning", "detected", "suppressing", "still_burning"] as const) expect(canAct(p)).toBe(true);
  });
  it("blocks Apply when there is no fire", () => {
    expect(canAct("idle")).toBe(false);
    expect(canAct("out")).toBe(false);
  });
});

describe("shouldAutoRank while a saved session replays (FE09-002)", () => {
  it("never ranks a read-only replay, but still ranks a live alarm", () => {
    expect(shouldAutoRank("vent_fwd", false, false, true)).toBe(false);
    expect(shouldAutoRank("vent_fwd", false, false, false)).toBe(true);
    expect(shouldAutoRank("vent_fwd", false, false)).toBe(true); // default: live
  });
});
