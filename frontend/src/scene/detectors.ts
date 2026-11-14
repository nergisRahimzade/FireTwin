/* FE-04: detector markers come only from POST /detect (DetectOut.detectors), so the 3D vents are
   always exactly where the backend's detector (BE-03) says. Metres, origin at the module centre. */
import type { DetectOut, Vec3 } from "../api/types";

export interface DetectorMark {
  id: string;
  position: Vec3;
  synthetic: boolean; // rule 5: placeholder positions get a "synthetic" label
}

// Entries without an id or a 3-number position are skipped, never guessed.
export function detectorMarks(detect: DetectOut | null): DetectorMark[] {
  return (detect?.detectors ?? []).flatMap(d => {
    const p = (d as { position?: unknown }).position;
    if (typeof d.id !== "string" || !Array.isArray(p) || p.length !== 3 || !p.every(n => Number.isFinite(n))) return [];
    const synthetic = (d as { is_synthetic?: unknown }).is_synthetic === true;
    return [{ id: d.id, position: [p[0], p[1], p[2]] as Vec3, synthetic }];
  });
}
