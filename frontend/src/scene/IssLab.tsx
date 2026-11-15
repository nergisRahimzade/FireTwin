/* FE-04 / FE-12: the detailed ISS lab module interior from glTF (Blender -> R3F guide, sections 1 and 6).
   Loads frontend/public/models/iss_lab-transformed.glb: the inside of one lab module (racks,
   lockers, handrails, ceiling lights, vent grilles, hatches), never the station's exterior, because
   the camera, smoke and fire are all inside it. Built by `npm run model:interior`:
   scripts/blender/generate_interior.py models it procedurally (NASA publishes no interior model),
   optimize_iss.py fits it to 8.5 m x 4.2 m and places the vent empties at the backend detector
   positions, then glTF Transform compresses it (Draco, prune keeping the empties). Any other source
   model goes through the same pipeline with `npm run model:iss -- <model>`.
   The camera starts in the aisle and stays there (lab/core.js CAMERA_START, clampCamera).
   IssScene wraps this in <Suspense fallback={<FallbackModule />}> (the coded module shows while the
   file loads) and an error boundary (the coded module stays if the file is missing or broken).
   Draco data is decoded with the copy in public/draco/, so the demo needs no CDN (OPS-05). */
import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import type * as THREE from "three";
import { VENTS } from "../lab/config.js";
import { openDirections } from "./interiorCheck";
import { checkVentEmpties } from "./ventEmpties";

export const ISS_LAB_URL = "/models/iss_lab-transformed.glb";
export const DRACO_PATH = "/draco/";

export function IssLab() {
  const { scene } = useGLTF(ISS_LAB_URL, DRACO_PATH);
  // Each 3D view (main page, Compare) gets its own copy: one three.js object can only sit in one
  // scene at a time. Geometry and materials are shared, so a copy costs almost nothing.
  const model = useMemo(() => {
    const copy = scene.clone(true);
    copy.traverse(o => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = false; // guide: shadows off on the module
        mesh.receiveShadow = false;
      }
    });
    return copy;
  }, [scene]);

  // Development check: the model's vent empties must match the contract (docs/contract.md), or
  // smoke would visibly reach one vent while another trips the alarm.
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const problems = checkVentEmpties(model, VENTS as { id: string; pos: number[] }[]);
    if (problems.length) {
      console.warn("ISS model vent empties don't match the contract; rebuild it with npm run model:interior.", problems);
    }
    // ...and it must be an interior: walls facing the fire in every direction (not an exterior shell).
    const open = openDirections(model);
    if (open.length) {
      console.warn("ISS model doesn't enclose the fire, so it isn't an interior; open towards:", open.join(", "));
    }
  }, [model]);

  return <primitive object={model} />;
}

// Start downloading the model as soon as this module loads, before anyone presses Ignite.
useGLTF.preload(ISS_LAB_URL, DRACO_PATH);
