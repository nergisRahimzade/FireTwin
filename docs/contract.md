# API contract

Source of truth: backend/app/schemas.py (BE-05)

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
