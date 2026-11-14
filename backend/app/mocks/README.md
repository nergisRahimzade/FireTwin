# BE-06 mock API

Run `make dev` after the team's normal setup. Mock mode defaults to `1`, so no `.env`, API key,
dataset, model, vector store, or network service is needed. The backend is at `http://localhost:8000`;
`/docs` shows all nine endpoints and `/openapi.json` exposes every contract model for FE-01.

`MOCK_MODE` accepts `0` or `1` (outer whitespace is trimmed); other values fail app construction.
The setting is captured when the app is created, so restart the server after changing it.
`MOCK_MODE=0` disables the mock router and keeps `/health`; real feature routes arrive in later tasks.

## Fixed response behavior

- `responses.py` defines validated contract-model fixtures. Every scenario has the ID
  `synthetic-scenario-001`, with a burning `/simulate` response and an extinguished `/apply` response.
- Bodies still follow the contract: missing fields, invalid action names, and malformed direction
  vectors return 422. Valid values are intentionally ignored, including unknown scenario IDs.
- `/apply` always shows the same fans-off + CO2 fixture, even if another action was requested.
  Its explanation says so. `/results` always contains the same three example rows (steps 1, 2, 3:
  simulate, detect, apply) in exactly the real store's shape (`docs/contract.md`); requests do not
  create or change stored scenarios. `/health` is defined in `main.py` and exists in both modes.
- `/meta` offers Synthetic cotton. Its range keys are training features (`o2_pct`, `pressure_kpa`,
  `flow_cm_s`); the scenario request uses `flow_speed_cm_s`, as specified by the shared contract.
- `/suppress` contains all five actions sorted by synthetic score. All have `data_support="none"`.
- `/chat` returns fixed text and a synthetic citation; no LLM or retrieval is called.
- `/export/{scenario_id}.pdf` downloads `export.pdf`, a fixed one-page PDF fixture with the same
  sample outcomes. Its response is `application/pdf`, with the attachment name
  `firetwin-synthetic.pdf`. This is not the real report renderer from BE-09.

## Synthetic data and frontend badges

Every `TestRef` sets `is_synthetic=true`. Flexible dictionaries (materials, range entries,
investigations, detectors, and citations) also carry that flag. Results rows don't have their own
flag: every row carries synthetic `sources`, and the frontend badges a row when any source is
synthetic. The keys of every dictionary are listed in `docs/contract.md`. Verdict explanations,
detector notes, action labels/explanations, chat text, and the PDF explicitly say synthetic.
The frontend must show the synthetic badge when rendering these fixtures, per the plan's honesty
rule. No frontend files are implemented by this task.

All source links use reserved `https://example.com`; they are placeholders, not NASA citations.
Trust stays weak and verdicts stay extrapolated. None of the fixture probabilities, timings,
coordinates, concentrations, or scores are measured or predicted NASA results.
