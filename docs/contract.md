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
- Results rows: `None` means the step didn't produce that value (a detect row has only
  `detection_s`). Rows have no flag of their own: a row counts as synthetic when any of its
  `sources` has `is_synthetic=true`, and the frontend shows the badge for it (rule 5).
  So every row, detect rows included, carries the sources behind the current verdict.
- Results rows follow the real store (`services/store.py`): `step` is the step's name, `sources`
  is a list of `test_id` strings, and `None` means the step didn't produce that value (a detect
  row has only `detection_s`). The BE-06 mocks are checked against the real store, row for row.
- **Open (Nergis + Nathan, rule 5):** an id string carries no `is_synthetic`, so the results
  table can't badge synthetic sources from a row alone. Today the ids show it by convention only
  (seed ids start with `SYN-`, mock ids with `synthetic-`). Options: store full `TestRef` dicts in
  `sources`, or add an `is_synthetic` key to each row. Either is a contract change (rule 3).

## GET /meta (BE-07): keys inside the free-form fields

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

- **Backend follow-up (Nergis, BE-03):** `ml/pipeline/config.py` still has `vent_aft` at
  `(4.0, 1.5, 0)`, `vent_fwd` at `(-4.0, 1.5, 0)` and `vent_mid` at `(0, 2.0, 0)`. With `+x` = fore,
  the two end names swap. Updating `DETECTORS` to the table above also changes the
  `time_to_detect_s` values its tests expect.
- The frontend draws detectors only where `DetectOut.detectors` puts them (FE-04). The alarm
  follows `time_to_detect_s` (FE-06), so particles never decide which vent trips. A wrong position
  is a visual bug, not a wrong verdict.
- Changing an axis, the fire position or a vent is a contract change (rule 3): update this table,
  BE-03's config and the frontend's `src/lab/config.js` together.

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
