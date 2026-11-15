/* FE-12: the Blender pipeline (scripts/blender/optimize_iss.py) puts a named empty at every vent
   detector in the backend config. This checks a loaded model against the contract vents
   (src/lab/config.js, the same numbers as ml/pipeline/config.py), so a model built from an old
   config, or a vent moved by hand in Blender, is caught in development instead of on stage. */
import type * as THREE from "three";

export interface VentSpec {
  id: string;
  pos: [number, number, number] | number[];
}

export interface VentProblem {
  id: string;
  problem: "missing" | "moved";
  found?: [number, number, number];
  distanceM?: number;
}

const TOLERANCE_M = 0.05; // 5 cm

export function checkVentEmpties(model: THREE.Object3D, vents: VentSpec[], toleranceM = TOLERANCE_M): VentProblem[] {
  model.updateMatrixWorld(true);
  const problems: VentProblem[] = [];
  for (const vent of vents) {
    const node = model.getObjectByName(vent.id);
    if (!node) {
      problems.push({ id: vent.id, problem: "missing" });
      continue;
    }
    const e = node.matrixWorld.elements; // world position of the empty
    const found: [number, number, number] = [e[12], e[13], e[14]];
    const d = Math.hypot(found[0] - vent.pos[0], found[1] - vent.pos[1], found[2] - vent.pos[2]);
    if (d > toleranceM) problems.push({ id: vent.id, problem: "moved", found, distanceM: d });
  }
  return problems;
}
