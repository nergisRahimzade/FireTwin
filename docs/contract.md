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
| `ResultsOut.rows[]` | `step` (1, 2, 3, ...), `inputs`, `state`, `probability`, `trust`, `detection_s`, `action`, `sources` | BE-01 store via BE-08 |
| `ChatOut.citations[]` | `title`, `investigation`, `source_url`, `snippet`, `is_synthetic` | ML-07 chat answerer |

- `ranges` uses the training feature names: `flow_cm_s`, while the request field is `flow_speed_cm_s`.
- **Open (Nergis + Ryan):** ML-03 saves min/max per feature **and per fuel_type**; BE-07 must turn
  that into the flat shape above (overall range, or the selected material's fuel type).
- `is_synthetic` is `true` for placeholder values; real NASA-derived values set `false`.
- Results rows: `None` means the step didn't produce that value (a detect row has only
  `detection_s`). Rows have no flag of their own: a row counts as synthetic when any of its
  `sources` has `is_synthetic=true`, and the frontend shows the badge for it (rule 5).
  So every row, detect rows included, carries the sources behind the current verdict.
