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
