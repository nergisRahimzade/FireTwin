/* FE-06 alarm: when the smoke alarm shows, and what the banner says. Pure, so it's unit-tested.
   The alarm follows DetectOut from the API (time_to_detect_s), never the particles: the smoke only
   illustrates. On the 10x demo clock, a detector that trips at 40 s shows red after 4 real seconds. */
import type { DetectOut } from "../api/types";
import { SCENE_TIME_SCALE } from "./clock";

// Real seconds after ignition when the alarm shows, or null if no detector ever trips.
export function alarmAfterS(detect: DetectOut | null, scale = SCENE_TIME_SCALE): number | null {
  if (!detect?.detected || detect.time_to_detect_s == null || !detect.detector_id) return null;
  return Math.max(0, detect.time_to_detect_s) / scale;
}

export interface Banner {
  kind: "alarm" | "note";
  text: string;
}

// alarm: the clock reached time_to_detect_s. note: no detector ever sees the smoke (DetectOut.note).
export function alarmBanner(detect: DetectOut | null, tripped: boolean): Banner | null {
  if (!detect) return null;
  if (!detect.detected) return { kind: "note", text: detect.note || "No detector sees the smoke." };
  if (!tripped) return null;
  const t = detect.time_to_detect_s;
  return {
    kind: "alarm",
    text: `Alarm: ${detect.detector_id} detected smoke ${t == null ? "" : `${t.toFixed(1)} s `}after ignition.`,
  };
}
