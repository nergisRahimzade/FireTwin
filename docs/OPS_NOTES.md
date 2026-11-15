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
- OPS-01 created `docker-compose.yml` as a comments-only placeholder; OPS-02 below now implements
  the two-service stack.
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
- Starlette warns that using `httpx` with its TestClient is deprecated in favour of `httpx2`.
  The plan specifies httpx (BE-12), so `pyproject.toml` ignores **exactly** that message and
  class (`StarletteDeprecationWarning`, which is a `UserWarning`, not a `DeprecationWarning`).
  Any other warning still shows. Switch to httpx2 if Starlette ever drops httpx support.
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
- Native `MOCK_MODE` still defaults to `1`. OPS-02 adds automatic missing-file fallback at the
  container entrypoint instead of changing native parsing. An explicit `MOCK_MODE=1` still
  forces fixtures; blank/unset mode in Docker selects real mode when required files exist.
- Open with Nergis: how ML-03's per-fuel-type ranges map onto the flat `MetaOut.ranges` shape.

**Checks**
- `backend/tests/test_mocks.py` covers each endpoint, request validation, the fixed mock loop,
  synthetic labels, disabled mode, app isolation, PDF structure, and all OpenAPI models.
  Checks use in-process HTTP and no keys, network services, data files, or ML artifacts.

## OPS-03: CI (2026-11-14, Ryan)
## BE-07: /meta choices and integration follow-ups (2026-11-14, Ryan)

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
  branch, BE-09 adds `/export`, and BE-10 adds `/chat`. Merging current `main` also brings
  the `/detect` and `/suppress` routers; all planned endpoints now exist in both modes.
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

## OPS-05: demo build (2026-11-14, Ryan)

**Done**
- The prebuilt artifacts are committed on `main`: `data/processed/tests.parquet` and
  `ml/artifacts/{model.joblib,feature_ranges.json,metrics.json,physics_params.json}`.
  `tests/test_demo_build.py` fails if any is untracked, empty or unloadable, or if a real
  prediction needs an API key. RAG retrieval is keyword search over `data/docs` (no Chroma), and
  `rag.py` falls back to a template without `GEMINI_API_KEY`/`OPENAI_API_KEY`, so the only network
  use is the optional LLM.

**Tag `demo-v1` on a green `main` (#14 OPS-04 and #16 real mode are both merged):**
```bash
git switch main && git pull                 # or: git fetch origin main:main
make lint && make test                      # rule 7
MOCK_MODE=0 make dev                        # in one terminal (or docker compose up, once OPS-02 lands)
make e2e                                    # in another: must print "e2e: PASS (real API ...)"
git tag -a demo-v1 -m "Demo build: real mode passes make e2e"
git push origin demo-v1                     # tags are pushed separately from branches
```
- A tag is a fixed name for one commit: the demo runs from `git checkout demo-v1`, whatever lands
  on `main` afterwards. If a fix is needed later, tag `demo-v2` instead of moving `demo-v1`.
- Rehearse on a fresh clone with no `.env`: `make setup` needs the network once (packages), then
  the demo runs offline apart from the optional LLM.

## BE-10: scenario-aware chat endpoint (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- Built on completed BE-09, which includes BE-08 and the `feature/BE-integration` base. The
  chat router is imported and mounted only inside `main.py`'s existing real-mode `else:` branch.
  Mock mode retains its fixed fixture; `/chat` moves out of the mock tests' unbuilt-path list.
- The router calls Nergis's unchanged `rag.answer(message, scenario)` and returns its `ChatOut`.
  `ChatIn`/`ChatOut`, RAG/store services, ML prompts, frontend types and dependencies are unchanged.
- Scenario summary = the ID, current inputs and full ordered history from one `store.get()`
  snapshot. Inputs are dumped into a new JSON-ready dictionary; history is already copied by the
  store. This lets the answerer compare initial and applied inputs and see saved outcomes, action
  names, detection times and source IDs, without exposing mutable store references.
- Omitted/null IDs mean general chat (`scenario=None`). Any supplied ID is looked up, including
  the empty string: missing IDs become 404 with the store's restart hint, before RAG is invoked.
  A known scenario with no steps still supplies its inputs and empty history.
- No chat history row is added (the store's planned steps are simulate/detect/apply). Chat does
  not change inputs, run a prediction, or include any other scenario in the context.
- Message text and RAG citations pass through; request validation remains with existing Pydantic
  models. No new blank-message rejection, truncation or trimming policy is introduced.
- RAG owns retrieval and offline fallback. Unexpected answerer failures return a generic 500,
  following `/simulate` and `/apply`; raw exception details stay out of the HTTP response.

**Checks**
- `test_chat.py` covers general/null IDs, unchanged message/citations, current and historical
  inputs, empty/unknown scenarios, context isolation, validation, offline retrieval/no evidence,
  real RAG serialization into a faked LLM call, LLM-failure fallback, generic service errors,
  OpenAPI and fixed mock behavior. All documents and LLM responses in these tests are synthetic.
- App wiring includes a real simulate -> chat sequence with the key removed and no documents
  required; chat receives the newly created scenario without appending history.

## BE-11: prediction and explanation cache (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- `services/cache.py` memoizes the existing prediction tuple plus `rag.explain()` result using
  SHA-256 over all normalized `ScenarioIn` fields. This is a plain Python service with no HTTP
  imports or new dependencies. IDs and state transitions remain outside the cache.
- Operational bounds: 256 entries per process, least-recently-used eviction, 60-second expiry
  measured from completion with a monotonic clock. This also bounds how long a successful offline
  template returned after an LLM failure is reused before retrying the service.
- Cache keys include online/offline API-key availability and OpenAI/Gemini model environment
  settings, not raw keys, plus `BURN_THRESHOLD`. Input defaults are normalized so omitted/default
  flow directions and explicitly supplied floating-point equivalents share an entry.
- A lock protects cache bookkeeping; a shared future combines concurrent identical misses.
  Prediction and explanation run outside the lock so different inputs can proceed in parallel.
  Failures wake waiters and are not cached. Each caller receives a deep copy of the cached data.
- `clear()` invalidates completed entries and detaches in-flight work using a generation number;
  older work can finish for existing callers but cannot restore stale entries after clearing.
- Artifact/data reloading is still owned by the existing ML loaders. Restart the backend after
  rebuilding those files. No persistent cache, distributed cache, startup hooks or HTTP clearing
  endpoint is added; mock mode and the chat/results/export/suppression paths are unchanged.

**Ownership exception approved by the user**
- `routers/simulate.py` belongs to Nergis. The user explicitly approved the prepared integration
  patch for BE-11 after reviewing the cache and patch: replace direct predict/explain calls in
  `run_step()` with `cache.predict_and_explain(inputs)` and adjust its import. Scenario creation,
  the burn threshold, `/apply` input updates and every history write remain in her router.
  Predictor, RAG, store, suppressor, ML files, schemas and frontend are unchanged.

**Checks**
- `test_cache.py` covers hits, equivalent defaults, changed fields, result isolation, expiry,
  eviction, errors, model/mode settings, clearing and concurrent work, using synthetic results.
- `test_cache_api.py` proves repeated simulations keep distinct IDs, repeated/no-op applications
  still append history, modified inputs compute separately, applied results can be reused by new
  scenarios, unknown IDs stay 404 and mock mode never invokes the cache.


## BE-10 / BE-11 integration into main (2026-11-14, Ryan)

- PR #19 uses `feature/BE-09`, which now includes merged BE-10 and BE-11 PRs. Main already
  contains BE-08/BE-09 through the real-mode integration, so this PR adds chat and caching.
- Resolved the real-router conflict by keeping every router: simulate/apply, meta, detect,
  suppress, results, export and chat. Kept main's Gemini/OpenAI RAG support and all upstream
  data, frontend, CI and end-to-end work. Shared schemas are unchanged.
- All endpoints are now implemented in real mode, so the old mock-only/unbuilt-route list and
  empty parameterized check are removed. App wiring still checks the complete real route set;
  per-app mode isolation uses mock acceptance versus real 404 for an unknown scenario ID.
- Both sides' changelog and operational notes are retained. The backend ownership exception
  remains limited to BE-11's approved predict/explain call-site change.
- Validation of the resolved integration: `make test` 492 passed, `make lint` passed (83 files),
  and `make e2e` passed all 8 steps against a temporary real-mode server with both LLM keys
  removed. An additional real-mode chat request returned the expected no-evidence response.
- Validation of the resolved integration: `make test` 504 passed, `make lint` passed (84 files),
  and `make e2e` passed all 8 steps against a temporary real-mode server with both LLM keys
  removed. An additional real-mode chat request returned the expected no-evidence response.
- Main advanced during validation with OPS-05 (#17); its demo-artifact checks and notes were
  retained and the documentation conflict was resolved before the final 504-test run. Runtime
  code is the same code exercised by the real end-to-end loop above.

## OPS-02: Docker Compose development stack (2026-11-14, Ryan)

**Chosen (the plan left it open)**
- The original BE-06-based stack is synchronized with current `main` before publication, so
  all real backend routes and ML artifacts are available. Native application files and the
  frontend dependency versions are preserved.
- `docker/backend.Dockerfile` uses Python 3.11 on Debian Bookworm plus uv 0.13.5, matching the local
  uv version. It installs only runtime packages using `uv sync --locked --no-dev`; the container
  runs uvicorn directly rather than resolving/installing dependencies at startup.
  `docker/frontend.Dockerfile` uses Node 22 Bookworm, `npm ci`, and Vite on `0.0.0.0:5173`.
  Dockerfiles stay in root-owned `docker/`, without changing frontend application files.
- Both services run as non-root users with `init: true` and a shutdown grace period. Frontend
  startup waits for backend `/health`, and both services have health checks using their existing
  Python/Node standard libraries. Host ports bind to loopback; source changes require rebuilding.
- `data/` and `ml/artifacts/` are read-only bind mounts, with host-path creation disabled so typos
  cannot create empty directories as root. `.dockerignore` allowlists source/locks/container tooling
  and excludes private docs, `.env` files, caches, host dependencies, data and model contents.
- The standalone `docker/backend_entrypoint.py` resolves unset/blank `MOCK_MODE` before backend
  import: missing/empty table, model or feature ranges selects synthetic mocks; otherwise real
  mode. These paths match the predictor readers. Explicit `1` forces mocks, while explicit `0`
  fails on missing files. This changes Docker startup only; the backend still receives strict 0/1.
  File contents are not loaded by the entrypoint. Current main provides all real feature routers.
- Compose does not require `.env` or load arbitrary env files into either service. It interpolates
  only named settings, forwarding OpenAI/Gemini keys and optional model selections to the backend
  only. Gemini forwarding follows the provider support already on main; blank model settings
  preserve the service defaults. The public frontend API URL
  points at localhost (the browser's network), never the Compose-only `backend` DNS name.
  Optional `BACKEND_PORT`/`FRONTEND_PORT` overrides also adjust default API URL/CORS; explicit
  `VITE_API_URL`/`CORS_ORIGINS` overrides remain possible. Details are in `docker/README.md`.

**Checks and follow-ups**
- `tests/test_container_startup.py` tests fallback, required files, explicit modes, bad settings,
  and entrypoint execution without Docker, keys or model loading. Full `make test`/`make lint`
  remain required. Runtime container checks use a separate project and temporary ports so an
  existing native dev stack is not stopped or overwritten.
- `npm ci` reports existing advisories in the frontend lockfile. OPS-02 preserves Nathan's
  dependency versions; updating them is separate work. No host packages are installed by this task.

**Publication validation (current main)**
- `make test`: 523 passed in 20.04s. `make lint`: passed, 87 files formatted.
- Built both images from the current lockfiles. A separate Compose project with temporary ports
  passed both health checks, automatic real mode without `.env` or keys, browser API URL/CORS,
  non-root execution, read-only mounts and the real OPS-04 loop through PDF export.
- Container checks also passed automatic mock fallback without mounted artifacts, explicit real
  failure on missing artifacts, explicit mocks with artifacts and Gemini model forwarding using
  a fake key without an LLM call. The temporary project was removed cleanly; the existing user
  stack was left running. Host Python/Node dependencies and application files were not modified.

## BE-12: endpoint tests (2026-11-14, Ryan)

- Most endpoints already had detailed tests in their own files (mocks, meta, detect, suppress,
  results, export, app wiring). BE-12 adds one matrix, `backend/tests/test_endpoints.py`, that
  answers "is every endpoint tested in both modes?" with status + contract checks, instead of
  duplicating those detailed tests.
- **Coverage guard:** each mode's OpenAPI routes must equal the matrix rows, so a new endpoint
  fails the suite until it gets a row (and so a test in both modes).
- BE-10 (#15, via #19) brought the real `/chat`, so all 9 endpoints are tested in **both** modes,
  and `/chat` is in the unknown-scenario 404 check.
- The plan's ordering test already existed at service level (`test_suppressor.py`); BE-12 adds the
  same check through `POST /suppress` in real mode.
- Requests go through FastAPI's `TestClient` (httpx's client API; it now runs on httpx2, which the
  `openai` package brings in).
- **Fixed:** `conftest.py` cleared the Gemini key but not `OPENAI_API_KEY`, despite its comment.
  `test_no_llm_key_reaches_a_test` fails without the fix (checked by reverting it).
