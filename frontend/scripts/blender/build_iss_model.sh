#!/usr/bin/env bash
# FE-12: source model -> public/models/iss_lab-transformed.glb, in one command (run from frontend/).
#   npm run model:iss -- ~/Downloads/iss_interior.glb [--max-tris 80000] [--uniform]
# 1. Blender (headless) runs optimize_iss.py: scale to 8.5 m x 4.2 m, decimate, join by material,
#    vent empties at the backend detector positions -> public/models/iss_lab.glb
# 2. gltfjsx --transform compresses it (Draco, WebP textures at 1024, dedupe, prune) ->
#    public/models/iss_lab-transformed.glb, which src/scene/IssLab.tsx loads.
#    --keepgroups keeps the vent empties; --instance instances repeated meshes (racks, handrails).
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

# gltfjsx also writes a JSX component; we keep our own IssLab.tsx, so send that file elsewhere.
GENERATED="$(mktemp -d)/IssLabGenerated.tsx"
npx --yes gltfjsx@6.5.3 public/models/iss_lab.glb --transform --keepgroups --instance --types \
  --resolution 1024 --output "$GENERATED"

ls -lh public/models/iss_lab-transformed.glb
echo "Done. The generated component (for reference only) is at $GENERATED"
