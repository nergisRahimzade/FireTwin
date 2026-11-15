/* FE-12: the lab model must be an interior: the camera, smoke and fire are all inside the module.
   Rays go out from the fire (0, 0, 0) along all six axes; each must hit a surface that faces back
   at the fire (three.js skips back faces of single-sided materials). An exterior model scaled
   into the module box fails: from inside, its walls face away. */
import * as THREE from "three";

const DIRECTIONS: [string, [number, number, number]][] = [
  ["+x (fore)", [1, 0, 0]], ["-x (aft)", [-1, 0, 0]],
  ["+y (overhead)", [0, 1, 0]], ["-y (deck)", [0, -1, 0]],
  ["+z (port)", [0, 0, 1]], ["-z (starboard)", [0, 0, -1]],
];

/** The directions in which the model leaves the fire open (empty when it encloses it). */
export function openDirections(model: THREE.Object3D, from: [number, number, number] = [0, 0, 0], far = 10): string[] {
  model.updateMatrixWorld(true);
  const ray = new THREE.Raycaster(new THREE.Vector3(...from), new THREE.Vector3(), 0, far);
  return DIRECTIONS.filter(([, d]) => {
    ray.ray.direction.set(...d);
    return ray.intersectObject(model, true).length === 0;
  }).map(([name]) => name);
}
