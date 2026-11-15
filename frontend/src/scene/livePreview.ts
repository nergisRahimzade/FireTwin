/* Live 3D preview: while a fire is active and the controls differ from the ignited scenario, the
   scene shows the new settings right away (smoke speed/direction, the flame's oxygen), then the
   model's verdict for them from POST /preview (no scenario is created, nothing is recorded).
   The verdict card, alarm and dashboard keep showing the ignited scenario: pressing Ignite again
   records the new settings. */
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PreviewOut, ScenarioIn, SimulateOut } from "../api/types";

// Wait this long after the last change before asking the API: a slider drag sends one request,
// not one per pixel.
export const PREVIEW_DELAY_MS = 250;

/** True when the controls no longer match the inputs the scenario was ignited with. */
export function inputsDiffer(a: ScenarioIn, b: ScenarioIn): boolean {
  return (
    a.material !== b.material ||
    a.o2_pct !== b.o2_pct ||
    a.flow_speed_cm_s !== b.flow_speed_cm_s ||
    a.pressure_kpa !== b.pressure_kpa ||
    a.flow_dir.some((v, i) => v !== b.flow_dir[i])
  );
}

/** The scene's view of the scenario at new inputs: verdict from the preview when it has one. */
export function liveScenario(sim: SimulateOut, inputs: ScenarioIn, preview: PreviewOut | null): SimulateOut {
  if (!preview) return { ...sim, inputs }; // until the verdict arrives: new airflow/O2, old verdict
  return { ...sim, inputs, state: preview.state, burn_probability: preview.burn_probability };
}

export interface LiveScene {
  scene: SimulateOut | null; // what the 3D view draws
  previewing: boolean; // true while the controls differ from the ignited scenario
}

/** The scenario for the 3D views: the ignited one, or a live preview of changed controls. */
export function useLiveScene(simulate: SimulateOut | null, inputs: ScenarioIn): LiveScene {
  const [preview, setPreview] = useState<PreviewOut | null>(null);
  const previewing = simulate != null && inputsDiffer(simulate.inputs, inputs);

  useEffect(() => {
    setPreview(null);
    if (!simulate || !inputsDiffer(simulate.inputs, inputs)) return;
    let current = true; // drop replies for settings the user has already moved past
    const timer = setTimeout(() => {
      api.preview(inputs)
        .then(p => { if (current) setPreview(p); })
        .catch(() => { /* keep the immediate view; the next change tries again */ });
    }, PREVIEW_DELAY_MS);
    return () => { current = false; clearTimeout(timer); };
  }, [simulate, inputs]);

  if (!simulate || !previewing) return { scene: simulate, previewing: false };
  return { scene: liveScenario(simulate, inputs, preview), previewing: true };
}
