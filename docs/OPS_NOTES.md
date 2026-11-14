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
