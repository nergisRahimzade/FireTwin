/* Flame in Freefall: 3D ISS lab core.
   Builds the module, the vents, the flame and the smoke from ./config.js. The FireTwin scene uses
   buildModule (src/scene/FallbackModule.tsx), clampCamera and the camera settings.
   Everything is built in code: no .glb, no Draco decoder, no textures to download. */
import * as THREE from "three";
import { AIRFLOW, DETECT_RADIUS, FIRE_POS, MODULE, TIME_SCALE, VENTS } from "./config.js";

export { AIRFLOW, DETECT_RADIUS, FIRE_POS, MODULE, TIME_SCALE, VENTS };

const FLOW_SPEED = 0.32; // m/s, cabin air along the chosen direction
const SINK_RANGE = 0.55; // m, how far a return vent's suction reaches
const BOUND = { x: 4.1, yz: 1.33 }; // smoke stays inside the aisle

const v3 = a => new THREE.Vector3().fromArray(a);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const oxygenK = o2 => clamp((o2 - 12) / (55 - 12), 0, 1);

/* ---------------- module interior ---------------- */
export function buildModule() {
  const group = new THREE.Group();
  group.name = "iss_module";
  const R = MODULE.diameter / 2, L = MODULE.length, A = MODULE.aisle;
  const box = new THREE.BoxGeometry(1, 1, 1);

  // Pressure hull, seen only in the corners between rack faces
  group.add(new THREE.Mesh(new THREE.CylinderGeometry(R, R, L, 48, 1, true).rotateZ(Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: 0x7d8693, roughness: 0.9, side: THREE.BackSide })));

  // Racks: 4 faces (overhead, deck, port, starboard) x 6 bays, one draw call
  const faces = [[0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
  const bays = 6, bayW = 1.04, depth = 0.55, faceW = 1.9;
  const rackColors = [0xe8e6df, 0xdfe3e8, 0xd2d7de, 0x5b636f];
  const racks = new THREE.InstancedMesh(box, new THREE.MeshStandardMaterial({ roughness: 0.78, metalness: 0.04 }), faces.length * bays);
  const lockers = new THREE.InstancedMesh(box, new THREE.MeshStandardMaterial({ roughness: 0.6, metalness: 0.05 }), faces.length * bays * 6);
  const rails = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.016, 0.016, 1, 10), new THREE.MeshStandardMaterial({ color: 0x7d97bd, roughness: 0.4, metalness: 0.3 }), faces.length * bays * 3);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color();
  const toX = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2);
  let ri = 0, li = 0, hi = 0;
  faces.forEach((n, f) => {
    const alongY = n[1] !== 0; // overhead/deck racks: the face spans z; wall racks: the face spans y
    for (let b = 0; b < bays; b++) {
      const x = (b - (bays - 1) / 2) * bayW;
      p.set(x, n[1] * (A + depth / 2), n[2] * (A + depth / 2));
      s.set(bayW - 0.04, alongY ? depth : faceW, alongY ? faceW : depth);
      racks.setMatrixAt(ri, m.compose(p, q.identity(), s));
      racks.setColorAt(ri++, c.setHex(rackColors[(b * 3 + f) % 7 === 3 ? 3 : (b + f) % 3]));
      // 2 x 3 stowage lockers on each rack front
      for (let i = 0; i < 2; i++) for (let j = 0; j < 3; j++) {
        const lx = x + (i - 0.5) * (bayW - 0.1) / 2, lo = (j - 1) * (faceW - 0.2) / 3;
        p.set(lx, alongY ? n[1] * (A - 0.012) : lo, alongY ? lo : n[2] * (A - 0.012));
        const w = (bayW - 0.1) / 2 - 0.04, hgt = (faceW - 0.2) / 3 - 0.05;
        s.set(w, alongY ? 0.024 : hgt, alongY ? hgt : 0.024);
        lockers.setMatrixAt(li, m.compose(p, q.identity(), s));
        lockers.setColorAt(li++, c.setHex((b + i + j + f) % 5 === 0 ? 0xb8c1cd : 0xf2f0ea));
      }
      // Handrail: bar along x near one edge, plus two standoffs (drawn as short bars)
      const off = 0.72 * (f % 2 ? -1 : 1);
      p.set(x, alongY ? n[1] * (A - 0.09) : off, alongY ? off : n[2] * (A - 0.09));
      rails.setMatrixAt(hi++, m.compose(p, toX, s.set(1, 0.6, 1)));
      for (const e of [-0.28, 0.28]) {
        p.set(x + e, alongY ? n[1] * (A - 0.045) : off, alongY ? off : n[2] * (A - 0.045));
        const qq = alongY ? q.identity() : new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
        rails.setMatrixAt(hi++, m.compose(p, qq, s.set(1, 0.09, 1)));
      }
    }
  });
  group.add(racks, lockers, rails);

  // Corner panels (chamfers between rack faces). Overhead corners carry the light strips.
  const panelMat = new THREE.MeshStandardMaterial({ color: 0x9aa3af, roughness: 0.85 });
  const stripMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff2dc, emissiveIntensity: 1.6 });
  for (const [sy, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
    const ang = Math.atan2(sz, sy);
    const panel = new THREE.Mesh(box, panelMat);
    panel.scale.set(L - 0.5, 0.06, 0.76);
    panel.position.set(0, sy * 1.17, sz * 1.17);
    panel.rotation.x = ang;
    group.add(panel);
    if (sy > 0) {
      const strip = new THREE.Mesh(box, stripMat);
      strip.scale.set(L - 1.2, 0.02, 0.16);
      strip.position.set(0, sy * 1.135, sz * 1.135);
      strip.rotation.x = ang;
      group.add(strip);
    }
  }

  // End cones with a square hatch at each end
  const endMat = new THREE.MeshStandardMaterial({ color: 0xa5adb8, roughness: 0.85, side: THREE.DoubleSide });
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x6e7783, roughness: 0.6, metalness: 0.3 });
  const holeMat = new THREE.MeshBasicMaterial({ color: 0x070a12 });
  for (const sx of [1, -1]) {
    const end = new THREE.Mesh(new THREE.CircleGeometry(R, 48), endMat);
    end.position.x = sx * (L / 2 - 0.01);
    end.rotation.y = -sx * Math.PI / 2;
    const hole = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.1), holeMat);
    hole.position.x = sx * (L / 2 - 0.02);
    hole.rotation.y = -sx * Math.PI / 2;
    group.add(end, hole);
    for (const [y, z, h, w] of [[0.62, 0, 0.12, 1.36], [-0.62, 0, 0.12, 1.36], [0, 0.62, 1.36, 0.12], [0, -0.62, 1.36, 0.12]]) {
      const bar = new THREE.Mesh(box, frameMat);
      bar.scale.set(0.08, h, w);
      bar.position.set(sx * (L / 2 - 0.05), y, z);
      group.add(bar);
    }
  }

  // Cabin lighting
  group.add(new THREE.HemisphereLight(0xe4ecff, 0x3a404c, 1.0));
  for (const x of [-2.8, 0, 2.8]) {
    const l = new THREE.PointLight(0xfff1e0, 2.6, 7, 1.6);
    l.position.set(x, 1.0, 0);
    group.add(l);
  }
  return group;
}

/* ---------------- air-return vents (the detectors) ---------------- */
const IDLE = 0x63e6be, HIT = 0xff5a4a;
function grilleTexture() {
  if (typeof document === "undefined") return null; // headless tests
  const cv = document.createElement("canvas");
  cv.width = cv.height = 64;
  const x = cv.getContext("2d");
  x.fillStyle = "#2a313c"; x.fillRect(0, 0, 64, 64);
  x.fillStyle = "#0b0f16";
  for (let i = 0; i < 6; i++) x.fillRect(6, 6 + i * 9.5, 52, 5);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
export function buildVents() {
  const group = new THREE.Group();
  group.name = "vents";
  const grille = new THREE.MeshStandardMaterial({ map: grilleTexture(), color: 0xffffff, roughness: 0.7, metalness: 0.2 });
  const items = VENTS.map(v => {
    const g = new THREE.Group();
    g.name = v.id; // named like the detector IDs, as the guide asks for Blender empties
    g.position.fromArray(v.pos);
    g.lookAt(v3(v.pos).add(v3(v.normal)));
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.28, 0.03), grille);
    const lampMat = new THREE.MeshBasicMaterial({ color: IDLE });
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.025, 12, 8), lampMat);
    lamp.position.set(0.24, 0.12, 0.02);
    const haloMat = new THREE.MeshBasicMaterial({ color: IDLE, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    const halo = new THREE.Mesh(new THREE.RingGeometry(0.3, 0.34, 40), haloMat);
    halo.position.z = 0.02;
    g.add(body, lamp, halo);
    group.add(g);
    return { ...v, position: g.position, lampMat, haloMat, halo, triggered: false };
  });
  const setState = (it, hit) => { it.triggered = hit; it.lampMat.color.setHex(hit ? HIT : IDLE); it.haloMat.color.setHex(hit ? HIT : IDLE); };
  return {
    group, items,
    trigger: it => setState(it, true),
    reset: () => items.forEach(it => setState(it, false)),
    update: t => items.forEach((it, i) => {
      const k = it.triggered ? 0.5 + 0.5 * Math.sin(t * 8) : 0.5 + 0.5 * Math.sin(t * 2 + i);
      it.haloMat.opacity = it.triggered ? 0.4 + 0.5 * k : 0.15 + 0.15 * k;
      it.halo.scale.setScalar(it.triggered ? 1 + 0.25 * k : 1);
    }),
  };
}

/* ---------------- flame ---------------- */
// Fresnel shell: bright at the silhouette, see-through in the middle, like a real diffusion flame.
function shell(color, power, opacity) {
  return new THREE.ShaderMaterial({
    uniforms: { uColor: { value: new THREE.Color(color) }, uPower: { value: power }, uOpacity: { value: opacity } },
    vertexShader: "varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }",
    fragmentShader: "uniform vec3 uColor; uniform float uPower; uniform float uOpacity; varying vec3 vN; varying vec3 vV; void main(){ float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), uPower); gl_FragColor = vec4(uColor * (0.4 + f), clamp(f * uOpacity, 0.0, 1.0));\n#include <colorspace_fragment>\n}",
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  });
}
function teardrop() {
  const pts = [];
  for (let i = 0; i <= 28; i++) { const t = i / 28; pts.push(new THREE.Vector2(0.3 * Math.sin(Math.PI * Math.pow(t, 0.6)) * (1 - 0.45 * t), -0.22 + 1.25 * t)); }
  return new THREE.LatheGeometry(pts, 40);
}
export class Flame {
  constructor() {
    this.group = new THREE.Group();
    this.group.name = "flame";
    this.group.position.fromArray(FIRE_POS);
    const sph = new THREE.SphereGeometry(1, 40, 24), drop = teardrop();
    this.mats = { blue: shell(0x5cc2ff, 2.2, 1.6), halo: shell(0x3a6dff, 0.9, 0.22), soot: shell(0xff9a4a, 2.6, 0.9), outer: shell(0xff7a2a, 1.4, 1.1), mid: shell(0xffc46b, 1.8, 1.0), core: shell(0xfff0c0, 1.2, 0.9) };
    this.ball = new THREE.Group();
    this.blue = new THREE.Mesh(sph, this.mats.blue);
    this.halo = new THREE.Mesh(sph, this.mats.halo); this.halo.scale.setScalar(1.6);
    this.soot = new THREE.Mesh(sph, this.mats.soot); this.soot.scale.setScalar(0.55);
    this.ball.add(this.halo, this.blue, this.soot);
    this.tear = new THREE.Group();
    const layer = (mat, sc) => { const me = new THREE.Mesh(drop, mat); me.scale.setScalar(sc); this.tear.add(me); return me; };
    layer(this.mats.outer, 1.15); layer(this.mats.mid, 0.9); layer(this.mats.core, 0.55);
    this.fuel = new THREE.Mesh(new THREE.SphereGeometry(0.028, 16, 12), new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x99a4b8, emissiveIntensity: 0.6, roughness: 0.3 }));
    this.light = new THREE.PointLight(0x6aa8ff, 0, 5, 1.6);
    this.group.add(this.ball, this.tear, this.fuel, this.light);
    this.g = 0; this.alive = 0; this.k = oxygenK(21); this.size = 0;
    this.blueC = new THREE.Color(0x6aa8ff); this.ambC = new THREE.Color(0xffa050);
  }
  // p: { g: 0 or 1, o2, burnP, alive: 0 or 1 }. dt in simulated seconds.
  update(dt, t, p) {
    const e = 1 - Math.exp(-dt * 3);
    this.g += (p.g - this.g) * e; this.k += (oxygenK(p.o2) - this.k) * e; this.alive += (p.alive - this.alive) * (1 - Math.exp(-dt * (p.alive ? 4 : 1.5)));
    const size = this.alive * (0.14 + 0.26 * this.k) * (0.7 + 0.3 * p.burnP);
    this.size = size;
    const G = this.g, wob = 1 + 0.03 * Math.sin(t * 1.3);
    this.ball.scale.setScalar(Math.max(1e-4, size * (1 - 0.62 * G) * wob));
    this.ball.position.y = -G * size * 0.1;
    this.mats.soot.uniforms.uOpacity.value = (0.25 + 0.9 * this.k) * (1 - G);
    const fl = 1 + 0.07 * Math.sin(t * 13) + 0.04 * Math.sin(t * 7.3);
    this.tear.scale.set(Math.max(1e-4, size * G * 1.05), Math.max(1e-4, size * G * 1.15 * fl), Math.max(1e-4, size * G * 1.05));
    this.tear.rotation.z = 0.04 * Math.sin(t * 9) * G;
    this.mats.outer.uniforms.uOpacity.value = 1.1 * G; this.mats.mid.uniforms.uOpacity.value = 1.0 * G; this.mats.core.uniforms.uOpacity.value = 0.9 * G;
    this.light.color.copy(this.blueC).lerp(this.ambC, G);
    this.light.intensity = this.alive * (1.5 + 18 * size) * (1 + 0.08 * Math.sin(t * 17));
  }
  reset() { this.alive = 0; this.size = 0; }
}

/* ---------------- smoke: one Points object, one draw call ---------------- */
export class Smoke {
  constructor(n = 1600) {
    this.n = n;
    this.pos = new Float32Array(n * 3); this.vel = new Float32Array(n * 3);
    this.age = new Float32Array(n).fill(-1); this.life = new Float32Array(n);
    this.alpha = new Float32Array(n); this.size = new Float32Array(n);
    this.geometry = new THREE.BufferGeometry();
    this.geometry.setAttribute("position", new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setAttribute("aAlpha", new THREE.BufferAttribute(this.alpha, 1).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setAttribute("aSize", new THREE.BufferAttribute(this.size, 1).setUsage(THREE.DynamicDrawUsage));
    this.material = new THREE.ShaderMaterial({
      uniforms: { uScale: { value: 400 }, uColor: { value: new THREE.Color(0x4a505b) } },
      vertexShader: "attribute float aAlpha; attribute float aSize; varying float vA; uniform float uScale; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vA = aAlpha; gl_PointSize = aSize * uScale / max(0.05, -mv.z); gl_Position = projectionMatrix * mv; }",
      fragmentShader: "uniform vec3 uColor; varying float vA; void main(){ float d = length(gl_PointCoord - 0.5); float a = smoothstep(0.5, 0.0, d) * vA; if (a < 0.003) discard; gl_FragColor = vec4(uColor, a);\n#include <colorspace_fragment>\n}",
      transparent: true, depthWrite: false,
    });
    this.points = new THREE.Points(this.geometry, this.material);
    this.points.name = "smoke";
    this.points.frustumCulled = false;
    this.acc = 0; this.cursor = 0;
  }
  // Point size in world meters needs the canvas height in device pixels and the camera fov.
  setScale(heightPx, fovDeg) { this.material.uniforms.uScale.value = heightPx / (2 * Math.tan((fovDeg * Math.PI) / 360)); }
  reset() { this.age.fill(-1); this.alpha.fill(0); this.acc = 0; this.flag(); }
  flag() { for (const k of ["position", "aAlpha", "aSize"]) this.geometry.attributes[k].needsUpdate = true; }
  spawn(src, r, g, life) {
    const i = this.cursor; this.cursor = (this.cursor + 1) % this.n;
    let x, y, z, d;
    do { x = Math.random() * 2 - 1; y = Math.random() * 2 - 1; z = Math.random() * 2 - 1; d = x * x + y * y + z * z; } while (d > 1 || d < 0.01);
    d = Math.sqrt(d); x /= d; y /= d; z /= d;
    const j = i * 3;
    this.pos[j] = src.x + x * r; this.pos[j + 1] = src.y + y * r + g * r * 1.6; this.pos[j + 2] = src.z + z * r;
    this.vel[j] = x * 0.25; this.vel[j + 1] = y * 0.25 + g * 0.35; this.vel[j + 2] = z * 0.25;
    this.age[i] = 0; this.life[i] = life ? life * (0.8 + Math.random() * 0.4) : 9 + Math.random() * 5;
  }
  // p: { rate (particles per simulated second), g, flow: AIRFLOW item, src: Vector3, radius }
  // Optional: speed (m/s along flow.dir, default the demo cabin flow), life (simulated s per particle).
  // vents: buildVents().items. onHit(vent) fires when a particle reaches a vent.
  // Simple cabin airflow: the fans push air along the chosen direction and it bends toward the
  // return vent furthest downstream. Every vent also pulls in what comes within ~0.5 m.
  // With the fans off nothing moves the smoke in 0 g except slow spreading.
  step(dt, p, vents, onHit) {
    this.acc += p.rate * dt;
    while (this.acc >= 1) { this.spawn(p.src, p.radius, p.g, p.life); this.acc -= 1; }
    const [fx, fy, fz] = p.flow.dir, fans = p.flow.fans ? 1 : 0, relax = Math.min(1, dt * 1.5), jit = 0.35 * Math.sqrt(dt);
    let target = null, best = -Infinity;
    if (fans) for (const v of vents) { const s = v.position.x * fx + v.position.y * fy + v.position.z * fz; if (s > best) { best = s; target = v; } }
    for (let i = 0; i < this.n; i++) {
      if (this.age[i] < 0) continue;
      const a = (this.age[i] += dt), j = i * 3;
      if (a > this.life[i]) { this.age[i] = -1; this.alpha[i] = 0; continue; }
      let px = this.pos[j], py = this.pos[j + 1], pz = this.pos[j + 2];
      const base = p.speed ?? FLOW_SPEED * 0.6; // m/s along flow.dir (FE-06 passes the scenario's speed)
      let ax = fx * base, ay = fy * base + p.g * 0.38 * Math.exp(-a / 6), az = fz * base;
      if (target) {
        const tx = target.position.x - px, ty = target.position.y - py, tz = target.position.z - pz, td = Math.max(Math.sqrt(tx * tx + ty * ty + tz * tz), 1e-3);
        ax += (tx / td) * FLOW_SPEED * 0.55; ay += (ty / td) * FLOW_SPEED * 0.55; az += (tz / td) * FLOW_SPEED * 0.55;
      }
      let absorbed = false;
      for (const v of vents) {
        const dx = v.position.x - px, dy = v.position.y - py, dz = v.position.z - pz, d = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (d < DETECT_RADIUS && fans) { absorbed = true; onHit(v); break; }
        const pull = fans * 0.8 * Math.exp(-d / SINK_RANGE) / Math.max(d, 1e-3);
        ax += dx * pull; ay += dy * pull; az += dz * pull;
      }
      if (absorbed) { this.age[i] = -1; this.alpha[i] = 0; continue; }
      const vx = (this.vel[j] += (ax - this.vel[j]) * relax + (Math.random() - 0.5) * jit);
      const vy = (this.vel[j + 1] += (ay - this.vel[j + 1]) * relax + (Math.random() - 0.5) * jit);
      const vz = (this.vel[j + 2] += (az - this.vel[j + 2]) * relax + (Math.random() - 0.5) * jit);
      px += vx * dt; py += vy * dt; pz += vz * dt;
      // Walls: smoke slides along the racks instead of passing through
      if (Math.abs(px) > BOUND.x) { px = Math.sign(px) * BOUND.x; this.vel[j] = 0; }
      if (Math.abs(py) > BOUND.yz) { py = Math.sign(py) * BOUND.yz; this.vel[j + 1] = 0; }
      if (Math.abs(pz) > BOUND.yz) { pz = Math.sign(pz) * BOUND.yz; this.vel[j + 2] = 0; }
      this.pos[j] = px; this.pos[j + 1] = py; this.pos[j + 2] = pz;
      this.size[i] = 0.07 + 0.5 * Math.min(1, a / 6);
      this.alpha[i] = Math.min(1, a * 3) * (1 - a / this.life[i]) * 0.62;
    }
    this.flag();
  }
}

/* ---------------- camera ---------------- */
// Keep the orbiting camera inside the cabin aisle.
export function clampCamera(camera) {
  const c = camera.position;
  c.x = clamp(c.x, -4.0, 4.0); c.y = clamp(c.y, -1.2, 1.2); c.z = clamp(c.z, -1.2, 1.2);
}
export const CAMERA_START = [-3.3, 0.45, 0.95];
export const CAMERA_FOV = 62;
