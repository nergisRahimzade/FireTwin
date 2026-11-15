/* FE-06: smoke from the fire at the module centre (docs/contract.md: (0, 0, 0)), drifting along
   flow_dir at the scenario's airflow speed on the 10x demo clock. One <points> object (one draw
   call) from lab/core.js Smoke: positions, sizes and alphas live in its typed arrays and are
   mutated in useFrame. No React state is set; the component only re-renders when a new
   SimulateOut arrives. Smoke never decides which vent trips: the alarm follows /detect. */
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { SimulateOut } from "../api/types";
import { FIRE_POS } from "../lab/config.js";
import { CAMERA_FOV, Smoke as CoreSmoke } from "../lab/core.js";
import { SCENE_TIME_SCALE, SMOKE_LIFE_S, smokeSettings } from "./smokeLogic";

export function Smoke({ simulate }: { simulate: SimulateOut | null }) {
  const settings = useMemo(() => smokeSettings(simulate), [simulate]);
  const { size, gl } = useThree();
  const smoke = useRef<CoreSmoke>(null as unknown as CoreSmoke);
  if (!smoke.current) smoke.current = new CoreSmoke(1600);
  const params = useRef({
    rate: 0, g: 0, flow: { dir: [1, 0, 0], fans: false }, speed: 0,
    src: new THREE.Vector3(...(FIRE_POS as [number, number, number])), radius: 0.12, life: SMOKE_LIFE_S,
  });
  const scenarioId = useRef<string | null>(null);

  // A new scenario starts with clean air.
  useEffect(() => {
    const id = simulate?.scenario_id ?? null;
    if (id !== scenarioId.current) {
      scenarioId.current = id;
      smoke.current.reset();
    }
  }, [simulate]);
  useEffect(() => smoke.current.setScale(size.height * gl.getPixelRatio(), CAMERA_FOV), [size.height, gl]);
  useEffect(() => {
    const s = smoke.current;
    return () => { s.geometry.dispose(); s.material.dispose(); };
  }, []);

  useFrame((_, delta) => {
    if (!simulate) return;
    const p = params.current;
    p.rate = settings.rate; // 0 once extinguished: the last smoke drifts on and fades
    p.flow.dir = settings.dir;
    p.flow.fans = settings.fans;
    p.speed = settings.speedMS;
    smoke.current.step(Math.min(0.05, delta) * SCENE_TIME_SCALE, p, [], () => {});
  });

  return (
    <points
      geometry={smoke.current.geometry}
      material={smoke.current.material}
      frustumCulled={false}
      name="smoke"
    />
  );
}
