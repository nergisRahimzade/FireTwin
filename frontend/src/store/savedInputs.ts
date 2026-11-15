/* FE-03: the "Set up the fire" controls survive a page reload. The setup the user last chose (by
   moving a control, or by pressing Ignite) is kept in this browser's localStorage and read back
   when the page opens. Replays and applied actions also move the controls, but they aren't the
   user's setup, so they don't overwrite it. Only this browser sees it; nothing goes to the API. */
import type { ScenarioIn } from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import { FLOW_DIRS, clampToLimits, sameDir, type SliderKey } from "../components/controlPanel.logic";

// v1: bump it if ScenarioIn changes shape, so an old saved value is ignored instead of misread.
export const SAVED_INPUTS_KEY = "firetwin.controls.v1";
const SLIDERS: SliderKey[] = ["o2_pct", "flow_speed_cm_s", "pressure_kpa"];

// localStorage can be missing (tests, old browsers) or throw (private mode, blocked site data):
// null = no storage, so the controls just start from the defaults.
function storage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** Saves the controls; a storage error is ignored (the app works the same, just without memory). */
export function saveInputs(inputs: ScenarioIn): void {
  try {
    storage()?.setItem(SAVED_INPUTS_KEY, JSON.stringify(inputs));
  } catch {
    /* quota full or storage blocked: nothing to do */
  }
}

/** The saved controls, checked field by field: anything missing or invalid takes its default.
    The material is checked later against /meta (see loadMeta), since the list isn't loaded yet. */
export function loadSavedInputs(): ScenarioIn {
  let saved: unknown = null;
  try {
    saved = JSON.parse(storage()?.getItem(SAVED_INPUTS_KEY) ?? "null");
  } catch {
    return DEFAULT_SCENARIO; // not valid JSON: someone edited it by hand, or an old format
  }
  if (!saved || typeof saved !== "object") return DEFAULT_SCENARIO;
  const s = saved as Record<string, unknown>;
  const inputs: ScenarioIn = { ...DEFAULT_SCENARIO };
  if (typeof s.material === "string") inputs.material = s.material;
  for (const key of SLIDERS) {
    const value = s[key];
    // clampToLimits: a value from an older build with wider sliders still lands on the slider.
    if (typeof value === "number" && Number.isFinite(value)) inputs[key] = clampToLimits(key, value);
  }
  // Only the six axis directions the panel offers; anything else would leave no button pressed.
  // length 3: sameDir only walks the saved array, so [1, 0] would otherwise match [1, 0, 0].
  const saved3 = Array.isArray(s.flow_dir) && s.flow_dir.length === 3 ? (s.flow_dir as ScenarioIn["flow_dir"]) : null;
  const dir = saved3 && FLOW_DIRS.find(d => sameDir(saved3, d.dir));
  if (dir) inputs.flow_dir = dir.dir;
  return inputs;
}
