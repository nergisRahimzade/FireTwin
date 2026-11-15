// FE-12: an interior model encloses the fire; an exterior shell does not.
import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { openDirections } from "./interiorCheck";

const room = (side: THREE.Side) =>
  new THREE.Mesh(new THREE.BoxGeometry(8.5, 4.2, 4.2), new THREE.MeshBasicMaterial({ side }));

describe("openDirections", () => {
  it("is empty for a room whose walls face inward", () => {
    expect(openDirections(room(THREE.BackSide))).toEqual([]);
  });

  it("lists every direction for an exterior shell (walls facing outward)", () => {
    expect(openDirections(room(THREE.FrontSide))).toHaveLength(6);
  });

  it("names the gap when one end of the room is missing", () => {
    const group = new THREE.Group();
    const wall = (pos: [number, number, number], rotY: number, rotX = 0) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(9, 9), new THREE.MeshBasicMaterial());
      m.position.set(...pos);
      m.rotation.set(rotX, rotY, 0);
      group.add(m);
    };
    wall([-4.25, 0, 0], Math.PI / 2); // aft bulkhead facing +x (no fore bulkhead)
    wall([0, 0, 2.1], Math.PI); // port wall facing -z
    wall([0, 0, -2.1], 0); // starboard wall facing +z
    wall([0, 2.1, 0], 0, Math.PI / 2); // overhead facing -y
    wall([0, -2.1, 0], 0, -Math.PI / 2); // deck facing +y
    expect(openDirections(group)).toEqual(["+x (fore)"]);
  });
});
