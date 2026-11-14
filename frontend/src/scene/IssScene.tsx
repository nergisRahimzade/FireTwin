/* FE-04/05/06: the ISS lab twin, driven only by API results (SimulateOut, DetectOut).
   - FE-04: coded module (no .glb), detectors at the positions /detect returns.
   - FE-05: flame sized by burn_probability and spread_rate_mm_s, stretched along flow_dir as the
     airflow rises, grey stripes + "outside tested range" when extrapolated, fades over ~2 s when
     the model says it goes out.
   - FE-06: smoke drifts along flow_dir at the flow speed; the alarm follows time_to_detect_s on a
     10x demo clock. The alarm comes from the API, not from particles touching a vent.
   Per frame only three.js objects and refs change; React state changes once, when the alarm trips. */
import { Html, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { type MutableRefObject, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { DetectOut, SimulateOut } from "../api/types";
import { CAMERA_FOV, CAMERA_START, Flame, Smoke, buildModule, clampCamera } from "../lab/core.js";
import {
  FIRE_POSITION, SCENE_TIME_SCALE, alarmAfterS, detectorMarks, flameTarget, flowOf,
} from "./sceneLogic";

const IDLE_COLOR = new THREE.Color(0x63e6be);
const ALARM_COLOR = new THREE.Color(0xff5a4a);
const UP = new THREE.Vector3(0, 1, 0);

function stripesMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uOpacity: { value: 0.55 } },
    vertexShader: "varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: "uniform float uOpacity; varying vec3 vP; void main(){ if (fract((vP.x + vP.y) * 4.0) < 0.5) discard; gl_FragColor = vec4(vec3(0.62), uOpacity);\n#include <colorspace_fragment>\n}",
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
  });
}

interface TwinProps {
  simulate: SimulateOut | null;
  detect: DetectOut | null;
  alarmId: string | null;
  clockEl: MutableRefObject<HTMLSpanElement | null>;
  onAlarm: (id: string) => void;
}

function Twin({ simulate, detect, alarmId, clockEl, onAlarm }: TwinProps) {
  const { camera, size, gl } = useThree();
  const world = useMemo(() => {
    const flame = new Flame();
    flame.group.position.set(...FIRE_POSITION);
    const stripes = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), stripesMaterial());
    stripes.visible = false;
    flame.group.add(stripes);
    // Draw the (additive) flame after the smoke, so the smoke never hides it.
    flame.group.traverse(o => { o.renderOrder = 10; });
    return { module: buildModule(), flame, stripes, smoke: new Smoke(1600) };
  }, []);
  const clock = useRef({ id: null as string | null, t: 0, alarmed: false });
  const halos = useRef<Record<string, THREE.Mesh | null>>({});
  const target = useMemo(() => flameTarget(simulate), [simulate]);
  const flow = useMemo(() => flowOf(simulate?.inputs), [simulate]);
  const alarmAt = useMemo(() => alarmAfterS(detect), [detect]);
  const marks = useMemo(() => detectorMarks(detect), [detect]);
  const smokeParams = useMemo(
    () => ({ rate: 0, g: 0, flow: { dir: [1, 0, 0], fans: false }, speed: 0, src: world.flame.group.position, radius: 0.1, life: 60 }),
    [world],
  );

  // A new scenario restarts the demo clock and clears the old smoke.
  const id = simulate?.scenario_id ?? null;
  useEffect(() => {
    if (clock.current.id !== id) {
      clock.current = { id, t: 0, alarmed: false };
      world.smoke.reset();
    }
  }, [id, world]);
  useEffect(() => { clock.current.alarmed = false; }, [detect]);
  useEffect(() => world.smoke.setScale(size.height * gl.getPixelRatio(), CAMERA_FOV), [size.height, gl, world]);
  useEffect(() => () => {
    for (const root of [world.module, world.flame.group]) {
      root.traverse(o => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose();
        for (const m of mesh.material ? ([] as THREE.Material[]).concat(mesh.material) : []) m.dispose();
      });
    }
    world.smoke.geometry.dispose();
    world.smoke.material.dispose();
  }, [world]);

  useFrame((_, delta) => {
    const dt = Math.min(0.05, delta), c = clock.current;
    if (simulate) c.t += dt; // real seconds since this scenario ignited
    if (clockEl.current) clockEl.current.textContent = (c.t * SCENE_TIME_SCALE).toFixed(1);
    if (alarmAt != null && !c.alarmed && c.t >= alarmAt && detect?.detector_id) {
      c.alarmed = true;
      onAlarm(detect.detector_id);
    }

    // Flame (real-time easing, so going out takes ~2 s)
    const f = world.flame;
    f.update(dt, c.t * 2.5, { g: target.stretch, o2: target.o2, burnP: target.burnP, alive: target.alive });
    if (flow.fans) f.tear.quaternion.setFromUnitVectors(UP, new THREE.Vector3(...flow.dir));
    f.group.scale.setScalar(target.spreadScale);
    world.stripes.visible = target.extrapolated && f.size > 0.01;
    world.stripes.scale.setScalar(Math.max(1e-4, f.size * 1.35));

    // Smoke, on the 10x demo clock. No buoyancy: in microgravity it only moves with the air.
    if (simulate) {
      smokeParams.rate = f.alive * (12 + 18 * target.burnP);
      smokeParams.flow = { dir: flow.dir, fans: flow.fans };
      smokeParams.speed = flow.speedMS;
      smokeParams.radius = Math.max(0.06, f.size);
      world.smoke.step(dt * SCENE_TIME_SCALE, smokeParams, [], () => {});
    }

    // Tripped detector pulses red
    const pulse = 1 + 0.35 * (0.5 + 0.5 * Math.sin(c.t * 10));
    for (const [hid, mesh] of Object.entries(halos.current)) mesh?.scale.setScalar(hid === alarmId ? pulse : 1);
    clampCamera(camera);
  });

  return (
    <>
      <primitive object={world.module} />
      <primitive object={world.flame.group} />
      {/* Smoke: one <points>, one draw call; its buffers change in place each frame */}
      <points geometry={world.smoke.geometry} material={world.smoke.material} frustumCulled={false} />
      {marks.map(m => {
        const tripped = m.id === alarmId;
        const color = tripped ? ALARM_COLOR : IDLE_COLOR;
        return (
          <group key={m.id} position={m.position}>
            <mesh><sphereGeometry args={[0.05, 16, 12]} /><meshBasicMaterial color={color} /></mesh>
            <mesh ref={el => { halos.current[m.id] = el; }}>
              <sphereGeometry args={[0.16, 24, 16]} />
              <meshBasicMaterial color={color} transparent opacity={tripped ? 0.45 : 0.18} depthWrite={false} blending={THREE.AdditiveBlending} />
            </mesh>
            <Html center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
              <div className={`lab3d-tag r3f ${tripped ? "hit" : "vent"}`}>
                {m.id}{tripped ? " · alarm" : ""}{m.synthetic ? " · synthetic" : ""}
              </div>
            </Html>
          </group>
        );
      })}
      {target.extrapolated && target.alive === 1 && (
        <Html position={[FIRE_POSITION[0], FIRE_POSITION[1] + 0.45, FIRE_POSITION[2]]} center style={{ pointerEvents: "none" }}>
          <div className="lab3d-tag r3f extrapolated">outside tested range</div>
        </Html>
      )}
    </>
  );
}

export function IssScene(props: TwinProps) {
  return (
    <Canvas
      flat
      dpr={[1, 2]}
      camera={{ position: CAMERA_START as [number, number, number], fov: CAMERA_FOV, near: 0.05, far: 30 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onCreated={({ scene }) => { scene.background = new THREE.Color(0x05080f); }}
      fallback={<div className="lab3d-msg">WebGL is off, so the 3D view can't start.</div>}
    >
      <Twin {...props} />
      <OrbitControls makeDefault enableDamping enablePan={false} minDistance={0.6} maxDistance={4.2} />
    </Canvas>
  );
}
