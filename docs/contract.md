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
