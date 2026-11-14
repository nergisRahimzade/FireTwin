# Changelog

One entry per task. API contract changes (rule 3) must always be noted here.

## 2026-11-14

- **OPS-01**: repo structure (one folder per layer, `.gitkeep` in empty folders), `Makefile`
  (`setup`, `data`, `train`, `dev`, `test`, `lint`; each skips with a message while its layer is
  empty), `.env.example`, `.gitignore`, `pyproject.toml` + `uv.lock` (Python 3.11, ruff, pytest,
  httpx), `tests/test_repo_structure.py`, and a placeholder `docker-compose.yml` (filled in by OPS-02).
  Also `CLAUDE.md` + an identical `AGENTS.md` (agent rules), `docs/plan/SUMMARY.md`, and
  `docs/OPS_NOTES.md` (decisions beyond the plan, for whoever owns OPS next).
  Review fixes: shared exclusion for private plan PDFs; `scripts/dev.py` supervises server process
  groups, propagates failures, and waits for bounded shutdown; `tests/test_dev.py` checks failures,
  signals, and descendant cleanup using local stand-ins. Second review round: `make dev` skips
  without calling uv, a deliberate second Ctrl+C force-stops (uv's echoed copy is ignored), `.env`
  reaching only the backend is tested, and the dev tests skip on non-POSIX systems. Reasons and
  lifecycle choices are recorded in `docs/OPS_NOTES.md`.
- **BE-05** (API contract added): `backend/app/schemas.py` with every model from the plan's
  "Shared API contract", field for field. Also added named models for the request/response bodies
  the plan's endpoint table writes inline: `ScenarioRef` `{scenario_id}` (/detect, /suppress),
  `ApplyIn` `{scenario_id, action}`, `ChatIn` `{message, scenario_id?}`, `HealthOut` `{status}`,
  plus the alias `ActionName` for the five actions. `TestRef.__test__ = False` only stops pytest
  mistaking it for a test class; the JSON schema is unchanged. FastAPI app with CORS for the Vite dev
  server (`backend/app/main.py`, `config.py`) and `GET /health`. Frontend types: nothing to
  regenerate yet (FE-01 not started).
  Review fixes (no API contract changes): validate configured CORS origins before app construction;
  make root data/ML packages importable under pytest, with `tests/test_python_imports.py` as a guard;
  expand contract tests to cover types, required nullable fields, defaults, enums, and vector shape.
  Second review round: CORS errors name the bad entry and reject host names browsers never send;
  ruff `src` includes the repo root; import rule (`app...`, never `backend.app...`) in OPS_NOTES.
- **BE-06**: `MOCK_MODE` configuration (default `1`, strict `0`/`1` flag) and conditional mock-router
  mounting. Every planned endpoint returns fixed, explicitly synthetic fixtures from
  `backend/app/mocks/`, including all five suppression actions, a fixed results table, chat
  citations, and a valid static PDF. Existing request validation and the shared contract remain
  unchanged; OpenAPI now exposes all request/response schemas. Added mock/config acceptance tests,
  frontend handoff notes in `backend/app/mocks/README.md`, and decisions in `docs/OPS_NOTES.md`.
  With `MOCK_MODE=0`, health remains available and mock feature routes are absent pending real tasks.
  Review fixes: `/results` mock rows match the BE-01 store shape (plan's 8 keys, numbered steps);
  keys of all free-form dict fields documented in `docs/contract.md`; `/health` defined once in
  `main.py`. No change to `schemas.py`.
- **OPS-03**: GitHub Actions CI (`.github/workflows/ci.yml`) on every pull request and every push
  to `main`. Job "Python (ruff + pytest)": `uv sync --locked --dev`, `make lint`, `make test`.
  Job "Frontend (tsc + vitest + build)": `npm ci`, `npm run typecheck`, `npm test`, `npm run build`.
  `tests/test_ci_workflow.py` fails if a planned check is removed from the workflow.
- **FE-04** (contract change, rule 3): `frontend/src/scene/` ISS module scene: the glTF from
  `/models/iss_lab-transformed.glb` loads in `Suspense`, with the coded 8.5 m × 4.2 m module as the
  fallback (also used when the file is missing), plus OrbitControls and detector markers at the
  `DetectOut.detectors` positions. `docs/contract.md` gains a "3D coordinate system" section shared
  by the frontend and BE-03:
  - **Axes:** origin at the module centre, `+x` = fore (the default `flow_dir`), `+y` = overhead,
    `+z` = port.
  - **Fire:** always at `(0, 0, 0)`.
  - **Vents:** BE-03's detector positions moved onto the overhead rack face (y = 1.37), so the
    markers are visible. They are `vent_fwd` `[4.0, 1.37, 0]`, `vent_aft` `[-4.0, 1.37, 0]` and
    `vent_mid` `[0, 1.37, 0]`; with `+x` = fore, the two end names swap.

  **Pending (Nergis, BE-03):** `ml/pipeline/config.py` must be updated to these positions and
  names. No change to `schemas.py`, so no frontend types to regenerate. The frontend's
  `src/lab/config.js` now matches the contract, and the old Concepts prototype is removed.
- **OPS-05**: `tests/test_demo_build.py` keeps the demo artifacts committed, non-empty and loadable,
  and checks a real prediction works with no API keys. `docs/OPS_NOTES.md` has the `demo-v1`
  tagging steps (after #14 and #16 merge; not tagged yet).
