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

describe("ISS lab layout (docs/contract.md, 3D coordinate system)", () => {
  it("puts the fire at the module centre", () => {
    expect(FIRE_POS).toEqual([0, 0, 0]);
  });

  it("has the contract's three vents on the overhead rack face, inside the 8.5 m x 4.2 m module", () => {
    expect(VENTS.map(v => v.id)).toEqual(["vent_fwd", "vent_aft", "vent_mid"]);
    expect(VENTS.map(v => v.pos)).toEqual([[4.0, 1.37, 0.0], [-4.0, 1.37, 0.0], [0.0, 1.37, 0.0]]);
    for (const v of VENTS) {
      expect(Math.abs(v.pos[0])).toBeLessThanOrEqual(MODULE.length / 2);
      expect(Math.abs(v.pos[1])).toBeLessThanOrEqual(MODULE.aisle); // visible, not inside a rack
      expect(Math.abs(v.pos[2])).toBeLessThanOrEqual(MODULE.aisle);
    }
  });
});

describe("smoke drifts to the vent downstream of the airflow", () => {
  for (const [flow, vent] of [["fore", "vent_fwd"], ["aft", "vent_aft"]]) {
    it(`${flow} airflow at 0 g trips ${vent} first`, () => {
      expect(first(run(flow, 0))).toBe(vent);
    });
    // At 1 g hot smoke rises straight up from the centre, so the vent above the fire may win.
    it(`${flow} airflow at 1 g trips ${vent} or the vent above the fire first`, () => {
      expect([vent, "vent_mid"]).toContain(first(run(flow, 1)));
    });
  }
  it("with the fans off in 0 g, no vent sees smoke", () => {
    expect(run("off", 0)).toEqual({});
  });
});
