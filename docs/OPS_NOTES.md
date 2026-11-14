# OPS notes: decisions beyond the plan

For whoever owns Layer 5 (DevOps, OPS-01 to OPS-05) next. The plan PDFs are the source of truth.
This file lists every place where OPS work added to the plan, chose something the plan left open,
or differs from it, so a new owner (person or coding agent) knows about it.
Add an entry each time an OPS task makes a decision like this.

## OPS-01: repo structure, Makefile, .env.example, .gitignore (2026-11-14, Ryan)

**Added (not in the plan)**
- `AGENTS.md` is an exact copy of `CLAUDE.md`, so other coding agents get the same rules.
  `tests/test_repo_structure.py` fails if the two files differ: edit one, then copy it over the other.
- `docs/plan/SUMMARY.md` is a one-page summary of the plan, for quick reading in new sessions.
- `pyproject.toml` at the repo root (uv project) with dev deps ruff, pytest and httpx, plus `uv.lock`
  and `.python-version` (3.11). Runtime deps get added by the tasks that need them (BE-05, ML-01, ...).
- `tests/test_repo_structure.py` checks the planned folders, root files, Makefile targets, and that
  `.env.example` has an empty key. Without it, `make test` fails at Phase 0 (pytest exits with an
  error when it finds zero tests).
- Makefile also has `help` (the default when you type just `make`).

**Chosen (the plan left it open)**
- Every Makefile target skips with a message while its layer is empty, instead of failing:
  - `setup`: `uv sync`, then `npm ci` only if `frontend/package.json` exists.
  - `data`: runs whichever of `download.py` → `clean_*.py` → `build_table.py` exist in `data/pipeline/`.
  - `train`: runs `ml/train.py` only if it exists. It does **not** run `ml/ingest_rag.py` (ML-08).
  - `dev`: assumes the backend starts with `uvicorn app.main:app --app-dir backend` (port 8000), and
    the frontend with `npm run dev` (port 5173). Update it if BE-05 or FE-01 chooses differently.
    Review follow-up: `Makefile` delegates to the standard-library POSIX launcher `scripts/dev.py`.
    Each server gets its own process group. The first exit stops the others and preserves the
    failing server's status; SIGINT/SIGTERM stop both groups, wait up to five seconds, then force
    termination if necessary. This replaces the shell's argumentless `wait`, which hid failures,
    and its job-PID-only trap, which did not wait for shutdown or reach all descendants.
    `tests/test_dev.py` exercises these cases with local stand-ins, without npm, network, or keys.
    `.env` is passed to the backend's `uv run` only, rather than loaded into the supervisor or npm.
    The Makefile prints the skip messages itself when neither layer exists, so a fresh clone
    doesn't call `uv` (which would create `.venv` and install packages). The backend command
    keeps `--reload-dir backend`: without it, the reloader scans every `.py` file, `.venv/` included.
    A second Ctrl+C at least 1 s after the first force-stops at once. A repeat within 1 s is ignored
    on purpose: real `uv run` delivers each Ctrl+C to its child twice (the terminal signals the
    whole group and uv forwards it too), which would otherwise skip the graceful shutdown.
    `tests/test_dev.py` is skipped on non-POSIX systems (no process groups on Windows).
  - `test`: does not load `.env`, on purpose, so tests never see real API keys.
  - `lint`: Python only (`ruff check`, `ruff format --check`). Frontend checks arrive with OPS-03.
- The Chroma database folder is named `chroma_db/` and git-ignored. **ML-08 must save Chroma there.**
- pytest runs with `--import-mode=importlib`, so two layers can each have a test file with the same
  name (e.g. `test_schema.py`) without clashing. Side effect: test files can't import each other
  directly; share helpers through `conftest.py`.
- `.gitignore` ignores `.env` and `.env.*` (except `.env.example`), `data/raw/*` (except
  `data/raw/.gitkeep`), Python/Node caches, `node_modules/` and `dist/`.
  Review follow-up: it also excludes `docs/plan/*.pdf`. A local `.git/info/exclude` rule protected
  only the original checkout; the shared rule protects teammates who obtain the private plans.

**Differs from the plan, or needs follow-up**
- `docker-compose.yml` is a comments-only placeholder (it's in the repo tree, but writing it is
  OPS-02). Until then `docker compose up` stops with an "empty compose file" error.
- `ml/artifacts/` is deliberately **not** ignored, because OPS-05 commits prebuilt artifacts there.
- OPS-05 says the demo should need no network except the LLM. If that means the vector store must
  ship prebuilt, OPS-05 has to stop ignoring `chroma_db/` (or rebuild it offline at startup).
- The plan PDFs are kept out of the repo (it's public). `docs/plan/SUMMARY.md` is committed instead.
- `frontend/src/*` already holds `.gitkeep` files, so Vite's scaffolder (FE-01) warns that the folder
  isn't empty. Choose "Ignore files and continue".
- `ml/prompts/` (ML-06/07) appears in the tasks but not in the repo tree, so OPS-01 didn't create it.
- The CI status check can only be required on `main` after OPS-03 adds the GitHub Actions workflow.

## BE-05: root-config changes and follow-ups (2026-11-14, Ryan)

**Changed in root files**
- `pyproject.toml`: runtime deps `fastapi` and `uvicorn`. Plain `uvicorn`, not `uvicorn[standard]`,
  so it reloads with StatReload. pytest `pythonpath = [".", "backend"]`, so tests import `app...`
  the same way uvicorn does and can import `data.pipeline` and `ml` from the repo root. The root
  entry was added on review: importlib mode does not add it automatically when `uv run pytest`
  runs the console entry point. `tests/test_python_imports.py` guards all three layer imports.
  Ruff `src = [".", "backend"]` makes the import sorter treat `data`, `ml` and `app` as our own
  code; it does not affect Python module resolution.
  **Import rule:** always `import app...`, never `backend.app...`. With the repo root on the path,
  `backend.app.schemas` would load a second, separate copy of the same file, whose classes don't
  match `app.schemas` (so `isinstance` checks and model comparisons would quietly fail).
- `scripts/dev.py` (the backend command `make dev` runs): added `--reload-dir backend`. See the
  OPS-01 `dev` note above.

**Chosen (the plan left it open)**
- New optional env var `CORS_ORIGINS` (comma-separated; default `http://localhost:5173` and
  `http://127.0.0.1:5173`). It is left out of `.env.example` because the plan lists only
  `OPENAI_API_KEY` and `MOCK_MODE`; add it there if Docker or a deployed frontend needs another origin.
  Review follow-up: every entry must be an explicit HTTP(S) origin with a host and a valid optional
  port, without credentials, whitespace, wildcards, paths (including a trailing slash), queries,
  or fragments. `*` and `null` are intentionally unsupported. Invalid entries reject the entire
  setting at app construction, so a URL typo cannot silently block the frontend. The error names
  the bad entry. Hosts with an empty part (`a..test`, `localhost.`) or a part starting or ending in
  `-` are rejected too, because no browser sends them. A valid but wrong origin (e.g. port `5137`
  instead of `5173`) still can't be detected: check the browser console's CORS error if it happens.
  Pydantic's existing URL parser normalizes host case, default ports, IDNs, and IPv6 to browser
  Origin serialization; this avoids rejecting a browser whose configured URL uses another spelling.
- `/health` lives in `main.py`, not a router, because the plan's router list has no place for it.
- Contract tests pin all field types, requiredness, defaults, and Literal values, including named
  inline bodies. Behavioral cases distinguish explicit null from omission, exercise allowed and
  rejected enum values, and check the three-number direction vector. The API contract itself
  has not changed, so no frontend type regeneration is needed for this review follow-up.

**Follow-ups**
- Starlette prints a deprecation warning: using `httpx` with its TestClient is deprecated in
  favour of `httpx2`. The plan specifies httpx (BE-12), so it stays for now. Revisit before
  OPS-03 if warnings ever become errors.
- Proposals only, **not done** (they change contract behaviour, so all three must agree):
  reject unknown request fields (`extra="forbid"`), and enforce the commented ranges
  (O2 10–40, flow 0–40) as validation.

## BE-06: fixed synthetic mock API (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- `MOCK_MODE` defaults to `1`, matching `.env.example`, so Phase 0 works without local `.env`,
  keys, data, or artifacts. Only `0` and `1` are accepted after whitespace trimming; an invalid
  flag fails app construction. Each app captures the setting once.
- Mock routes live in `backend/app/mocks/router.py`, including `/simulate` and `/apply`, so no real
  router or service ever contains mock code. `/health` is defined once in `main.py` and exists in
  both modes. With the flag off, only `/health` is mounted until the real feature tasks land.
- Every valid request returns a fixed fixture from `mocks/responses.py`. Request bodies are still
  validated against the existing contract, but valid inputs, action choices, chat text and IDs
  are ignored. Unknown scenario IDs return the same fixture, and no scenario history is stored.
  `/apply` always returns the combined fans-off + CO2 example; its explanation labels this.
  These mocks do not implement the real simulation, scenario store, or suppression logic.
- All test references set `is_synthetic=true`; flexible dictionaries also include the flag.
  Numbers without a top-level flag in the fixed contract are labeled through explanations/notes
  and synthetic source references. All sources use reserved `https://example.com`, not invented
  NASA citations; trust is weak, extrapolated is true, and action data support is none.
  Frontend owners must display the plan's synthetic badges when using these fixtures.
- `/meta.ranges` uses the training feature name `flow_cm_s`; the request field remains
  `flow_speed_cm_s`, as in the plan. No contract fields or types changed. All 13 named models
  now appear in OpenAPI through actual request/response annotations; frontend generation is FE-01.
- PDF export returns a static, valid one-page `mocks/export.pdf` fixture with synthetic labels
  and the same sample outcomes. It was authored once using the Python standard library, so
  BE-06 adds no dependency and does not implement the later ReportLab renderer (BE-09).
  `backend/app/mocks/README.md` documents the frontend handoff and fixed-response limitations.
- Review follow-up: the mocks' free-form dictionaries are now the de facto contract, so their keys
  are written down in `docs/contract.md`. `/results` rows use exactly the BE-01 store's shape:
  the plan's 8 keys, `step` as a number, `None` where a step made no value, and no row-level
  `is_synthetic` (a row is badged when any of its sources is synthetic). **Ask Nathan** whether
  FE-09 wants `step` as a number; switching to names would change BE-01 and these mocks together.

**Follow-ups**
- `MOCK_MODE` defaulting to `1` suits Phase 0, but once real routes exist a deployment that
  forgets to set it would quietly serve fixtures. OPS-02 should flip the default to `0`, or switch
  to mock mode only when `ml/artifacts/` is missing (the plan's wording for `docker compose up`).
- Open with Nergis: how ML-03's per-fuel-type ranges map onto the flat `MetaOut.ranges` shape.

**Checks**
- `backend/tests/test_mocks.py` covers each endpoint, request validation, the fixed mock loop,
  synthetic labels, disabled mode, app isolation, PDF structure, and all OpenAPI models.
  Checks use in-process HTTP and no keys, network services, data files, or ML artifacts.

## OPS-03: CI (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- Python runs `make lint` and `make test`, the same commands as rule 7, so CI and laptops can't
  disagree about what "passing" means. `UV_LOCKED=1` makes any `uv run` fail if `uv.lock` is out
  of date with `pyproject.toml` (someone forgot `uv lock`), instead of quietly re-locking.
- Versions match OPS-02: uv 0.13.5 (as in `docker/backend.Dockerfile`), Python 3.11 from
  `.python-version`, Node 22 (as in `docker/frontend.Dockerfile`).
- Runs on pull requests into **any** branch, so stacked PRs (e.g. into a teammate's branch) are
  checked too, plus pushes to `main`. A newer push cancels the older run of the same PR.
- The workflow token is read-only (`permissions: contents: read`); CI never writes to the repo.
- Actions are pinned to major tags (`@v4`, `@v6`), not commit SHAs: simpler for a 24-hour build;
  pin SHAs if the repo outlives the hackathon.

**Added (beyond the plan's "npm run build + tsc")**
- The frontend job also runs `npm test` (vitest), because FE already has unit tests
  (e.g. `controlPanel.logic.test.ts`); untested tests rot.

**Follow-up for the repo owner**
- Once CI has run green once, make it required for `main`: Settings -> Rules -> Rulesets ->
  `protect-main` -> **Require status checks to pass** -> add **"Python (ruff + pytest)"** and
  **"Frontend (tsc + vitest + build)"** (GitHub only offers checks it has already seen run).

## BE-07: /meta choices and integration follow-ups (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- Built on Nergis's branch stack (`BE-02-simulate-apply`), the only place with BE-05, the seed
  table, `feature_ranges.json` and her cached loaders (`ml.pipeline.model.load_table/load_ranges`),
  which `/meta` reuses instead of reading the files a second way.
- `ranges` = the flat `"overall"` section of `feature_ranges.json`, because the frontend's
  `MetaOut.ranges` type is one `{min, max}` per feature. The per-fuel-type ranges stay in the file
  for the predictor; if the UI later wants them, that's a contract change.
- `is_synthetic` is derived from the table (any synthetic row behind a material or the ranges),
  since `feature_ranges.json` doesn't record it (rule 5).
- `investigations` is `[]` until DAT-06 writes `investigations.json`; nothing is made up.
- Missing or broken data files -> 503 with a "run `make data` / `make train`" message.

**Integration follow-ups (not done here)**
- Done on `feature/BE-integration`: with `MOCK_MODE=0`, `main.py` mounts the real `/simulate`,
  `/apply` (BE-02) and `/meta` (BE-07). Their imports sit inside that branch so mock mode still
  starts without pandas, the model or data files. BE-08 adds `/results` in the same real-mode
  branch, and BE-09 adds `/export`. `/detect`, `/suppress` and `/chat` remain unbuilt in real
  mode; mock mode serves all endpoints.
- BE-05 is not on `main`: PR #3 merged into `feature/OPS-01` instead. It reaches `main` when
  Nergis's stack merges (her branches contain it).

## Integration follow-ups (2026-11-14, Ryan, `feature/BE-integration`)

- `config.py` now carries the OpenAI settings (`openai_api_key`, `openai_model`). **Nergis:**
  switch `rag.py`'s `os.getenv("OPENAI_API_KEY")`/`os.getenv("OPENAI_MODEL")` to
  `get_settings()`; the defaults match, so behaviour doesn't change. `OPENAI_MODEL` is optional and
  left out of `.env.example`, which lists only the plan's two settings.
- The key field uses `repr=False`, so logging or printing `Settings` never leaks it.
- Mock `/results` rows were realigned from my earlier BE-01 shape (numbered steps, full source
  objects) to Nergis's pushed store (step names, `test_id` strings), which is what BE-08 serves.
  `test_results_rows_equal_what_the_real_store_records` keeps the two from drifting apart.
- Open with Nergis and Nathan (rule 5): id-only `sources` can't carry `is_synthetic`; see the
  "Open" note under `ResultsOut.rows` in `docs/contract.md`.
- `make dev` now gives the backend `PYTHONPATH=<repo root>` (the frontend is unchanged), like
  the OPS-02 image's `PYTHONPATH=/app/backend:/app`. Tests hadn't caught the missing path because
  pytest's own `pythonpath = [".", "backend"]` hides it; `tests/test_dev.py` now checks the env.
- **Gap closed for `/detect` and `/suppress`** (`feature/BE-03-04-routers`): thin routers over
  Nergis's services, mounted in real mode. `/detect` appends the "detect" row (with the current
  verdict's source ids); `/suppress` appends nothing. Combined with BE-08 and BE-09 on
  `feature/BE-real-mode`, the real-mode e2e loop (`make e2e`, OPS-04) **passes all 8 steps**:
  cable insulation -> burning (p 0.93) -> alarm at 40 s -> `fans_off_co2` -> extinguished ->
  3 history rows -> a 2-page PDF with the honesty line and synthetic labels.
  Seen in that run: with flow `+x` (fore) the backend reports `vent_aft` tripping, because
  `ml/pipeline/config.py` still uses the old vent names (see "3D coordinate system", BE-03 follow-up).

## BE-08: read-only scenario results (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- Rebased onto `origin/feature/BE-integration` (PR #9), which already combines BE-06 and Nergis's
  stack plus BE-07. OPS-02's pending work and running containers remain separate.
- `backend/app/routers/results.py` serves the copied rows from `store.history(scenario_id)`
  in the existing `ResultsOut` model. Unknown IDs map Nergis's `store.ScenarioNotFound` to HTTP 404
  with its restart hint; a known empty history returns 200 with an empty list.
- `main.py` imports and mounts the reader only in the existing real-mode `else:` branch
  (`MOCK_MODE=0`). Mock mode keeps its fixed router, with no duplicate real results route.
  Results is removed from the mock tests' unbuilt-route list and added to real app wiring checks.
- Stored step names, source-ID strings, snapshots and nulls pass through unchanged; GET neither
  recalculates outcomes nor changes history/current inputs. No store, schema or frontend changes.
- Mock results already match this shape through the integration branch's
  `test_results_rows_equal_what_the_real_store_records` regression. The earlier BE-08 notes about
  numbered mock steps/full references were stale and are removed. The existing id-only synthetic
  badge question remains with the store/frontend owners, without introducing unapproved row keys.

**Checks**
- `backend/tests/test_results.py` explicitly selects real mode and covers ordered snapshots,
  JSON arrays, nulls, source IDs/probabilities, empty/unknown scenarios, isolation, read-only
  behavior, new rows after earlier reads, restart loss and OpenAPI.
- `test_app_wiring.py` checks a real simulate/apply/results sequence against the stored history,
  while a mock request for a real scenario still returns the fixed synthetic fixture.

## BE-09: PDF export (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- Based on completed BE-08 (itself based on `feature/BE-integration`). `routers/export.py` mounts
  only in `main.py`'s real-mode branch; BE-06's fixed synthetic PDF stays unchanged.
- `services/pdf.py` uses ReportLab (already a runtime dependency) and `BytesIO`; no report files,
  new packages, HTTP/LLM calls, or changes to the store, shared schemas or teammates' files.
- `store.get()` provides one snapshot of current inputs plus the same saved rows as `/results`.
  The landscape table includes all eight columns, exact saved values and input snapshots, repeats
  column headers across pages, and splits long rows. Current inputs are labeled separately.
- The store saves no ranked recommendation. The report calls Nergis's existing
  `suppressor.suppress()` for the snapshot's current inputs and labels it "Calculated at export
  time", alongside the ranking's illustrative crew-risk/detection-delay assumptions. It never
  calls `predict()` or `rag.explain()` to replace recorded history outcomes.
- Sources are resolved by the saved IDs in the current test table, not by rerunning nearest-test
  retrieval. The selected recommendation's references are included too. The PDF explicitly labels
  metadata as resolved at export time, synthetic sources with `is_synthetic=true`, model outputs
  and illustrative detection times. It does not solve the results JSON's id-only badge question
  by changing that contract.
- If artifacts/data are missing or malformed, saved rows still export; recommendation and source
  metadata are labeled unavailable/unverified, and unknown IDs get no invented URL or synthetic
  status. Unknown scenarios map `ScenarioNotFound` to 404; an existing empty history is a valid PDF.
- PDFs include a UTC timestamp, a stable generic download filename (never raw user text in headers),
  and the required line "Flame is illustrative; verdicts come from NASA PSI data." All text is
  escaped before ReportLab markup parsing so source URLs/materials cannot cause image fetching.
- PDF page compression is disabled so report content can be checked without adding a PDF-parser
  package. PDFs remain standard, downloadable documents; source URLs are printed as text.

**Checks**
- `test_export.py` checks required content, exact results-to-renderer parity, precision/nulls/zero,
  synthetic and unknown sources, read-only behavior, empty/unknown IDs, unavailable data/model,
  escaped markup without image loading, pagination, scenario isolation, PDF OpenAPI and mock mode.
- `test_app_wiring.py` runs simulate -> export on the real seed files with the API key removed.

## OPS-04: end-to-end loop (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- `tests/e2e_loop.py` is a script run by `make e2e`, not by `make test`: it needs a server that's
  already running (`make dev` or `docker compose up`, with `MOCK_MODE=0`). Its name doesn't start
  with `test_`, so pytest never collects it. `tests/test_e2e_loop.py` runs the same loop
  in-process against the BE-06 mock app (no server, no network), so CI tests the checks themselves.
- Beyond "PDF is non-empty", each step is checked against `schemas.py`, and the steps against each
  other: same `scenario_id` throughout; `/suppress` sorted by score with `recommended` on top;
  `/apply` inputs equal the recommended action's `new_inputs` (plan BE-02); `/results` contains the
  apply step; `/export` is `application/pdf` starting with `%PDF`.
- It ignites "cable insulation" (the demo script's material) when `/meta` offers it, else the first
  material, at 21 % O2 and 10 cm/s.
- A mock-mode API fails the run (the plan says "hits the real API"); `--allow-mock` checks wiring only.
- `make help` now lists targets with digits in their names (`e2e`).

**Status on 2026-11-14:**
- On `main` before #16: mock mode passed all 8 steps; real mode stopped at `meta: HTTP 404`
  because `main.py` mounted no real routers.
- With #16 (`feature/BE-real-mode`: real-mode wiring, `/detect`, `/suppress`, `/results`,
  `/export`), a real-mode server with no API keys **passes all 8 steps** (`make e2e`).

**Gap in the plan:** BE-03 and BE-04 build the detector and suppressor *services*, but no task ID
creates the `/detect` and `/suppress` *routers*. Under the plan's ownership table they fall under
"rest of `backend/`" (Ryan); they're built on `feature/BE-03-04-routers`.
