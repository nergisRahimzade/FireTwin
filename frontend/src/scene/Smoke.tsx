/* FE-06: smoke from the fire at the module centre (docs/contract.md: (0, 0, 0)), drifting along
   flow_dir at the scenario's airflow speed on the 10x demo clock. One <points> object (one draw
   call): SmokeDriver (smokeLogic.ts) mutates the lab/core.js Smoke buffers in useFrame.
   syncSmoke decides when the cloud resets: cleared on Reset (no scenario), restarted on a new
   ignition, caught up to the current moment when this view mounts mid-ignition (Compare and back),
   kept through /apply. Elapsed time is simulated in full through bounded substeps.
   No React state is set; the component only re-renders when the scenario changes.
   Smoke never decides which vent trips: the alarm follows /detect. */
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { SimulateOut } from "../api/types";
import { CAMERA_FOV } from "../lab/core.js";
import { SmokeDriver, smokeSettings, syncSmoke } from "./smokeLogic";

interface SmokeProps {
  simulate: SimulateOut | null;
  ignition: number; // the store's ignition counter
  ignitedAt: number | null; // Date.now() at this ignition (store)
}

export function Smoke({ simulate, ignition, ignitedAt }: SmokeProps) {
  const settings = useMemo(() => smokeSettings(simulate), [simulate]);
  const { size, gl } = useThree();
  const driver = useRef<SmokeDriver>(null as unknown as SmokeDriver);
  if (!driver.current) driver.current = new SmokeDriver(1600);

  useEffect(() => { syncSmoke(driver.current, simulate, ignition, ignitedAt); }, [simulate, ignition, ignitedAt]);
  useEffect(() => driver.current.smoke.setScale(size.height * gl.getPixelRatio(), CAMERA_FOV), [size.height, gl]);
  useEffect(() => {
    const s = driver.current.smoke;
    return () => { s.geometry.dispose(); s.material.dispose(); };
  }, []);

  useFrame((_, delta) => {
    if (simulate) driver.current.advance(delta, settings);
  });

  return (
    <points
      geometry={driver.current.smoke.geometry}
      material={driver.current.smoke.material}
      frustumCulled={false}
      name="smoke"
    />
  );
}
