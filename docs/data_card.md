# Data card (DAT-09)

All numbers below were counted from `data/processed/tests.parquet` (412 rows, none synthetic).
Rebuild with `make data`, then `python data/pipeline/build_investigations.py`.

## Sources
NASA Physical Sciences Informatics (PSI), https://psi.nasa.gov. Each row's `source_url` is the
PSI investigation page. NASA data is public domain; check PSI's terms before redistributing the
raw tables. Raw tables stay out of Git (`data/raw/`).

## Rows per investigation
| Investigation | Rows | burned | extinguished | unknown | Notes |
|---|---|---|---|---|---|
| BASS-II | 129 | 0 | 27 | 102 | solids; no pressure recorded |
| FLEX | 274 | 27 | 186 | 61 | droplets (heptane, methanol); flow is always 0 |
| Saffire-II | 9 | 0 | 0 | 9 | solids; no pressure, no single outcome per sample |

In the model: 220 rows have a known outcome and complete inputs (7 BASS-II, 213 FLEX).
Not in the unified table (no per-test rows): BASS, Saffire-I, Saffire-III, FLEX-2, SAME, SAME-R.
They feed `investigations.json` and the chat documents only.

## Known gaps
- **No solid test is labeled "burned".** The model sees solids only as extinguished, so it
  predicts "goes out" for every solid fuel. Fix: label the BASS-II rows (DAT-02).
- **Solids have no recorded pressure.** The model assumes 101.3 kPa (`NOMINAL_PRESSURE_KPA`).
- **No spread rates** anywhere, so the spread model (ML-02) returns null.
- **Droplet flow is always 0 cm/s**, so airflow effects are learned from solids only.
- **No partial-gravity data**, no water-mist data, and no solid test above 22.2 % O2, so
  Moon-base oxygen levels are always flagged as extrapolated.
- **Crew risk, detector layout and diffusion values are team assumptions**, not NASA data.
- `data/docs` holds PSI description pages only (4 investigations); SAME, SAME-R, BASS and the
  Saffire-I/III pages are summarized from their tables in `investigations.json`.
