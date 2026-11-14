# FireTwin: instructions for Claude Code

NASA Space Apps 2026, "Flame in Freefall". Read `docs/plan/SUMMARY.md` for the one-page plan.
The full plan PDFs (Project Overview, Implementation Tasks) are the source of truth; they are kept
out of Git, so get them from the team and put them in `docs/plan/` locally.
Read `docs/OPS_NOTES.md` for decisions that go beyond the plan.

## Rules for Claude Code (copied word for word from the Implementation Tasks doc)

1. Read the Project Overview first. It defines the idea, architecture and design decisions.
2. Task IDs follow `LAYER-NN` (DAT, ML, BE, FE, OPS). Work in phase order (see Build phases), and inside a phase, in ID order.
3. Never change the API contract without updating `backend/app/schemas.py`, regenerating frontend types, and noting it in `docs/CHANGELOG.md`.
4. Keep layers separate: frontend talks only to the API; services never import FastAPI; data scripts never import backend code.
5. Any number the user sees must trace to a NASA test row or be labeled. Synthetic or placeholder data must set `is_synthetic=true` and show a "synthetic" badge in the UI.
6. Small commits, one task per commit, message `TASK-ID: what changed`.
7. After each task, run `make test` and `make lint`. Do not mark a task done if either fails.
8. When a task is done, explain in 1–2 plain sentences what each new or changed file does.

## Project notes

- Stack is fixed: Python 3.11, FastAPI, Pydantic v2, React + Vite + TS, Docker Compose.
- Use uv for Python (the team already uses it) and npm for the frontend.
- Folder ownership: Nergis, Ryan and Nathan each work only in their own folders (see the Phases
  table in `docs/plan/SUMMARY.md`).
- Never commit .env or any API key.
