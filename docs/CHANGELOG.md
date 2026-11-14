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
