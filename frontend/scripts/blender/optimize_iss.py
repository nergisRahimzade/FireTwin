"""FE-12 (stretch): prepare an ISS lab module model for the web, headless in Blender.

Automates the FireTwin Blender -> R3F guide (sections 4 and 5):
  1. import the source model (.glb/.gltf, .obj or .fbx)
  2. drop cameras, lights and helper empties; bake every transform
  3. turn the long axis to +x, centre the model on the origin, and scale it to the module size in
     the backend config: 8.5 m long, 4.2 m across (ml/pipeline/config.py)
  4. decimate dense meshes until the whole model fits a triangle budget (default 100k)
  5. join meshes that share a material, so each material is one draw call
  6. add a named empty at every vent detector in the backend's DETECTORS (plus fire_origin at
     (0, 0, 0)), so the 3D vents sit exactly where the alarm comes from
  7. export a GLB (Y-up, no animations, no Draco: build_iss_model.sh compresses it next)

Run it with Blender (4.2 or newer), from the frontend folder:
    blender --background --python scripts/blender/optimize_iss.py -- \\
        --input ~/Downloads/iss_interior.glb --output public/models/iss_lab.glb

Without Blender, check the layout it will use (read from the backend config) and its helpers:
    python3 scripts/blender/optimize_iss.py --self-test

Coordinates follow docs/contract.md: metres, origin at the module centre, +x fore, +y overhead,
+z port (three.js, Y-up). Blender is Z-up, so a contract point (x, y, z) is placed at Blender
(x, -z, y); the glTF exporter's Y-up conversion turns it back into (x, y, z).
"""

from __future__ import annotations

import argparse
import ast
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND_CONFIG = REPO / "ml" / "pipeline" / "config.py"
MIN_FACES_TO_DECIMATE = 200  # small parts (handrails, knobs) keep their shape


# ---------- pure helpers (no Blender needed; covered by --self-test) ----------


def read_backend_layout(path: Path = BACKEND_CONFIG) -> tuple[float, float, list[dict]]:
    """MODULE_LENGTH_M, MODULE_DIAMETER_M and DETECTORS from the backend config, without importing
    it (Blender's Python doesn't have the backend's packages)."""
    values: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
            if name in {"MODULE_LENGTH_M", "MODULE_DIAMETER_M", "DETECTORS"}:
                values[name] = ast.literal_eval(node.value)
    missing = {"MODULE_LENGTH_M", "MODULE_DIAMETER_M", "DETECTORS"} - values.keys()
    if missing:
        raise ValueError(f"{path} is missing {sorted(missing)}")
    detectors = [
        {"id": str(d["id"]), "position": tuple(float(v) for v in d["position"])}
        for d in values["DETECTORS"]
    ]
    return float(values["MODULE_LENGTH_M"]), float(values["MODULE_DIAMETER_M"]), detectors


def contract_to_blender(x: float, y: float, z: float) -> tuple[float, float, float]:
    """A docs/contract.md point (three.js, Y-up) in Blender's Z-up frame."""
    return (x, 0.0 - z, y)  # 0.0 - z, not -z: no "-0.0" in the output


def long_axis(dims: tuple[float, float, float]) -> int:
    """Index (0 = x, 1 = y, 2 = z) of the model's longest side."""
    return max(range(3), key=lambda i: dims[i])


def scale_factors(
    dims: tuple[float, float, float], length: float, diameter: float, uniform: bool = False
) -> tuple[float, float, float]:
    """Per-axis scale that makes a model (long axis already on x) exactly length x diameter.
    uniform=True keeps the proportions and only matches the length."""
    along = length / dims[0]
    if uniform:
        return (along, along, along)
    across = diameter / max(dims[1], dims[2])
    return (along, across, across)


def decimate_ratio(total_tris: int, max_tris: int, ratio: float | None = None) -> float:
    """The ratio to collapse dense meshes to: the given one, or just enough to fit max_tris."""
    if ratio is not None:
        return min(1.0, max(0.01, ratio))
    if total_tris <= max_tris:
        return 1.0
    return max(0.01, max_tris / total_tris)


def self_test() -> None:
    length, diameter, detectors = read_backend_layout()
    assert (length, diameter) == (8.5, 4.2), (length, diameter)
    ids = [d["id"] for d in detectors]
    assert ids and len(ids) == len(set(ids)), ids
    for d in detectors:  # every vent sits on the rack faces inside the module (contract table)
        x, y, z = d["position"]
        assert abs(x) <= length / 2 and abs(y) <= 1.38 and abs(z) <= 1.38, d
    assert contract_to_blender(4.0, 1.37, -0.5) == (4.0, 0.5, 1.37)
    assert long_axis((2.0, 9.0, 3.0)) == 1

    def close(a: tuple, b: tuple) -> bool:
        return all(math.isclose(x, y) for x, y in zip(a, b, strict=True))

    assert close(scale_factors((17.0, 8.4, 8.0), 8.5, 4.2), (0.5, 0.5, 0.5))
    assert close(scale_factors((17.0, 4.2, 6.0), 8.5, 4.2), (0.5, 0.7, 0.7))
    assert close(scale_factors((17.0, 4.2, 6.0), 8.5, 4.2, uniform=True), (0.5, 0.5, 0.5))
    assert decimate_ratio(50_000, 100_000) == 1.0
    assert math.isclose(decimate_ratio(400_000, 100_000), 0.25)
    assert decimate_ratio(400_000, 100_000, ratio=0.3) == 0.3
    print(f"self-test passed. Module {length} m x {diameter} m; vents (contract frame, metres):")
    for d in detectors:
        print(f"  {d['id']:<10} {d['position']}  ->  Blender {contract_to_blender(*d['position'])}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the ISS lab model for the web (FE-12).")
    parser.add_argument("--input", type=Path, help="source model: .glb, .gltf, .obj or .fbx")
    parser.add_argument("--output", type=Path, default=Path("public/models/iss_lab.glb"))
    parser.add_argument(
        "--max-tris", type=int, default=100_000, help="triangle budget (guide: under ~100k)"
    )
    parser.add_argument("--ratio", type=float, help="fixed decimate ratio instead of the budget")
    parser.add_argument(
        "--uniform", action="store_true", help="keep proportions; match the length only"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="check the helpers and layout, no Blender"
    )
    return parser.parse_args(argv)


# ---------- the Blender pipeline ----------


def run_in_blender(args: argparse.Namespace) -> None:
    try:
        import bpy  # only exists inside Blender
        from mathutils import Matrix, Vector
    except ImportError:
        raise SystemExit(
            "This step runs inside Blender:\n"
            "  blender --background --python scripts/blender/optimize_iss.py -- --input <model>\n"
            "(or npm run model:iss -- <model>). Without Blender, try --self-test."
        ) from None

    length, diameter, detectors = read_backend_layout()
    src = args.input.expanduser().resolve()
    out = args.output.expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"input model not found: {src}")

    def log(msg: str) -> None:
        print(f"[optimize_iss] {msg}", flush=True)

    def meshes() -> list:
        return [o for o in bpy.context.scene.objects if o.type == "MESH"]

    def triangles() -> int:
        return sum(max(0, len(p.vertices) - 2) for o in meshes() for p in o.data.polygons)

    def select(objs: list, active=None) -> None:
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)

    def world_bounds() -> tuple[Vector, Vector]:
        lo = Vector((float("inf"),) * 3)
        hi = Vector((float("-inf"),) * 3)
        for o in meshes():
            for corner in o.bound_box:
                p = o.matrix_world @ Vector(corner)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
        return lo, hi

    # 1. Import into an empty scene.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = src.suffix.lower()
    if ext in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(src))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(src))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(src))
    else:
        raise SystemExit(f"unsupported model type {ext!r} (use .glb, .gltf, .obj or .fbx)")
    if not meshes():
        raise SystemExit("the model has no meshes")
    log(f"imported {src.name}: {len(meshes())} meshes, {triangles():,} triangles")

    # 2. Keep meshes only, with their parents' transforms baked in.
    select(meshes())
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    for o in list(bpy.context.scene.objects):
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    for o in meshes():  # shared mesh data can't take an applied transform: give each its own copy
        if o.data.users > 1:
            o.data = o.data.copy()
    select(meshes())
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # 3. Long axis -> +x, centre on the origin, scale to the module size.
    lo, hi = world_bounds()
    axis = long_axis(tuple(hi - lo))
    turn = {
        0: Matrix.Identity(4),
        1: Matrix.Rotation(-1.5707963267948966, 4, "Z"),
        2: Matrix.Rotation(1.5707963267948966, 4, "Y"),
    }[axis]
    for o in meshes():
        o.matrix_world = turn @ o.matrix_world
    select(meshes())
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    lo, hi = world_bounds()
    centre, dims = (lo + hi) / 2, hi - lo
    sx, sy, sz = scale_factors((dims.x, dims.y, dims.z), length, diameter, args.uniform)
    fit = Matrix.Diagonal((sx, sy, sz, 1.0)) @ Matrix.Translation(-centre)
    for o in meshes():
        o.matrix_world = fit @ o.matrix_world
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    lo, hi = world_bounds()
    size = hi - lo
    log(
        f"scaled to {size.x:.2f} m x {size.y:.2f} m x {size.z:.2f} m "
        f"(factors {sx:.4f}, {sy:.4f}, {sz:.4f}{'; proportions kept' if args.uniform else ''})"
    )
    if not args.uniform and abs(sx - sy) / max(sx, sy) > 0.15:
        log(
            "note: length and width were scaled by more than 15 % differently; "
            "check it doesn't look stretched"
        )

    # 4. Decimate dense meshes to fit the triangle budget.
    before = triangles()
    ratio = decimate_ratio(before, args.max_tris, args.ratio)
    if ratio < 1.0:
        for o in meshes():
            if len(o.data.polygons) < MIN_FACES_TO_DECIMATE:
                continue
            select([o])
            mod = o.modifiers.new(name="FireTwinDecimate", type="DECIMATE")
            mod.decimate_type = "COLLAPSE"
            mod.ratio = ratio
            bpy.ops.object.modifier_apply(modifier=mod.name)
    log(f"decimate ratio {ratio:.3f}: {before:,} -> {triangles():,} triangles")

    # 5. One object per material (one draw call each).
    groups: dict[str, list] = {}
    for o in meshes():
        mat = o.active_material.name if o.active_material else "__no_material__"
        groups.setdefault(mat, []).append(o)
    for mat, objs in groups.items():
        if len(objs) > 1:
            select(objs, active=objs[0])
            bpy.ops.object.join()
        bpy.context.view_layer.objects.active.name = f"mesh_{mat}"[:60]
    log(f"{len(meshes())} objects, {len(bpy.data.materials)} materials after joining")

    # 6. Vent empties at the backend detector positions (contract frame -> Blender frame).
    for name, pos in [
        *((d["id"], d["position"]) for d in detectors),
        ("fire_origin", (0.0, 0.0, 0.0)),
    ]:
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.15
        empty.location = contract_to_blender(*pos)
        bpy.context.scene.collection.objects.link(empty)
        log(f"empty {name} at contract {pos}")

    # 7. Export (build_iss_model.sh adds Draco and the other compression next).
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        use_selection=False,
        export_apply=True,
        export_yup=True,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
        export_draco_mesh_compression_enable=False,
    )
    log(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB). Next: compression (build_iss_model.sh).")
    if triangles() > args.max_tris:
        log(f"warning: still {triangles():,} triangles (budget {args.max_tris:,}); try --ratio 0.2")


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.input is None:
        raise SystemExit("--input is required (or use --self-test)")
    run_in_blender(args)


if __name__ == "__main__":
    main()
