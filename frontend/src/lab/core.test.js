// The 3D lab's smoke model, run headless: does the smoke end up where the airflow sends it?
import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { AIRFLOW, FIRE_POS, MODULE, Smoke, VENTS, buildVents } from "./core.js";

// Burn for `seconds` of simulated time; return {vent id: first detection time}.
function run(flowId, g, seconds = 25) {
  const vents = buildVents(), smoke = new Smoke(), hits = {};
  const flow = AIRFLOW.find(a => a.id === flowId), src = new THREE.Vector3().fromArray(FIRE_POS);
  const p = { rate: 90, g, flow, src, radius: 0.15 };
  for (let t = 0; t < seconds; t += 1 / 60) {
    smoke.step(1 / 60, p, vents.items, v => { if (!(v.id in hits)) hits[v.id] = t; });
  }
  return hits;
}
const first = hits => Object.entries(hits).sort((a, b) => a[1] - b[1])[0]?.[0];

describe("ISS lab layout", () => {
  it("has the three named vents inside the 8.5 m x 4.2 m module", () => {
    expect(VENTS.map(v => v.id)).toEqual(["vent_1", "vent_2", "vent_3"]);
    for (const v of VENTS) {
      expect(Math.abs(v.pos[0])).toBeLessThanOrEqual(MODULE.length / 2);
      expect(Math.hypot(v.pos[1], v.pos[2])).toBeLessThanOrEqual(MODULE.diameter / 2);
    }
  });
});

describe("smoke drifts to the vent downstream of the airflow", () => {
  for (const [flow, vent] of [["fore", "vent_1"], ["aft", "vent_2"], ["starboard", "vent_3"]]) {
    for (const g of [0, 1]) {
      // Aft at 1 g: vent_2 is on the deck and hot smoke rises away from it, so sometimes no
      // vent trips at all. What must never happen is a different vent tripping first.
      const deckVentIn1g = flow === "aft" && g === 1;
      it(`${flow} airflow at ${g} g trips ${vent} first${deckVentIn1g ? " (or none)" : ""}`, () => {
        const got = first(run(flow, g));
        if (deckVentIn1g) expect([vent, undefined]).toContain(got);
        else expect(got).toBe(vent);
      });
    }
  }
  it("with the fans off in 0 g, no vent sees smoke", () => {
    expect(run("off", 0)).toEqual({});
  });
});
