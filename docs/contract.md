# API contract

Source of truth: backend/app/schemas.py (BE-05)

## Keys inside free-form fields

`schemas.py` types these fields as `dict` or `list[dict]`. The keys below are what the BE-06 mocks
serve and what the frontend builds against, so the real tasks must return the **same keys**.
Changing them is a contract change (rule 3).

| Field | Keys | Real values come from |
|---|---|---|
| `MetaOut.materials[]` | `name`, `fuel_type`, `n_tests`, `is_synthetic` | BE-07 (unified test table) |
| `MetaOut.ranges` | `{feature: {min, max, is_synthetic}}` for `o2_pct`, `pressure_kpa`, `flow_cm_s` | BE-07 from `ml/artifacts/feature_ranges.json` (ML-03) |
| `MetaOut.investigations[]` | at least `name`, `pillar`, `objective`, `source_url`, `is_synthetic` (DAT-06 adds more) | BE-07 from `processed/investigations.json` (DAT-06) |
| `DetectOut.detectors[]` | `id`, `position` (`[x, y, z]`, metres), `peak_concentration`, `is_synthetic` | BE-03 detector service |
| `ResultsOut.rows[]` | `step` (`"simulate"`, `"detect"` or `"apply"`), `inputs`, `state`, `probability`, `trust`, `detection_s`, `action`, `sources` | BE-01 store via BE-08 |
| `ChatOut.citations[]` | `title`, `investigation`, `source_url`, `snippet`, `is_synthetic` | ML-07 chat answerer |

- `ranges` uses the training feature names: `flow_cm_s`, while the request field is `flow_speed_cm_s`.
- ML-03 saves min/max per feature **and per fuel_type**; BE-07 serves the `"overall"` section
  (see the BE-07 section below).
- `is_synthetic` is `true` for placeholder values; real NASA-derived values set `false`.
- Results rows follow the real store (`services/store.py`): `step` is the step's name, `sources`
  is a list of `test_id` strings, and `None` means the step didn't produce that value (a detect
  row has only `detection_s`). The BE-06 mocks are checked against the real store, row for row.
- **Open (Nergis + Nathan, rule 5):** an id string carries no `is_synthetic`, so the results
  table can't badge synthetic sources from a row alone. Today the ids show it by convention only
  (seed ids start with `SYN-`, mock ids with `synthetic-`). Options: store full `TestRef` dicts in
  `sources`, or add an `is_synthetic` key to each row. Either is a contract change (rule 3).

## GET /meta (BE-07): keys inside the free-form fields

| Field | Keys | Source |
|---|---|---|
| `materials[]` | `name`, `fuel_type`, `n_tests`, `is_synthetic` | one entry per (material, fuel_type) in `data/processed/tests.parquet` |
| `ranges` | `{feature: {min, max, is_synthetic}}` for `o2_pct`, `pressure_kpa`, `flow_cm_s` | the `"overall"` section of `ml/artifacts/feature_ranges.json` |
| `investigations[]` | passed through from `data/processed/investigations.json` (DAT-06) | `[]` until that file exists |

- `ranges` uses training feature names (`flow_cm_s`); the request field is `flow_speed_cm_s`.
  The frontend's `testedRange()` already accepts either name.
- `is_synthetic` is `true` on a material if any of its tests is synthetic, and on every range if
  any table row is synthetic (the ranges are computed from the table).
- Missing or malformed table/ranges file -> HTTP 503 whose `detail` says what to run.

## GET /results/{scenario_id} (BE-08)

- In real mode (`MOCK_MODE=0`), returns `ResultsOut` with the requested `scenario_id` and
  `store.history(scenario_id)`, oldest first. The reader is mounted inside `main.py`'s real-mode
  `else:` branch alongside the existing real routers.
- A known scenario with no recorded steps returns 200 with `rows: []`. Nergis's
  `store.ScenarioNotFound` becomes HTTP 404, including after an in-memory store restart.
- Saved step names, historical inputs, nulls, probabilities and source-ID strings pass through
  unchanged. Tuple directions serialize as JSON arrays; no prediction or retrieval is repeated.
- GET does not append history, update inputs, or otherwise change the scenario.
- Mock mode retains BE-06's fixed results response. Its rows already match the real store, as
  checked by `test_results_rows_equal_what_the_real_store_records`; BE-08 changes neither shape.
  The existing rule 5 question about badging id-only sources remains recorded above.


## GET /export/{scenario_id}.pdf (BE-09)

- Real mode only: an in-memory ReportLab report downloaded as `application/pdf`, with
  `Content-Disposition: attachment; filename="firetwin-results.pdf"`. Mock mode keeps the fixed
  BE-06 synthetic PDF. No JSON model changes or frontend type changes.
- One `store.get()` snapshot supplies current inputs and the same ordered history as `/results`.
  All eight columns retain saved values, including nulls, zero detection times and source IDs.
  Unknown scenarios (including after a restart) map `ScenarioNotFound` to 404; known empty
  histories produce a report saying there are no recorded steps.
- Includes the title, UTC generation timestamp, current inputs, a paginated results table,
  recommended action, source list with URLs, and the exact honesty line from the plan.
- The store does not save suppression rankings. The recommendation is calculated with
  `suppressor.suppress()` for the snapshot's current inputs, explicitly labeled as calculated at
  export time, with illustrative ranking assumptions. History outcomes are never re-predicted.
- Historical sources store only IDs. The PDF resolves those exact IDs in the current unified
  table and labels synthetic references (`is_synthetic=true`); it also lists the recommendation's
  sources. Metadata is labeled as resolved at export time. Missing IDs stay visible as unverified,
  with unknown synthetic status; no URL is invented. No nearest-test replacement of saved IDs.
- Missing model/data files do not prevent exporting saved rows: the recommendation or source
  metadata is marked unavailable. PDF rendering performs no network/LLM calls and writes no files.


## POST /chat (BE-10)

- In real mode (`MOCK_MODE=0`), validates the existing `ChatIn` body and returns the existing
  `ChatOut` from `rag.answer(message, scenario)`. Message text and citation dictionaries pass
  through unchanged; there are no new length limits, trimming rules or contract fields.
- An omitted or explicitly null `scenario_id` sends `scenario=None` for a general question.
  A supplied ID is resolved before retrieval. Unknown IDs (including an empty string or an ID
  lost after restart) map `store.ScenarioNotFound` to 404.
- Scenario context has `scenario_id`, current `inputs` serialized from `ScenarioIn`, and the
  ordered `history` from one `store.get()` snapshot. This retains historical inputs, verdicts,
  actions, detection times and source IDs for comparison; only the requested scenario is included.
  Inputs and history are detached from store objects before handing them to the answerer.
- Chat never creates scenarios, applies actions, re-predicts outcomes, or appends history.
- Retrieval, citations, answer length, no-evidence answers and offline/LLM-failure fallback belong
  to the existing RAG service. Unexpected service failures are logged and return a generic 500
  (`chat failed; see server log`), without exposing exception text to the client.
- Mock mode retains BE-06's fixed synthetic chat response and ignores supplied scenario IDs.


## Prediction/explanation caching (BE-11)

- Real `/simulate` and `/apply` reuse the prediction tuple and grounded explanation for identical
  `ScenarioIn` values. A SHA-256 key includes every input field; omitted defaults and explicit
  equivalent defaults normalize to the same key. Direction, pressure, module and material are
  included even when the current predictor uses only a subset of them.
- The process-local cache holds at most 256 entries, evicts least-recently-used entries and
  expires results 60 seconds after computation finishes. Concurrent identical requests share
  one computation; different inputs may compute concurrently. Exceptions are not cached.
- Keys also distinguish API-key availability (never the key values), OpenAI/Gemini model settings
  and the burn threshold. A change between online/offline settings misses the previous entry.
  A template returned by RAG after an LLM failure counts as a successful result and can be reused
  until expiry; the router does not invent an alternative answer or citation.
- Every caller receives detached source objects. Neither scenario IDs nor store/history writes
  are cached: every `/simulate` still creates a scenario, and every `/apply` still resolves its
  ID, updates current inputs and appends a history row, including on a cache hit.
- Mock mode stays independent of the cache. `/chat`, `/results`, export and suppression ranking
  are not wrapped by this simulation cache. Shared request/response schemas are unchanged.
- `cache.clear()` invalidates entries and prevents already-running older work from refilling the
  cache. It does not reload the ML loaders: restart the backend after rebuilding model/data
  artifacts. The cache is not shared across worker processes and disappears on restart.
