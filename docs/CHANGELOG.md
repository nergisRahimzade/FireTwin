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
- **BE-07**: `GET /meta` from real data. `backend/app/services/meta.py` builds materials (with
  `n_tests`) from the unified table, ranges from the `"overall"` section of `feature_ranges.json`
  (the predictor's own file), and investigations from `investigations.json` once DAT-06 exists.
  `backend/app/routers/meta.py` is a thin router; missing data gives 503. Keys documented in
  `docs/contract.md`. No change to `schemas.py`. The router is not mounted in `main.py` yet.
- **BE-06 (integration)**: `main.py` mounts the real routers when `MOCK_MODE=0` (`/simulate`,
  `/apply`, `/meta`); mock mode is unchanged. `backend/tests/test_app_wiring.py` checks both modes.
- **BE-05 follow-up (Nergis's request)**: `Settings` gains `openai_api_key` (`None` when unset or
  blank; hidden from `repr`) and `openai_model` (default `gpt-4o-mini`, env `OPENAI_MODEL`), so
  `rag.py` can read them through `get_settings()` instead of `os.getenv`. `rag.py` itself unchanged.
- **BE-06 follow-up**: mock `/results` rows now match Nergis's real store exactly (`step` names,
  `sources` as `test_id` strings); a test feeds each mock row through `store.append()` and requires
  identical JSON. Open rule 5 question (badging id-only sources) recorded in `docs/contract.md`.
- **OPS-01 fix**: `make dev` could not start the real backend (`No module named 'ml'`):
  `--app-dir backend` exposes only `backend/`, but `/simulate` and `/meta` import `ml.pipeline`
  from the repo root. `scripts/dev.py` now puts the repo root first on the backend's
  `PYTHONPATH` (Docker already sets `/app/backend:/app`). Found by starting the real server.
- **BE-03 router (gap fix)**: `POST /detect` (`backend/app/routers/detect.py`), mounted in real mode.
  Runs the detector service at the scenario's current inputs and appends the `"detect"` history row
  (`detection_s`, plus the current verdict's source ids). Unknown scenario -> 404. No task in the
  plan created this router; OPS-04's e2e loop stopped here.
