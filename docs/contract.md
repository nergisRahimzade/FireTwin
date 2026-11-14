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
