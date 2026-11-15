"""FE-12: procedurally model the interior of one ISS lab module (Destiny-style), headless.

NASA publishes no interior model of a lab module, so this builds one from code at the backend's
size (8.5 m long, 4.2 m across, ml/pipeline/config.py). The camera, smoke and fire all live in the
aisle, so everything is modelled to be seen from inside:
  - pressure hull and end bulkheads with their normals facing inward (backface culling on)
  - 4 rack faces (overhead, deck, port, starboard) x 6 bays: stowage racks with locker doors,
    handles and bolts; experiment racks with a screen, knobs and drawers; dark utility racks with
    ports and cables. Racks are solids standing in the room, so their normals face the aisle.
  - handrails with standoffs on every bay, foot restraints on the deck
  - ceiling: corner panels with light strips overhead, cable conduits below, vent grilles and a
    smoke detector at every vent in the backend's DETECTORS
  - end sections: closeout panels, a fire extinguisher, a breathing-apparatus box, square hatches
Each material is one mesh (one draw call), and an empty is placed at every vent and at the fire
origin (0, 0, 0). Along the racks the aisle is clear to 1.29 m from the axis (handrails), so the
smoke (kept within 1.33 m) and the camera (kept within 1.2 m) stay out of the geometry; only the
extinguisher and breathing-apparatus box in the end sections reach in further (to about 1.2 m).

Frames: docs/contract.md is metres, +x fore, +y overhead, +z port (three.js, Y-up). Blender is
Z-up, so a contract point (x, y, z) is Blender (x, -z, y), and the glTF exporter turns it back.

Run from frontend/ (or use npm run model:interior, which also compresses it):
    blender --background --factory-startup --python scripts/blender/generate_interior.py -- \\
        --output scripts/blender/out/iss_interior.glb
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimize_iss import contract_to_blender, read_backend_layout  # noqa: E402

AISLE = 1.38  # rack face distance from the axis (src/lab/config.js MODULE.aisle)
RACK_DEPTH = 0.5
FACE_W = 1.84  # rack face width; corners stay inside the 2.1 m hull radius
BAYS = 6
BAY_W = 1.04

# name: (base colour, roughness, metallic, emission colour or None, emission strength, cull backs).
# Everything is a closed solid or the inward-facing shell, so back faces are never seen: cull them
# (glTF doubleSided false), which halves the fragments three.js shades for these surfaces.
MATERIALS = {
    "hull": ((0.42, 0.45, 0.50), 0.9, 0.0, None, 0.0, True),
    "rack_white": ((0.80, 0.79, 0.75), 0.75, 0.0, None, 0.0, True),
    "rack_gray": ((0.66, 0.69, 0.73), 0.75, 0.0, None, 0.0, True),
    "rack_dark": ((0.20, 0.22, 0.26), 0.6, 0.1, None, 0.0, True),
    "locker": ((0.89, 0.88, 0.84), 0.6, 0.0, None, 0.0, True),
    "panel": ((0.55, 0.59, 0.64), 0.85, 0.0, None, 0.0, True),
    "metal": ((0.50, 0.53, 0.58), 0.35, 0.8, None, 0.0, True),
    "handrail": ((0.30, 0.42, 0.62), 0.4, 0.3, None, 0.0, True),
    "black": ((0.03, 0.03, 0.04), 0.7, 0.0, None, 0.0, True),
    "light": ((1.0, 0.97, 0.90), 0.5, 0.0, (1.0, 0.95, 0.86), 2.0, True),
    "screen": ((0.05, 0.12, 0.20), 0.2, 0.0, (0.25, 0.55, 0.85), 1.2, True),
    "red": ((0.70, 0.06, 0.05), 0.45, 0.1, None, 0.0, True),
    "led": ((1.0, 0.1, 0.05), 0.5, 0.0, (1.0, 0.1, 0.05), 3.0, True),
    "hatch": ((0.33, 0.36, 0.40), 0.5, 0.4, None, 0.0, True),
}
SHELL = {"hull"}  # the room itself: normals must face inward


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--output", default="scripts/blender/out/iss_interior.glb")
    return p.parse_args(argv)


def run_in_blender(args: argparse.Namespace) -> None:
    try:
        import bmesh
        import bpy
        from mathutils import Matrix, Vector
    except ImportError:
        raise SystemExit(
            "run this inside Blender (see the command at the top of the file)"
        ) from None

    length, diameter, detectors = read_backend_layout()
    half_l, radius = length / 2, diameter / 2
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # One bmesh per material: building straight into it is the join (one draw call per material).
    meshes = {name: bmesh.new() for name in MATERIALS}

    def box(mat: str, centre, size, rot_x: float = 0.0) -> None:
        m = (
            Matrix.Translation(Vector(centre))
            @ Matrix.Rotation(rot_x, 4, "X")
            @ Matrix.Diagonal((*size, 1.0))
        )
        bmesh.ops.create_cube(meshes[mat], size=1.0, matrix=m)

    def cyl(mat: str, p0, p1, r: float, seg: int = 12) -> None:
        a, b = Vector(p0), Vector(p1)
        d = b - a
        rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
        res = bmesh.ops.create_cone(
            meshes[mat],
            cap_ends=True,
            cap_tris=False,
            segments=seg,
            radius1=r,
            radius2=r,
            depth=d.length,
            matrix=Matrix.Translation((a + b) / 2) @ rot,
        )
        side = {f for v in res["verts"] for f in v.link_faces if len(f.verts) == 4}
        for f in side:
            f.smooth = True

    # Rack faces. n = the face's direction from the axis, t = across the face (both Blender axes).
    faces = {
        "overhead": (Vector((0, 0, 1)), Vector((0, 1, 0))),
        "deck": (Vector((0, 0, -1)), Vector((0, 1, 0))),
        "port": (Vector((0, -1, 0)), Vector((0, 0, 1))),
        "starboard": (Vector((0, 1, 0)), Vector((0, 0, 1))),
    }

    def at(face: str, u: float, v: float, w: float) -> Vector:
        """u along the module, v across the face, w distance from the axis."""
        n, t = faces[face]
        return Vector((u, 0, 0)) + n * w + t * v

    def fbox(mat: str, face: str, u, v, w, su, sv, sw) -> None:
        n, t = faces[face]
        size = (
            Vector((su, 0, 0)) + Vector([abs(c) for c in n]) * sw + Vector([abs(c) for c in t]) * sv
        )
        box(mat, at(face, u, v, w), size)

    def fcyl(mat: str, face: str, a, b, r: float, seg: int = 12) -> None:
        cyl(mat, at(face, *a), at(face, *b), r, seg)

    front = AISLE  # rack front plane
    for fi, face in enumerate(faces):
        for b in range(BAYS):
            u = (b - (BAYS - 1) / 2) * BAY_W
            kind = (
                "experiment"
                if (b in (2, 3) and face in ("port", "starboard")) or (b + fi) % 5 == 4
                else ("dark" if (b + 2 * fi) % 7 == 3 else "stowage")
            )
            body = {"experiment": "rack_gray", "dark": "rack_dark", "stowage": "rack_white"}[kind]
            w_in = BAY_W - 0.04
            fbox(body, face, u, 0, front + RACK_DEPTH / 2, w_in, FACE_W, RACK_DEPTH)
            # Front frame: posts and rails, slightly proud of the rack face.
            for s in (-1, 1):
                fbox("metal", face, u + s * (w_in / 2 - 0.02), 0, front - 0.01, 0.04, FACE_W, 0.02)
                fbox("metal", face, u, s * (FACE_W / 2 - 0.02), front - 0.01, w_in, 0.04, 0.02)
            if kind == "stowage":  # 2 x 3 locker doors with a handle and 4 bolts each
                lw, lh = (w_in - 0.12) / 2, (FACE_W - 0.16) / 3
                for i in range(2):
                    for j in range(3):
                        lu, lv = u + (i - 0.5) * (lw + 0.03), (j - 1) * (lh + 0.03)
                        fbox("locker", face, lu, lv, front - 0.015, lw, lh, 0.025)
                        fbox(
                            "metal", face, lu, lv - lh / 2 + 0.06, front - 0.035, 0.16, 0.025, 0.02
                        )
                        for bu in (-1, 1):
                            for bv in (-1, 1):
                                bp = (lu + bu * (lw / 2 - 0.03), lv + bv * (lh / 2 - 0.03))
                                fcyl(
                                    "metal",
                                    face,
                                    (*bp, front - 0.028),
                                    (*bp, front - 0.034),
                                    0.009,
                                    6,
                                )
            elif kind == "experiment":  # screen, knob row, two drawers, a cable loop
                fbox("black", face, u, 0.38, front - 0.012, 0.62, 0.42, 0.02)
                fbox("screen", face, u, 0.38, front - 0.024, 0.56, 0.36, 0.006)
                for k in range(6):
                    ku = u - 0.3 + k * 0.12
                    fcyl(
                        "black",
                        face,
                        (ku, 0.06, front - 0.01),
                        (ku, 0.06, front - 0.045),
                        0.022,
                        10,
                    )
                for d in range(2):
                    dv = -0.3 - d * 0.32
                    fbox("locker", face, u, dv, front - 0.015, w_in - 0.14, 0.28, 0.025)
                    fbox("metal", face, u, dv, front - 0.04, 0.3, 0.03, 0.025)
                for k in range(3):
                    cu = u + 0.35 + k * 0.035
                    fcyl(
                        "black", face, (cu, -0.78, front - 0.02), (cu, 0.1, front - 0.02), 0.011, 6
                    )
            else:  # dark utility rack: patch panel of ports and a fan grille
                for row in range(4):
                    for col in range(8):
                        fbox(
                            "black",
                            face,
                            u - 0.35 + col * 0.1,
                            0.55 - row * 0.09,
                            front - 0.006,
                            0.05,
                            0.035,
                            0.012,
                        )
                for k in range(9):
                    fbox("metal", face, u, -0.2 - k * 0.06, front - 0.008, 0.6, 0.015, 0.016)
                fbox("led", face, u + 0.4, 0.75, front - 0.01, 0.025, 0.025, 0.01)
            # Handrail along each bay, on two standoffs (clear of the aisle: 1.29 m from the axis).
            side = 0.62 * (1 if fi % 2 else -1)
            fcyl(
                "handrail",
                face,
                (u - 0.42, side, front - 0.09),
                (u + 0.42, side, front - 0.09),
                0.017,
            )
            for e in (-0.3, 0.3):
                fcyl(
                    "handrail",
                    face,
                    (u + e, side, front - 0.02),
                    (u + e, side, front - 0.09),
                    0.013,
                    8,
                )
            if face == "deck":  # foot restraint loops
                for e in (-0.25, 0.25):
                    fbox("black", face, u + e, -side, front - 0.04, 0.05, 0.3, 0.012)
                    for s in (-1, 1):
                        fbox(
                            "black", face, u + e, -side + s * 0.15, front - 0.02, 0.05, 0.012, 0.04
                        )

    # Corner panels between the rack faces; light strips overhead, cable conduits below.
    racks_end = BAYS * BAY_W / 2
    for sy in (1, -1):
        for sz in (1, -1):
            ang = math.atan2(sy, sz)  # rotate the panel to face the axis diagonally
            r = 1.62
            centre = (0, sy * r / math.sqrt(2), sz * r / math.sqrt(2))
            box("panel", centre, (length - 0.3, 0.8, 0.05), rot_x=-ang)
            if sz > 0:
                strip = (0, sy * (r - 0.03) / math.sqrt(2), sz * (r - 0.03) / math.sqrt(2))
                box("light", strip, (length - 1.4, 0.16, 0.02), rot_x=-ang)
            else:
                for k in (-1, 0, 1):
                    off = Vector((0, sz, -sy)).normalized() * (k * 0.06)  # across the panel
                    c = Vector(centre) * ((r - 0.06) / r) + off
                    cyl("black", (-half_l + 0.2, c.y, c.z), (half_l - 0.2, c.y, c.z), 0.02, 8)

    # End sections (between the last bay and the bulkhead): closeout panels on all four faces.
    end_len = half_l - racks_end - 0.03
    for sx in (1, -1):
        cu = sx * (racks_end + end_len / 2 + 0.01)
        for face in faces:
            fbox("panel", face, cu, 0, front + 0.02, end_len, FACE_W, 0.04)
        # A fire extinguisher on brackets (starboard) and a breathing-apparatus box (port), both
        # low on the wall, out of the starting camera's view (port side, above the aisle centre).
        fcyl(
            "red",
            "starboard",
            (cu - 0.25, -0.55, front - 0.11),
            (cu + 0.25, -0.55, front - 0.11),
            0.075,
            16,
        )
        fcyl(
            "black",
            "starboard",
            (cu + 0.25, -0.55, front - 0.11),
            (cu + 0.33, -0.55, front - 0.11),
            0.03,
            10,
        )
        for e in (-0.15, 0.15):
            fbox("metal", "starboard", cu + e, -0.55, front - 0.06, 0.04, 0.2, 0.12)
        fbox("locker", "port", cu, -0.6, front - 0.12, 0.45, 0.35, 0.22)
        fbox("red", "port", cu, -0.6, front - 0.235, 0.47, 0.06, 0.012)

    # Vent grilles and smoke detectors at the backend detector positions (overhead).
    for d in detectors:
        cx, cy, cz = contract_to_blender(*d["position"])
        z = cz + 0.003  # just proud of the rack face (vents sit at 1.37 m, the face at 1.38 m)
        box("black", (cx, cy, z + 0.002), (0.44, 0.44, 0.01))
        for s in (-1, 1):
            box("metal", (cx + s * 0.21, cy, z - 0.008), (0.03, 0.46, 0.02))
            box("metal", (cx, cy + s * 0.21, z - 0.008), (0.46, 0.03, 0.02))
        for k in range(7):
            box("metal", (cx, cy - 0.18 + k * 0.06, z - 0.012), (0.4, 0.012, 0.03))
        dx = cx - 0.32 if cx > 0 else cx + 0.32
        cyl("locker", (dx, cy + 0.32, z), (dx, cy + 0.32, z - 0.04), 0.065, 20)
        box("led", (dx, cy + 0.32, z - 0.043), (0.015, 0.015, 0.008))

    # Pressure hull and end bulkheads (the room shell), with a square hatch at each end.
    hull = meshes["hull"]
    bmesh.ops.create_cone(
        hull,
        cap_ends=False,
        cap_tris=False,
        segments=64,
        radius1=radius,
        radius2=radius,
        depth=length,
        matrix=Matrix.Rotation(math.pi / 2, 4, "Y"),
    )
    for sx in (1, -1):
        bmesh.ops.create_circle(
            hull,
            cap_ends=True,
            cap_tris=False,
            segments=64,
            radius=radius,
            matrix=Matrix.Translation((sx * half_l, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, "Y"),
        )
        hx = sx * (half_l - 0.04)
        for s in (-1, 1):
            box("metal", (hx, s * 0.62, 0), (0.08, 0.1, 1.34))
            box("metal", (hx, 0, s * 0.62), (0.08, 1.34, 0.1))
        box("hatch", (sx * (half_l - 0.03), 0, 0), (0.05, 1.14, 1.14))
        box("black", (sx * (half_l - 0.06), 0, 0.3), (0.01, 0.22, 0.22))  # hatch window
        cyl(
            "metal",
            (sx * (half_l - 0.08), -0.35, -0.1),
            (sx * (half_l - 0.08), -0.35, 0.1),
            0.02,
            8,
        )
    for f in hull.faces:
        if f.calc_area() > 0.5 and len(f.verts) > 4:  # bulkhead discs: flat
            f.smooth = False
        else:
            f.smooth = True

    # Normals: the shell faces inward (the camera is inside); solids face outward, into the aisle.
    inward = hull_faces = 0
    for name, bm in meshes.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        if name in SHELL:
            for f in bm.faces:
                if f.normal.dot(f.calc_center_median()) > 0:
                    f.normal_flip()
            inward = sum(1 for f in bm.faces if f.normal.dot(f.calc_center_median()) < 0)
            hull_faces = len(bm.faces)
        else:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # Materials and objects: one object per material.
    tris = 0
    for name, bm in meshes.items():
        if not bm.faces:
            continue
        col, rough, metal, emit, strength, cull = MATERIALS[name]
        mat = bpy.data.materials.new(name)
        mat.use_backface_culling = cull
        if bpy.app.version < (5, 0, 0):  # node trees are always on from Blender 5
            mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*col, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        if emit:
            bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
            bsdf.inputs["Emission Strength"].default_value = strength
        mat.diffuse_color = (*col, 1.0)
        me = bpy.data.meshes.new(f"mesh_{name}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        obj = bpy.data.objects.new(f"mesh_{name}", me)
        bpy.context.scene.collection.objects.link(obj)
        tris += sum(len(p.vertices) - 2 for p in me.polygons)

    # Empties at the vents and the fire (optimize_iss.py re-creates them from the same config).
    for name, pos in [
        *((d["id"], d["position"]) for d in detectors),
        ("fire_origin", (0.0, 0.0, 0.0)),
    ]:
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.15
        empty.location = contract_to_blender(*pos)
        bpy.context.scene.collection.objects.link(empty)

    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
        export_draco_mesh_compression_enable=False,
    )
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    print(
        f"[generate_interior] {len(objs)} meshes (one per material), {tris:,} triangles, "
        f"shell faces facing inward: {inward}/{hull_faces}; "
        f"vents {[d['id'] for d in detectors]}; wrote {out} ({out.stat().st_size / 1e6:.2f} MB)"
    )


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    run_in_blender(parse_args(argv))


if __name__ == "__main__":
    main()
