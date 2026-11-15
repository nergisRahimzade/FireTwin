"""Build data/processed/investigations.json (DAT-06): one summary per NASA investigation.

Every value is taken from a file in the repo, never typed in from memory:
- conditions ranges and fuels: the unified table (data/processed/tests.parquet);
- objective: the "Objectives" section of the PSI description in data/docs/<investigation>/;
- hardware, sample geometry and the air-flow range of investigations that have no rows in the
  unified table: their PSI experiment table in data/raw/, when that file is present.
A field with no source in the repo is null and is listed under "missing", so the gap is visible.

Not named clean_*.py on purpose: `make data` runs those; run this one by hand after it.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from pathlib import Path

import pandas as pd

log = logging.getLogger("build_investigations")

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "data" / "processed" / "tests.parquet"
DOCS_DIR = ROOT / "data" / "docs"
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "investigations.json"
PSI_PAGE = "https://psi.nasa.gov/physci/repo/data/investigations/{id}"

# name -> (pillar, PSI id, raw experiment-table file, flow column, material column).
# The pillar is the team's own classification into NASA's three fire-safety pillars.
INVESTIGATIONS = {
    "BASS": (
        "prevention",
        "PSI-26",
        "PSI-26_Experimental table_BASS.csv",
        None,
        "Fuel Sample Material",
    ),
    "BASS-II": ("prevention", "PSI-25", "PSI-25_Experimental table_BASS-II.csv", None, None),
    "Saffire-I": (
        "prevention",
        "PSI-98",
        "PSI-98_Experimental table_SAFFIRE-1.csv",
        "Air Flow (cm/s)",
        "Material",
    ),
    "Saffire-II": ("prevention", "PSI-99", "PSI-99_Experimental table_SAFFIRE-2.csv", None, None),
    "Saffire-III": (
        "prevention",
        "PSI-100",
        "PSI-100_Experimental table_SAFFIRE-3.csv",
        "Air Flow",
        "Material",
    ),
    "FLEX": ("suppression", "PSI-69", "PSI-69_Experimental table_FLEX.csv", None, None),
    "FLEX-2": ("suppression", "PSI-68", "PSI-68_Experimental table_Flex2.csv", None, None),
    "SAME": (
        "detection",
        "PSI-102",
        "PSI-102_Experimental table_SAME.csv",
        "Air Flow (cm/s)",
        "Sample Material",
    ),
    "SAME-R": (
        "detection",
        "PSI-101",
        "PSI-101_Experimental table_SAME-R.csv",
        "Inlet velocity (cm/s)",
        "Sample Type",
    ),
}


def _span(values: pd.Series) -> dict | None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return None if values.empty else {"min": float(values.min()), "max": float(values.max())}


def objective_from_doc(name: str, docs_dir: Path = DOCS_DIR) -> str | None:
    """The first paragraph under the "Objectives" heading of the investigation's PSI text."""
    for path in sorted((docs_dir / name).glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^Objectives?\s*\n+(.+?)(?:\n\s*\n|\Z)", text, flags=re.M | re.S)
        if match:
            return " ".join(match.group(1).split())
    return None


def raw_table_facts(file_name: str, flow_col: str | None, material_col: str | None) -> dict:
    """Row count, materials and air-flow range read straight from a PSI experiment table."""
    path = RAW_DIR / file_name
    if not path.exists():
        return {}
    try:
        data = path.read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")  # some PSI tables are saved in the Windows code page
        reader = csv.reader(io.StringIO(text, newline=""))
        header = [" ".join(h.split()) for h in next(reader)]
        rows = [dict(zip(header, (c.strip() for c in row), strict=False)) for row in reader]
    except Exception:
        log.exception("raw_table_facts: cannot read %s", path)
        raise
    facts: dict = {"n_table_rows": len(rows), "table_columns": header}
    if material_col in header:
        facts["materials"] = sorted({r[material_col] for r in rows if r.get(material_col)})
    if flow_col in header:
        speeds = [float(n) for r in rows for n in re.findall(r"\d*\.\d+|\d+", r.get(flow_col, ""))]
        if speeds:
            facts["flow_cm_s"] = {"min": min(speeds), "max": max(speeds)}
    return facts


def build(table_path: Path = TABLE) -> list[dict]:
    table = pd.read_parquet(table_path)
    out = []
    for name, (pillar, psi_id, raw_file, flow_col, material_col) in INVESTIGATIONS.items():
        rows = table[table["investigation"] == name]
        raw = raw_table_facts(raw_file, flow_col, material_col)
        in_table = not rows.empty
        entry = {
            "name": name,
            "pillar": pillar,
            "objective": objective_from_doc(name),
            "fuel": sorted(rows["fuel_type"].dropna().unique()) if in_table else None,
            "materials": sorted(rows["material"].dropna().unique())
            if in_table
            else raw.get("materials"),
            "sample_geometry": None,
            "hardware": sorted(rows["hardware"].dropna().unique()) if in_table else None,
            "conditions": {
                "o2_pct": _span(rows["o2_pct"]) if in_table else None,
                "pressure_kpa": _span(rows["pressure_kpa"]) if in_table else None,
                "flow_cm_s": _span(rows["flow_cm_s"]) if in_table else raw.get("flow_cm_s"),
            },
            "sensors": None,
            "n_tests_in_unified_table": int(len(rows)),
            "n_rows_in_psi_table": raw.get("n_table_rows"),
            "psi_table_columns": raw.get("table_columns"),
            "source_url": PSI_PAGE.format(id=psi_id),
            "is_synthetic": bool(rows["is_synthetic"].any()) if in_table else False,
        }
        entry["missing"] = sorted(
            key
            for key in ("objective", "fuel", "sample_geometry", "hardware", "sensors")
            if entry[key] is None
        )
        out.append(entry)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    entries = build()
    OUT.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    for e in entries:
        log.info(
            "%s: %d unified rows, missing=%s",
            e["name"],
            e["n_tests_in_unified_table"],
            e["missing"],
        )


if __name__ == "__main__":
    main()
