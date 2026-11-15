#!/usr/bin/env bash
# FE-12: source model -> public/models/iss_lab-transformed.glb, in one command (run from frontend/).
#   npm run model:iss -- ~/Downloads/iss_interior.glb [--max-tris 80000] [--uniform]
# 1. Blender (headless) runs optimize_iss.py: scale to 8.5 m x 4.2 m, decimate, join by material,
#    vent empties at the backend detector positions -> public/models/iss_lab.glb
# 2. glTF Transform compresses it (dedupe, prune keeping leaves, WebP at 1024, Draco) ->
#    public/models/iss_lab-transformed.glb, which src/scene/IssLab.tsx loads.
# 3. gltfjsx --keepgroups --instance writes a reference component from it.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: npm run model:iss -- <model.glb|.gltf|.obj|.fbx> [optimize_iss.py options]" >&2
  exit 2
fi
SOURCE="$1"; shift

BLENDER="${BLENDER:-$(command -v blender || true)}"
if [[ -z "$BLENDER" && -x /Applications/Blender.app/Contents/MacOS/Blender ]]; then
  BLENDER=/Applications/Blender.app/Contents/MacOS/Blender
fi
if [[ -z "$BLENDER" ]]; then
  echo "Blender not found. Install it (e.g. brew install --cask blender) or set BLENDER=/path/to/blender." >&2
  exit 1
fi

mkdir -p public/models
"$BLENDER" --background --factory-startup --python scripts/blender/optimize_iss.py -- \
  --input "$SOURCE" --output public/models/iss_lab.glb "$@"

# 2. Compress for the web with glTF Transform, the library gltfjsx --transform runs. We call it
#    ourselves because gltfjsx 6.5.3's --transform prunes empty leaf nodes even with --keepgroups,
#    which deletes the vent empties. Same steps: dedupe, prune (keeping leaves), WebP at 1024, Draco.
GT="npx --yes @gltf-transform/cli@4.1.1"
WORK="$(mktemp -d)"
$GT dedup public/models/iss_lab.glb "$WORK/1.glb"
$GT prune "$WORK/1.glb" "$WORK/2.glb" --keep-leaves true
$GT resize "$WORK/2.glb" "$WORK/3.glb" --width 1024 --height 1024
$GT webp "$WORK/3.glb" "$WORK/4.glb"
$GT draco "$WORK/4.glb" public/models/iss_lab-transformed.glb

# 3. gltfjsx writes a reference JSX component (--keepgroups keeps the vent empties in it,
#    --instance instances repeated meshes). We keep our own IssLab.tsx, so it goes to a temp folder.
GENERATED="$WORK/IssLabGenerated.tsx"
npx --yes gltfjsx@6.5.3 public/models/iss_lab-transformed.glb --keepgroups --instance --types \
  --output "$GENERATED"

ls -lh public/models/iss_lab-transformed.glb
echo "Done. The generated component (for reference only) is at $GENERATED"
