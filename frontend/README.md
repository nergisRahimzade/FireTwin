# Flame in Freefall: frontend

Vite + React + Tailwind + React Three Fiber. This is the "Flame in Freefall Concepts" prototype
ported into the repo: the three layouts (search-first portal, story & lab, three cards), the
filters, charts and data table, plus the **3D ISS Lab** tab.

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm test         # smoke-model tests (vitest)
npm run build    # production build in dist/
```

## Data and backend

- This frontend was first built in our earlier `flame-in-freefall` repo and copied here without
  its history. Until the FireTwin API exists (BE-05, `backend/app/schemas.py`), everything runs on
  the bundled data in `src/data/fallback.json`: 419 real test rows from FLEX, FLEX-2, Saffire-II and
  BASS-II, a FLEX/Saffire-II ranking, and saved report-search results for 5 demo questions.
  Typed questions match the closest demo question.
- `src/api.js` still targets the earlier repo's `GET /search` and `POST /summarize`, and is only
  used when `VITE_API_URL` is set. It should move to the FireTwin contract (`/meta`, `/simulate`,
  `/detect`, ...) once BE-05 lands, since CLAUDE.md rule 4 says the frontend talks only to the API.

## 3D ISS Lab

| File | What it holds |
| --- | --- |
| `src/lab/config.js` | Module size (8.5 m x 4.2 m), vent/detector positions, fire position, airflow options. Meters, origin at the module center. **The backend detector (`services/detector.py`) must use these same numbers.** |
| `src/lab/core.js` | Builds the module interior, vents, flame and smoke in code (no .glb, no Draco, nothing to download). |
| `src/lab/IssLabScene.jsx` | Draws the core with React Three Fiber. Smoke is one `<points>` (one draw call); `useFrame` mutates refs and never calls `setState`. |
| `src/lab/core.test.js` | Runs the smoke model headless: smoke must reach the vent downstream of the airflow. |

Controls: Ignite / Reset, 0 g ISS vs 1 g Earth, oxygen %, airflow direction, burn probability.
Burn probability defaults to the FLEX kept-burning share near the chosen oxygen level (12–34%),
and can be set by hand. On Ignite, the flame keeps burning with that chance; otherwise it goes
out on its own after a few seconds. The flame and airflow are an illustration, not a fire
simulation, and the lab clock runs 2.5x real time.

The single-file artifact version inlines `config.js` and `core.js` and draws them with plain
three.js, so both stay in sync if you edit those two files.

## FE-12 (stretch): detailed ISS module from Blender

The scene shows the coded module (`src/scene/FallbackModule.tsx`) until
`public/models/iss_lab-transformed.glb` exists. That file is built from a source model in one command:

```bash
cd frontend
npm run model:iss:check                          # no Blender needed: shows the vent layout it will use
npm run model:iss -- ~/Downloads/iss_interior.glb  # needs Blender (brew install --cask blender)
```

`npm run model:iss` runs `scripts/blender/build_iss_model.sh`:

1. **Blender, headless:** `blender --background --factory-startup --python scripts/blender/optimize_iss.py -- --input <model> --output public/models/iss_lab.glb`.
   - **Import:** the source model (`.glb`/`.gltf`, `.obj` or `.fbx`).
   - **Clean up:** drops cameras and lights, and bakes every transform.
   - **Orient and scale:** turns the long axis to +x, centres the model, and scales it to the module size in `ml/pipeline/config.py` (8.5 m long, 4.2 m across; add `--uniform` to keep proportions).
   - **Decimate:** reduces dense meshes to fit a triangle budget (`--max-tris`, default 100,000), or uses a fixed `--ratio`.
   - **Join:** merges meshes that share a material.
   - **Vent empties:** adds an empty at every detector in the backend's `DETECTORS` (`vent_fwd`, `vent_aft`, `vent_mid`), plus `fire_origin` at (0, 0, 0).
   - **Export:** a Y-up GLB.
2. **Compress:** glTF Transform (the library behind `gltfjsx --transform`) runs dedup, prune, a 1024 px WebP resize, then Draco, and writes `public/models/iss_lab-transformed.glb`.
   - Prune runs with `--keep-leaves true`. gltfjsx 6.5.3's own `--transform` prunes empty leaf nodes even with `--keepgroups`, so it deleted the vent empties when tested on a NASA model.
3. **gltfjsx:** `gltfjsx@6.5.3 --keepgroups --instance --types` writes a reference component from the compressed GLB.
   - It goes to a temp folder; `src/scene/IssLab.tsx` loads the GLB instead.

Commit only `public/models/iss_lab-transformed.glb`; the intermediate `iss_lab.glb` is git-ignored. Keep the result under about 5 MB and 100k triangles (guide, section 8). In development, `IssLab.tsx` warns in the console if the model's vent empties are missing or more than 5 cm from the contract positions.

**Source model.** NASA 3D Resources doesn't publish an ISS interior or Destiny laboratory model. Its ISS entries are exterior models: ISS (A), (B) and (D) as `.glb`, and a high-res Lightwave file (github.com/nasa/NASA-3D-Resources, science.nasa.gov/3d-resources). An interior has to come from somewhere else, such as a third-party model whose license allows this use, or one modelled by the team. Check its license before committing it.
