# FireTwin plan: one-page summary

Condensed from `FireTwin — Project Overview.pdf` and `FireTwin — Implementation Tasks (2).pdf`
(both by Nergis, Nov 13 2026). The PDFs win if this page disagrees with them. They are kept out
of the public repo: ask the team for them. Decisions beyond the plan: `docs/OPS_NOTES.md`.

## Idea
NASA Space Apps 2026, challenge "Flame in Freefall". A fire-safety dashboard around a 3D digital twin
of an ISS lab module. The user sets O2 %, airflow speed and direction, and a material, then ignites it.
A model trained on NASA PSI microgravity combustion data predicts whether the fire keeps burning.
Smoke drifts with the airflow (it doesn't rise in microgravity) until a vent detector trips. The app
then ranks suppression actions (fans off, cut power, CO2, water mist), each with NASA citations and a
trust level. Results can be explored in a chatbot tab (RAG) and exported as a PDF.
**Honesty rule:** the 3D flame only illustrates. Outcomes come from the model. Inputs outside the
tested ranges are flagged ("no direct NASA data"). Synthetic rows set `is_synthetic=true` and show a badge.

## Architecture (4 layers; the browser never touches data directly)
- **Frontend**: React + Vite + TS, React Three Fiber, Plotly, Zustand. Three tabs: Simulation, Results, Chat.
- **API** (FastAPI): thin routers that talk REST/JSON with the frontend.
- **Services** (plain Python, never import FastAPI): predictor (logistic regression), detector
  (smoke along the airflow), suppressor (score = extinction prob − crew-risk × weight), RAG + LLM
  (grounded, cited), cache (keyed by input hash), PDF (ReportLab), in-memory scenario store.
- **Data**: unified test table `data/processed/tests.parquet`, Chroma vector store, `investigations.json`.

This architecture summarizes the original plan. Current main uses the team-whiteboard
one-page/Compare UI rather than three tabs; see `docs/OPS_NOTES.md`. Chroma is optional
at runtime with keyword fallback, and default Docker does not mount an index/cache.
Pending decisions and observed contract gaps are recorded in `docs/DECISIONS.md`.

## API contract (source of truth: `backend/app/schemas.py`)
| Endpoint | Request → Response |
|---|---|
| `GET /meta` | → `MetaOut` (materials, ranges, investigations) |
| `POST /simulate` | `ScenarioIn` → `SimulateOut` |
| `POST /detect` | `{scenario_id}` → `DetectOut` |
| `POST /suppress` | `{scenario_id}` → `SuppressOut` (data-backed first by score; water mist last) |
| `POST /apply` | `{scenario_id, action}` → `SimulateOut` |
| `GET /results/{scenario_id}` | → `ResultsOut` |
| `POST /chat` | `{message, scenario_id?}` → `ChatOut` |
| `GET /export/{scenario_id}.pdf` | → `application/pdf` |
| `GET /health` | → `{status}` |

Contract changes need all three people to agree. Each change updates `schemas.py`, regenerates the
frontend types (`npm run gen:api`) and gets a note in `docs/CHANGELOG.md`.

## Task ID rules
`LAYER-NN` with layers DAT, ML, BE, FE, OPS. Work in phase order (0 contract + mocks → 1 parallel build
→ 2 integration → 3 quality → 4 freeze + ship), and in ID order within a phase. One task = one commit,
`TASK-ID: what changed`. `make test` and `make lint` must pass before a task counts as done. The team
runs the E2E loop (OPS-04) together at hours 10, 16 and 20.

## Who owns what (work only in your own folders)
| Person | Folders | Tasks |
|---|---|---|
| **Nergis** | `data/pipeline/label_outcomes.csv`, `build_table.py`, `ml/train.py`, `ml/artifacts/`, `ml/prompts/`, `backend/app/services/{predictor,rag,store,detector,suppressor}.py`, `backend/app/routers/simulate.py` | DAT-01–03, ML-01–07, BE-01–04 |
| **Ryan** | rest of `backend/`, `ml/ingest_rag.py`, `services/fallback.py`, `ml/tests/test_evals.py`, root files, CI | BE-05–12, ML-08–10, OPS-01–05 |
| **Nathan** | `frontend/`, `download.py`, `clean_*.py`, `data/tests/`, `data/docs/`, `processed/investigations.json`, `docs/data_card.md`, `README.md` | FE-01–11, DAT-04–09, OPS-06 |

Phase 0 (hours 0–2): Nergis DAT-01 seed table · Ryan OPS-01, BE-05, BE-06 · Nathan FE-01.
Milestone: the frontend calls the mock API.
