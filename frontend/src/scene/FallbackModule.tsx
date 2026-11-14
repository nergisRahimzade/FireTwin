/* FE-04: the coded ISS lab module, shown while the glTF loads and whenever it is missing or broken.
   A cylinder 8.5 m long and 4.2 m across, origin at its centre (+x fore, +y overhead, +z port),
   with rack boxes, lockers, handrails and light strips, all built in code (lab/core.js buildModule).
   Vent markers are not baked in: IssScene draws them at the positions /detect returns. */
import { useEffect, useMemo } from "react";
import type * as THREE from "three";
import { buildModule } from "../lab/core.js";

export function FallbackModule() {
  const module = useMemo(() => buildModule() as THREE.Group, []);
  useEffect(() => () => {
    module.traverse(o => {
      const mesh = o as THREE.Mesh;
      mesh.geometry?.dispose();
      for (const m of mesh.material ? ([] as THREE.Material[]).concat(mesh.material) : []) m.dispose();
    });
  }, [module]);
  return <primitive object={module} />;
}
