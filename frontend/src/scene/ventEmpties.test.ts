// FE-12: a model's vent empties against the contract vents (src/lab/config.js).
import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { VENTS } from "../lab/config.js";
import { checkVentEmpties } from "./ventEmpties";

// A stand-in for the exported GLB: empties named like the detectors, as optimize_iss.py makes them.
function modelWith(positions: Record<string, [number, number, number]>, parentOffset: [number, number, number] = [0, 0, 0]) {
  const root = new THREE.Group();
  const group = new THREE.Group(); // gltfjsx --keepgroups keeps nesting like this
  group.position.set(...parentOffset);
  root.add(group);
  for (const [id, p] of Object.entries(positions)) {
    const empty = new THREE.Object3D();
    empty.name = id;
    empty.position.set(p[0] - parentOffset[0], p[1] - parentOffset[1], p[2] - parentOffset[2]);
    group.add(empty);
  }
  return root;
}
const contract = Object.fromEntries(VENTS.map(v => [v.id, v.pos as [number, number, number]]));

describe("checkVentEmpties", () => {
  it("accepts a model whose empties sit at the contract vents (world positions, through groups)", () => {
    expect(checkVentEmpties(modelWith(contract, [1, 2, 3]), VENTS)).toEqual([]);
  });

  it("reports a missing vent and one moved by more than 5 cm", () => {
    const moved = { ...contract, vent_mid: [0, 1.5, 0] as [number, number, number] };
    delete (moved as Record<string, unknown>).vent_aft;
    const problems = checkVentEmpties(modelWith(moved), VENTS);
    expect(problems.map(p => [p.id, p.problem])).toEqual([["vent_aft", "missing"], ["vent_mid", "moved"]]);
    expect(problems[1].distanceM).toBeCloseTo(0.13, 5);
  });

  it("tolerates small export rounding", () => {
    const nudged = { ...contract, vent_fwd: [4.01, 1.37, 0] as [number, number, number] };
    expect(checkVentEmpties(modelWith(nudged), VENTS)).toEqual([]);
  });
});
