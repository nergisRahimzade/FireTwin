# API contract

Source of truth: backend/app/schemas.py (BE-05)

## Keys inside free-form fields

`schemas.py` types these fields as `dict` or `list[dict]`. The keys below are what the BE-06 mocks
serve and what the frontend builds against, so the real tasks must return the **same keys**.
Changing them is a contract change (rule 3).

The table records intended inline keys. Known current implementation gaps are listed
below; documenting a gap does not approve dropping a field or adding a new one.

| Field | Keys | Real values come from |
|---|---|---|
| `MetaOut.materials[]` | `name`, `fuel_type`, `n_tests`, `is_synthetic` | BE-07 (unified test table) |
| `MetaOut.ranges` | `{feature: {min, max, is_synthetic}}` for `o2_pct`, `pressure_kpa`, `flow_cm_s` | BE-07 from `ml/artifacts/feature_ranges.json` (ML-03) |
| `MetaOut.ranges_by_fuel_type` | `{fuel_type: {feature: {min, max, is_synthetic}}}`, same features | BE-07 from `feature_ranges.json` `"by_fuel_type"` (ML-03) |
| `MetaOut.investigations[]` | at least `name`, `pillar`, `objective`, `source_url`, `is_synthetic` (DAT-06 adds more) | BE-07 from `processed/investigations.json` (DAT-06) |
| `DetectOut.detectors[]` | `id`, `position` (`[x, y, z]`, metres), `peak_concentration`, `is_synthetic` | BE-03 detector service |
| `ResultsOut.rows[]` | `step` (`"simulate"`, `"detect"` or `"apply"`), `inputs`, `state`, `probability`, `trust`, `detection_s`, `action`, `sources` | BE-01 store via BE-08 |
| `ChatOut.citations[]` | `title`, `investigation`, `source_url`, `snippet`, `is_synthetic` | ML-07 chat answerer |

- `ranges` uses the training feature names: `flow_cm_s`, while the request field is `flow_speed_cm_s`.
- ML-03 saves min/max per feature **and per fuel_type**; BE-07 serves the `"overall"` section
  (see the BE-07 section below).
- `is_synthetic` is `true` for placeholder values; real NASA-derived values set `false`.
- Results rows always contain the eight table keys. For detect rows, `state`,
  `probability`, `trust` and `action` are null; `inputs` is the current snapshot and
  `sources` carries the latest verdict's IDs. `detection_s` may also be null if nothing
  is detected. Null does not mean the keys are omitted.
- Results rows follow the real store (`services/store.py`): `step` is the step's name, `sources`
  is a list of `test_id` strings. Nulls indicate values that the step did not produce,
  as described above. The BE-06 mocks are checked against the real store, row for row.
- **Open (Nergis + Nathan, rule 5):** an id string carries no `is_synthetic`, so the results
  table can't badge synthetic sources from a row alone. Today the ids show it by convention only
  (seed ids start with `SYN-`, mock ids with `synthetic-`). This naming convention is
  not a general provenance guarantee. Options: store full `TestRef` dicts in
  `sources`, or add an `is_synthetic` key to each row. Either is a contract change (rule 3).

- **Known inline provenance gaps:** real `rag._citation()` currently returns title,
  investigation, URL and snippet without `is_synthetic`; mock citations include it.
  Real detector dictionaries include `time_s` but do not include `is_synthetic`, while
  mocks carry the synthetic flag. These free-form outputs need a coordinated team
  decision; the table above is not proof that every producer supplies every key.
  See `docs/DECISIONS.md` for owners and affected consumers.

## 3D coordinate system (frontend and backend)

One frame for the 3D scene (`frontend/src/scene/`) and the detector service (BE-03,
`ml/pipeline/config.py` `DETECTORS`). Everything is in metres, in the ISS lab module.

| | Value |
|---|---|
| Origin `(0, 0, 0)` | Centre of the module: 8.5 m long along x, 4.2 m across |
| `+x` | **Fore**, the forward airflow direction: `ScenarioIn.flow_dir` defaults to `(1, 0, 0)` |
| `+y` | Overhead (deck is `-y`) |
| `+z` | Port (starboard is `-z`) |
| Fire position | Always `(0, 0, 0)`. `ScenarioIn` has no position field, so the fire starts at the module centre. |

**Vent detectors.** These keep BE-03's x and z, but move each vent onto the overhead rack face. The
overhead racks fill y ≈ 1.38–1.93 m, so y = 1.5 is inside a rack and y = 2.0 is behind it, and a
marker there is hidden. y = 1.37 sits on the rack face, inside the open aisle (|y|, |z| < 1.38).

| id | position `[x, y, z]` | where |
|---|---|---|
| `vent_fwd` | `[4.0, 1.37, 0.0]` | overhead, fore end |
| `vent_aft` | `[-4.0, 1.37, 0.0]` | overhead, aft end |
| `vent_mid` | `[0.0, 1.37, 0.0]` | overhead, above the fire |

- **Aligned on current main:** `ml/pipeline/config.py` and the frontend's
  `src/lab/config.js` now use the table above. Earlier swapped end names and different
  heights are historical (fixed during integration, `b000eca`).
- The frontend draws detectors only where `DetectOut.detectors` puts them (FE-04). The alarm
  follows `time_to_detect_s` (FE-06), so particles never decide which vent trips. Detector
  geometry affects detection times as well as visualization; the burn predictor is separate.
- Changing an axis, the fire position or a vent is a contract change (rule 3): update this table,
  BE-03's config and the frontend's `src/lab/config.js` together.

## GET /meta (BE-07): keys inside the free-form fields

| Field | Keys | Source |
|---|---|---|
| `materials[]` | `name`, `fuel_type`, `n_tests`, `is_synthetic` | one entry per (material, fuel_type) in `data/processed/tests.parquet` |
| `ranges` | `{feature: {min, max, is_synthetic}}` for `o2_pct`, `pressure_kpa`, `flow_cm_s` | the `"overall"` section of `ml/artifacts/feature_ranges.json` |
| `ranges_by_fuel_type` | `{fuel_type: {feature: {min, max, is_synthetic}}}`, same features | the `"by_fuel_type"` section of the same file |
| `investigations[]` | passed through from `data/processed/investigations.json` (DAT-06) | committed metadata; `[]` if absent |

- `ranges` uses training feature names (`flow_cm_s`); the request field is `flow_speed_cm_s`.
  The frontend's `testedRange()` already accepts either name.
- `is_synthetic` is `true` on a material if any of its tests is synthetic, and on every range if
  any table row is synthetic (the ranges are computed from the table).
- The predictor flags `extrapolated` against the material's own fuel type, so the UI shades
  `ranges_by_fuel_type[<the material's fuel_type>]` on its sliders and falls back to `ranges`
  only when that fuel type is missing. A fuel type's `is_synthetic` is `true` if any of its rows is.
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


## POST /preview (BE-05, added 2026-11-15)

`ScenarioIn` -> `PreviewOut {state, burn_probability, trust, extrapolated, is_synthetic, inputs}`.
The same prediction and `BURN_THRESHOLD` as `/simulate`, but **no scenario, no history row and no
explanation** (so no LLM call): it is fast and leaves `/results` untouched. For live views only:
the 3D scene while sliders move, and the O2 sweep chart. Recording a step still needs `/simulate`
or `/apply`. `is_synthetic` is `true` in mock mode (rule 5); non-finite inputs give 422 like
`/simulate`. Added because the O2 chart called `/simulate` once per point (7 scenarios and 7
explanations per Ignite/Apply).

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

## POST /suppress: order of `actions` (BE-04)

The contract used to say "sorted by score". The suppressor (BE-04) ranks by NASA data support first,
following the plan's BE-04 rules (`water_mist` has no PSI data and is "ranked last unless data is
added"; `cut_power` changes no input and has no data support):

1. Actions with `data_support` `"direct"` or `"indirect"`, highest `score` first.
2. Then actions with `data_support` `"none"`, highest `score` first, except `water_mist`, always last.

`recommended` is the first data-backed action (`cut_power` if none is backed). A no-data action can
therefore score higher yet appear lower; the UI should show the list in the given order and highlight
`recommended` by name. `frontend/src/api/types.ts` now documents this same ordering
(merged with FE-06). This is the implemented behavior, not a new approval of the ranking
assumptions. Any proposed policy change remains a team decision.


## Pending contract decisions

Input ranges and material catalog checks are not yet enforced as the proposed semantic
validation policy. `ScenarioIn` currently specifies types/defaults and the supported
module literal; it does not yet reject every physically invalid numeric value or unknown
material. Do not treat slider limits or training-data ranges as API validation.

`docs/DECISIONS.md` records proposed validation/error behavior, source provenance,
recorded PDF recommendations and optional new report/export APIs. None changes this
contract until the team agrees and schemas, frontend types, tests and changelog are
updated together. There is currently no `POST /report`, CSV/DOCX endpoint or agent_trace
field in the public API. Internal pipeline stages do not add public endpoints.
