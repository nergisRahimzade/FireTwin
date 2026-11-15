/* FE-06: smoke from the fire at the module centre (docs/contract.md: (0, 0, 0)), drifting along
   flow_dir at the scenario's airflow speed on the 10x demo clock. One <points> object (one draw
   call) drawing the shared SmokeDriver for this ignition (smokeLogic.ts):
   - every 3D view (main page, Compare) draws the same driver, so switching views keeps the cloud
     as it is, including smoke still fading after the fire is put out;
   - a new ignition gets a new, empty driver; Reset (no scenario) clears it; /apply keeps it;
   - elapsed time is simulated in full through bounded substeps.
   No React state is set; the component only re-renders when the scenario changes.
   Smoke never decides which vent trips: the alarm follows /detect. */
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import type { SimulateOut } from "../api/types";
import { CAMERA_FOV } from "../lab/core.js";
import { smokeDriverFor, smokeSettings, syncSmoke } from "./smokeLogic";

interface SmokeProps {
  simulate: SimulateOut | null;
  ignition: number; // the store's ignition counter: picks this ignition's shared driver
}

export function Smoke({ simulate, ignition }: SmokeProps) {
  const settings = useMemo(() => smokeSettings(simulate), [simulate]);
  const driver = useMemo(() => smokeDriverFor(ignition), [ignition]);
  const { size, gl } = useThree();

  // Opening this view: catch up the moment since the other view last drew the cloud.
  // eslint isn't set up here; this effect intentionally runs only when the driver (view or ignition) changes.
  useEffect(() => { if (simulate) driver.resume(smokeSettings(simulate)); }, [driver]);
  useEffect(() => { syncSmoke(driver, simulate); }, [driver, simulate]);
  useEffect(() => driver.smoke.setScale(size.height * gl.getPixelRatio(), CAMERA_FOV), [driver, size.height, gl]);

  useFrame((_, delta) => {
    if (simulate) driver.advance(delta, settings);
  });

  return <points geometry={driver.smoke.geometry} material={driver.smoke.material} frustumCulled={false} name="smoke" />;
}
