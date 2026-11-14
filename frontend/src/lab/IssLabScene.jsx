/* The 3D ISS lab drawn with React Three Fiber.
   The module, vents, flame and smoke all come from ./core.js (pure code, no .glb or Draco),
   so this file only wires them into the R3F frame loop.

   Performance rules from the team's Blender/R3F guide:
   - smoke is ONE <points> object (one draw call), its buffers are mutated in place;
   - useFrame only mutates refs and three.js objects; it never calls setState.
     React state changes only on events (ignite, flame out, a vent detecting smoke). */
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import { useEffect, useImperativeHandle, useMemo, useRef } from "react";
import * as THREE from "three";
import {
  AIRFLOW, CAMERA_FOV, CAMERA_START, FIRE_POS, Flame, Smoke, TIME_SCALE,
  buildModule, buildVents, clampCamera, oxygenK,
} from "./core.js";

function disposeAll(...roots) {
  for (const root of roots) root.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    for (const m of o.material ? [].concat(o.material) : []) { if (m.map) m.map.dispose(); m.dispose(); }
  });
}

function Lab({ params, api, clockEl, onEvent }) {
  const { camera, size, gl } = useThree();
  const world = useMemo(() => ({ module: buildModule(), vents: buildVents(), flame: new Flame(), smoke: new Smoke() }), []);
  const sim = useRef({ running: false, alive: 0, simT: 0, outAt: null, t: 0 });
  const tags = useRef({});
  const P = useRef(params);
  P.current = params; // read inside useFrame, so moving a slider never rebuilds anything
  const fp = useMemo(() => ({ g: 0, o2: 21, burnP: 0.5, alive: 0 }), []);
  const sp = useMemo(() => ({ rate: 0, g: 0, flow: AIRFLOW[0], src: world.flame.group.position, radius: 0.1 }), [world]);

  useEffect(() => world.smoke.setScale(size.height * gl.getPixelRatio(), CAMERA_FOV), [size.height, gl, world]);
  useEffect(() => () => { disposeAll(world.module, world.vents.group, world.flame.group); world.smoke.geometry.dispose(); world.smoke.material.dispose(); }, [world]);

  const onHit = v => {
    if (v.triggered) return;
    world.vents.trigger(v);
    const el = tags.current[v.id];
    if (el) { el.classList.add("hit"); el.textContent = `${v.id} · smoke`; }
    onEvent({ type: "detect", id: v.id, t: sim.current.simT });
  };

  useImperativeHandle(api, () => ({
    // The flame keeps burning with chance burnP; otherwise it goes out on its own after a few seconds.
    ignite() {
      const s = sim.current;
      if (s.alive) return;
      s.running = true; s.alive = 1;
      s.outAt = Math.random() < P.current.burnP ? null : s.simT + 2.5 + Math.random() * 2.5;
      onEvent({ type: "ignite", t: s.simT });
    },
    reset() {
      Object.assign(sim.current, { running: false, alive: 0, outAt: null, simT: 0 });
      world.flame.reset(); world.smoke.reset(); world.vents.reset();
      for (const v of world.vents.items) { const el = tags.current[v.id]; if (el) { el.classList.remove("hit"); el.textContent = v.id; } }
      if (clockEl.current) clockEl.current.textContent = "0.0";
    },
  }), [world, onEvent, clockEl]);

  useFrame((_, delta) => {
    const s = sim.current, p = P.current, dt = Math.min(0.05, delta) * TIME_SCALE;
    s.t += dt;
    if (s.running) {
      s.simT += dt;
      if (s.outAt != null && s.simT >= s.outAt) { s.alive = 0; s.outAt = null; onEvent({ type: "out", t: s.simT }); }
    }
    fp.g = p.g; fp.o2 = p.o2; fp.burnP = p.burnP; fp.alive = s.alive;
    world.flame.update(dt, s.t, fp);
    if (s.running) {
      sp.rate = world.flame.alive * (50 + 90 * oxygenK(p.o2));
      sp.g = p.g; sp.flow = AIRFLOW.find(a => a.id === p.flow) || AIRFLOW[0];
      sp.radius = Math.max(0.06, world.flame.size);
      world.smoke.step(dt, sp, world.vents.items, onHit);
    }
    world.vents.update(s.t);
    clampCamera(camera); // OrbitControls updates first (priority -1); keep the camera inside the aisle
    if (clockEl.current) clockEl.current.textContent = s.simT.toFixed(1);
  });

  return (
    <>
      <primitive object={world.module} />
      <primitive object={world.vents.group} />
      <primitive object={world.flame.group} />
      {/* Smoke: one <points>, one draw call */}
      <points geometry={world.smoke.geometry} material={world.smoke.material} frustumCulled={false} />
      {world.vents.items.map(v => (
        <Html key={v.id} position={v.pos} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
          <div ref={el => { tags.current[v.id] = el; }} className="lab3d-tag vent r3f">{v.id}</div>
        </Html>
      ))}
      <Html position={FIRE_POS} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
        <div className="lab3d-tag fire r3f">fire source</div>
      </Html>
    </>
  );
}

export function IssLabScene({ params, api, clockEl, onEvent, onReady }) {
  return (
    <Canvas
      flat
      dpr={[1, 2]}
      camera={{ position: CAMERA_START, fov: CAMERA_FOV, near: 0.05, far: 30 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onCreated={({ scene }) => { scene.background = new THREE.Color(0x05080f); if (onReady) onReady(); }}
      fallback={<div className="lab3d-msg">WebGL is off, so the 3D view can't start.</div>}
    >
      <Lab params={params} api={api} clockEl={clockEl} onEvent={onEvent} />
      <OrbitControls makeDefault enableDamping enablePan={false} minDistance={0.6} maxDistance={4.2} />
    </Canvas>
  );
}
