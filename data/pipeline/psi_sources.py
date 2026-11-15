"""The NASA PSI experiment tables the pipeline uses, and helpers shared by the pipeline scripts.

Not named clean_*.py on purpose: `make data` runs every data/pipeline/clean_*.py as a script.
Standard library only, so the pipeline runs before any layer adds pandas to pyproject.toml.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The experiment tables, tracked in Git (see .gitignore). data/raw/ is only for local uploads.
RAW_DIR = ROOT / "data" / "psi_tables"
CLEAN_DIR = ROOT / "data" / "clean"
OTHER_DIR = CLEAN_DIR / "other"  # cleaned tables that are not burn tests (detection, FLEX-2)

PSI_PAGE = "https://psi.nasa.gov/physci/repo/data/investigations/{id}"
# The study API the PSI site itself calls. It refuses requests without a signed-in session.
PSI_API = "https://psi.nasa.gov/geode-py/ws/studies/{id}"


@dataclass(frozen=True)
class Source:
    name: str  # investigation, as written in the unified table
    psi_id: str | None  # None = no PSI study found yet
    file_name: str  # the file name PSI gives the experiment table
    note: str = ""

    @property
    def page_url(self) -> str:
        return PSI_PAGE.format(id=self.psi_id) if self.psi_id else ""

    @property
    def api_url(self) -> str:
        return PSI_API.format(id=self.psi_id) if self.psi_id else ""

    @property
    def raw_path(self) -> Path:
        return RAW_DIR / self.file_name


SOURCES = [
    Source(
        "BASS",
        "PSI-26",
        "PSI-26_Experimental table_BASS.csv",
        note="table lists only the fuel samples: no O2, flow or outcome columns",
    ),
    Source("BASS-II", "PSI-25", "PSI-25_Experimental table_BASS-II.csv"),
    Source("Saffire-I", "PSI-98", "PSI-98_Experimental table_SAFFIRE-1.csv"),
    Source("Saffire-II", "PSI-99", "PSI-99_Experimental table_SAFFIRE-2.csv"),
    Source(
        "Saffire-III",
        "PSI-100",
        "PSI-100_Experimental table_SAFFIRE-3.csv",
        note="two samples, no O2 and no outcome recorded",
    ),
    Source("FLEX", "PSI-69", "PSI-69_Experimental table_FLEX.csv"),
    # FLEX-2's table is a matrix of test conditions per fuel (ranges such as "0.17; 0.21"),
    # not one row per test, so it is cleaned into data/clean/other/flex2_conditions.csv.
    Source("FLEX-2", "PSI-68", "PSI-68_Experimental table_Flex2.csv"),
    # Smoke-detection studies: aging/weight-loss measurements, not fire outcomes. They are cleaned
    # into data/clean/other/ and stay out of the burn-model table.
    Source("SAME", "PSI-102", "PSI-102_Experimental table_SAME.csv"),
    Source("SAME-R", "PSI-101", "PSI-101_Experimental table_SAME-R.csv"),
]
BY_NAME = {s.name: s for s in SOURCES}

# The unified-table columns (DAT-03, data/pipeline/build_table.py). Every clean CSV has these.
COLUMNS = [
    "test_id",
    "investigation",
    "fuel_type",
    "material",
    "hardware",
    "o2_pct",
    "pressure_kpa",
    "flow_cm_s",
    "outcome",
    "spread_rate_mm_s",
    "source_url",
    "is_synthetic",
]

MMHG_TO_KPA = 0.133322
ATM_TO_KPA = 101.325
PSI_TO_KPA = 6.894757


# DAT-05 unit rules: pressure -> kPa, airflow -> cm/s.
# (Mole fraction x 100 -> O2 % happens in clean_flex.py.)
PRESSURE_TO_KPA = {"kpa": 1.0, "psi": PSI_TO_KPA, "mmhg": MMHG_TO_KPA, "atm": ATM_TO_KPA}
FLOW_TO_CM_S = {"cm/s": 1.0, "mm/s": 0.1, "m/s": 100.0}


def to_kpa(value: float | None, unit: str) -> float | None:
    """Pressure in kPa from psi, mmHg, atm or kPa. Raises on an unknown unit."""
    factor = PRESSURE_TO_KPA.get(unit.strip().lower())
    if factor is None:
        raise ValueError(f"unknown pressure unit {unit!r}")
    return None if value is None else value * factor


def to_cm_s(value: float | None, unit: str) -> float | None:
    """Airflow in cm/s from cm/s, mm/s or m/s. Raises on an unknown unit."""
    factor = FLOW_TO_CM_S.get(unit.strip().lower())
    if factor is None:
        raise ValueError(f"unknown flow unit {unit!r}")
    return None if value is None else value * factor


def flow_cm_s(text: object) -> float | None:
    """'20 cm/s' -> 20.0, '5 mm/s' -> 0.5. A bare number is taken as cm/s."""
    value = first_number(text)
    unit = re.search(r"(cm/s|mm/s|m/s)", str(text or "").lower())
    return to_cm_s(value, unit.group(1) if unit else "cm/s")


def numbers_in(text: object) -> list[float]:
    """Every number written in a cell: '~ 21.5' -> [21.5], '22.1 to 22.0' -> [22.1, 22.0].
    A leading dot counts ('.5' -> 0.5), as the PSI tables often drop the zero."""
    return [float(n) for n in re.findall(r"\d*\.\d+|\d+", str(text or ""))]


def first_number(text: object) -> float | None:
    found = numbers_in(text)
    return found[0] if found else None


def read_text(path: Path) -> str:
    """File text as UTF-8 (BOM removed); tables saved in the Windows code page fall back to it."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_rows(path: Path) -> list[dict[str, str]]:
    """Rows of a PSI CSV with tidy headers (runs of spaces collapsed; PSI's BOM removed)."""
    reader = csv.reader(io.StringIO(read_text(path), newline=""))
    header = [" ".join(h.split()) for h in next(reader)]
    return [dict(zip(header, (c.strip() for c in row), strict=False)) for row in reader]


def write_clean(rows: list[dict], path: Path) -> Path:
    """Write rows in the unified-table column order. None becomes an empty cell."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: ("" if row.get(c) is None else row[c]) for c in COLUMNS})
    return path


def rounded(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)
