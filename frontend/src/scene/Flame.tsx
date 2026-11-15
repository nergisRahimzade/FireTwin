/* FE-05: the microgravity flame at the module centre (docs/contract.md: the fire is always at
   (0, 0, 0)). The look comes from lab/core.js Flame: blue, roughly spherical fresnel shells, which
   become a teardrop stretched along flow_dir as the airflow rises.
   - size from burn_probability (with O2) and spread_rate_mm_s
   - state "extinguished": shrinks and fades over ~2 s
   - extrapolated: grey stripes + an "outside tested range" tag
   Performance: every animated object is held in a ref and mutated in useFrame. No React state is
   set per frame; the component only re-renders when a new SimulateOut arrives. */
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { SimulateOut } from "../api/types";
import { FIRE_POS } from "../lab/config.js";
import { Flame as CoreFlame } from "../lab/core.js";
import { flameTarget, stepLife } from "./flameLogic";

const UP = new THREE.Vector3(0, 1, 0);
const STRIPES_VERT = "varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }";
const STRIPES_FRAG = "uniform float uOpacity; varying vec3 vP; void main(){ if (fract((vP.x + vP.y) * 4.0) < 0.5) discard; gl_FragColor = vec4(vec3(0.62), uOpacity);\n#include <colorspace_fragment>\n}";

export function Flame({ simulate }: { simulate: SimulateOut | null }) {
  const target = useMemo(() => flameTarget(simulate), [simulate]);
  const flame = useRef<CoreFlame>(null as unknown as CoreFlame);
  if (!flame.current) {
    flame.current = new CoreFlame();
    flame.current.group.traverse((o: THREE.Object3D) => { o.renderOrder = 10; }); // additive glow on top
  }
  const stripes = useRef<THREE.Mesh>(null);
  const stripesMat = useRef<THREE.ShaderMaterial>(null);
  const clock = useRef(0);
  const life = useRef(0); // 0 = no flame ... 1 = fully burning; changes linearly
  const dir = useRef(new THREE.Vector3(1, 0, 0));

  useEffect(() => {
    const f = flame.current;
    return () => {
      f.group.traverse((o: THREE.Object3D) => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose();
        for (const m of mesh.material ? ([] as THREE.Material[]).concat(mesh.material) : []) m.dispose();
      });
    };
  }, []);

  useFrame((_, delta) => {
    const f = flame.current;
    const dt = Math.min(0.05, delta);
    clock.current += dt;
    // Linear life: ignition reaches full size in ~0.4 s; going out shrinks and fades over ~2 s.
    life.current = stepLife(life.current, target.alive, dt);
    f.update(dt, clock.current * 2.5, { g: target.stretch, o2: target.o2, burnP: target.burnP, alive: life.current });
    f.fuel.visible = simulate !== null; // the fuel droplet appears once a scenario exists
    dir.current.set(target.flowDir[0], target.flowDir[1], target.flowDir[2]);
    f.tear.quaternion.setFromUnitVectors(UP, dir.current);
    f.group.scale.setScalar(target.spreadScale);
    if (stripes.current && stripesMat.current) {
      stripes.current.visible = target.extrapolated && f.size > 0.01;
      stripes.current.scale.setScalar(Math.max(1e-4, f.size * 1.35));
      stripesMat.current.uniforms.uOpacity.value = 0.55 * Math.min(1, f.alive * 1.5);
    }
  });

  return (
    <group position={FIRE_POS as [number, number, number]} name="fire">
      <primitive object={flame.current.group} position={[0, 0, 0]}>
        <mesh ref={stripes} visible={false} renderOrder={11}>
          <sphereGeometry args={[1, 32, 16]} />
          <shaderMaterial
            ref={stripesMat}
            uniforms={{ uOpacity: { value: 0.55 } }}
            vertexShader={STRIPES_VERT}
            fragmentShader={STRIPES_FRAG}
            transparent
            depthWrite={false}
            side={THREE.DoubleSide}
          />
        </mesh>
      </primitive>
      {target.extrapolated && target.alive === 1 && (
        <Html position={[0, 0.45, 0]} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
          <div className="lab3d-tag r3f extrapolated">outside tested range</div>
        </Html>
      )}
    </group>
  );
}
