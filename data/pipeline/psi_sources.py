"""The NASA PSI experiment tables the pipeline uses, and helpers shared by the pipeline scripts.

Not named clean_*.py on purpose: `make data` runs every data/pipeline/clean_*.py as a script.
Standard library only, so the pipeline runs before any layer adds pandas to pyproject.toml.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"

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
    Source("BASS-II", "PSI-25", "PSI-25_Experimental table_BASS-II.csv"),
    Source("Saffire-II", "PSI-99", "PSI-99_Experimental table_SAFFIRE-2.csv"),
    Source(
        "Saffire-III",
        None,
        "Saffire-III_Experimental table.csv",
        note="no PSI study id found for Saffire-III yet",
    ),
    Source("FLEX", "PSI-69", "PSI-69_Experimental table_FLEX.csv"),
    # FLEX-2's table is a matrix of test conditions per fuel (ranges such as "0.17; 0.21"),
    # not one row per test, so it is downloaded but not cleaned into test rows.
    Source("FLEX-2", "PSI-68", "PSI-68_Experimental table_Flex2.csv"),
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


def numbers_in(text: object) -> list[float]:
    """Every number written in a cell: '~ 21.5' -> [21.5], '22.1 to 22.0' -> [22.1, 22.0].
    A leading dot counts ('.5' -> 0.5), as the PSI tables often drop the zero."""
    return [float(n) for n in re.findall(r"\d*\.\d+|\d+", str(text or ""))]


def first_number(text: object) -> float | None:
    found = numbers_in(text)
    return found[0] if found else None


def read_rows(path: Path) -> list[dict[str, str]]:
    """Rows of a PSI CSV with tidy headers (runs of spaces collapsed; PSI's BOM removed)."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
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
