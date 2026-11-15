/* FE-04 / FE-12: the detailed ISS lab module from glTF (Blender -> R3F guide, sections 1 and 6).
   Loads frontend/public/models/iss_lab-transformed.glb, built by `npm run model:iss -- <model>`:
   scripts/blender/optimize_iss.py (scale to 8.5 m x 4.2 m, decimate, join by material, vent empties
   at the backend detector positions), then gltfjsx --transform --keepgroups --instance.
   IssScene wraps this in <Suspense fallback={<FallbackModule />}> (the coded module shows while the
   file loads) and an error boundary (the coded module stays if the file is missing or broken).
   Draco data is decoded with the copy in public/draco/, so the demo needs no CDN (OPS-05). */
import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import type * as THREE from "three";
import { VENTS } from "../lab/config.js";
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
      console.warn("ISS model vent empties don't match the contract; rebuild it with npm run model:iss.", problems);
    }
  }, [model]);

  return <primitive object={model} />;
}

// Start downloading the model as soon as this module loads, before anyone presses Ignite.
useGLTF.preload(ISS_LAB_URL, DRACO_PATH);
