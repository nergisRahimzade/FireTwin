/* FE-04: the ISS module scene.
   <Suspense> shows the coded FallbackModule while the glTF loads; an error boundary keeps showing it
   if the file is missing or broken, so the scene is never empty. OrbitControls (camera kept inside
   the aisle), soft lighting, and a marker at every detector position /detect returns. */
import { Html, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Component, type ReactNode, Suspense, useMemo } from "react";
import * as THREE from "three";
import type { DetectOut, SimulateOut } from "../api/types";
import { CAMERA_FOV, CAMERA_START, clampCamera } from "../lab/core.js";
import { FallbackModule } from "./FallbackModule";
import { Flame } from "./Flame";
import { Smoke } from "./Smoke";
import { IssLab } from "./IssLab";
import { detectorMarks } from "./detectors";

// Falls back to the coded module when the glTF can't load (Suspense only covers "still loading").
class ModelBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(err: unknown) {
    console.info("ISS glTF unavailable, showing the coded module:", err instanceof Error ? err.message : err);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function KeepCameraInside() {
  useFrame(({ camera }) => clampCamera(camera));
  return null;
}

function DetectorMarkers({ detect }: { detect: DetectOut | null }) {
  const marks = useMemo(() => detectorMarks(detect), [detect]);
  return (
    <>
      {marks.map((m, index) => (
        // index + id: two detectors could share an id
        <group key={`${index}-${m.id}`} position={m.position} name={m.id}>
          <mesh>
            <sphereGeometry args={[0.05, 16, 12]} />
            <meshBasicMaterial color={0x63e6be} />
          </mesh>
          <mesh>
            <sphereGeometry args={[0.16, 24, 16]} />
            <meshBasicMaterial color={0x63e6be} transparent opacity={0.2} depthWrite={false} blending={THREE.AdditiveBlending} />
          </mesh>
          <Html center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
            <div className="lab3d-tag r3f vent">
              {m.id}{m.synthetic ? " · synthetic" : ""}
            </div>
          </Html>
        </group>
      ))}
    </>
  );
}

export function IssScene({ detect, simulate }: { detect: DetectOut | null; simulate: SimulateOut | null }) {
  return (
    <Canvas
      flat
      dpr={[1, 2]}
      camera={{ position: CAMERA_START as [number, number, number], fov: CAMERA_FOV, near: 0.05, far: 30 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onCreated={({ scene }) => { scene.background = new THREE.Color(0x05080f); }}
      fallback={<div className="lab3d-msg">WebGL is off, so the 3D view can't start.</div>}
    >
      <ambientLight intensity={0.45} />
      <hemisphereLight args={[0xe4ecff, 0x3a404c, 0.5]} />
      <ModelBoundary fallback={<FallbackModule />}>
        <Suspense fallback={<FallbackModule />}>
          <IssLab />
        </Suspense>
      </ModelBoundary>
      <DetectorMarkers detect={detect} />
      <Smoke simulate={simulate} />
      <Flame simulate={simulate} />
      <OrbitControls makeDefault enableDamping enablePan={false} minDistance={0.6} maxDistance={4.2} />
      <KeepCameraInside />
    </Canvas>
  );
}
