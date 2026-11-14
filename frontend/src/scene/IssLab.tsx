/* FE-04: the ISS lab module from glTF (Blender guide, sections 1 and 6).
   Expects frontend/public/models/iss_lab-transformed.glb from gltfjsx --transform: metres, origin at
   the module centre, vent empties named like the detector ids. Until that file exists, the load
   fails and IssScene shows the coded FallbackModule instead.
   Draco files are decoded with the copy in public/draco/, so the demo needs no CDN (OPS-05). */
import { useGLTF } from "@react-three/drei";

export const ISS_LAB_URL = "/models/iss_lab-transformed.glb";
export const DRACO_PATH = "/draco/";

export function IssLab() {
  const { scene } = useGLTF(ISS_LAB_URL, DRACO_PATH);
  return <primitive object={scene} />;
}

// Start downloading the model as soon as this module loads, before anyone presses Ignite.
useGLTF.preload(ISS_LAB_URL, DRACO_PATH);
