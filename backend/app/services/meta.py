"""Data behind GET /meta (BE-07): materials, tested ranges and investigations for the UI controls.

- materials + n_tests: counted from the unified test table (data/processed/tests.parquet).
- ranges: the "overall" min/max from ml/artifacts/feature_ranges.json (every fuel type together).
- ranges_by_fuel_type: the same file's "by_fuel_type" section. The predictor flags `extrapolated`
  against the material's own fuel_type, so the UI shades these on the sliders; that way the
  shaded band and the "outside tested range" warning always agree.
- investigations: data/processed/investigations.json (DAT-06) once it exists; until then an empty
  list, never made-up summaries.

Plain Python: no FastAPI imports (rule 4). The router turns MetaUnavailableError into HTTP 503.
"""

import json
import logging

import pandas as pd

from app.schemas import MetaOut
from ml.pipeline import config, model

log = logging.getLogger(__name__)

# Written by DAT-06; missing is normal until then.
INVESTIGATIONS_PATH = config.ROOT / "data" / "processed" / "investigations.json"
# The features the UI shades on its sliders. Names are the training ones: flow_cm_s, not the
# request's flow_speed_cm_s (the frontend maps between the two).
RANGE_FEATURES = ("o2_pct", "pressure_kpa", "flow_cm_s")


class MetaUnavailableError(RuntimeError):
    """The test table or ranges file is missing or malformed, so /meta can't be built honestly."""


def build_meta() -> MetaOut:
    """Assemble MetaOut from the table, the ranges file and (if present) investigations.json."""
    try:
        table = model.load_table()
        ranges_file = model.load_ranges()
    except Exception as exc:  # the loaders already logged the full error
        raise MetaUnavailableError(
            "test table or feature ranges not available: run `make data` and `make train`"
        ) from exc
    # feature_ranges.json doesn't record where its numbers came from, but it is computed from this
    # table: if any row is synthetic, the ranges are too (rule 5: label it, don't hide it).
    ranges_synthetic = bool(table["is_synthetic"].any())
    return MetaOut(
        materials=_materials(table),
        ranges=_ranges(ranges_file.get("overall"), "overall", ranges_synthetic),
        ranges_by_fuel_type=_ranges_by_fuel_type(ranges_file, table),
        investigations=_investigations(),
    )


def _materials(table: pd.DataFrame) -> list[dict]:
    # One entry per (material, fuel_type); rows without a material name can't be chosen in the UI.
    groups = table.dropna(subset=["material"]).groupby(["material", "fuel_type"], sort=True)
    return [
        {
            # int()/bool(): pandas gives numpy numbers, which the JSON encoder can't handle.
            "name": str(name),
            "fuel_type": str(fuel_type),
            "n_tests": int(len(rows)),
            # True if any test behind this material is synthetic, so the UI shows the badge.
            "is_synthetic": bool(rows["is_synthetic"].any()),
        }
        for (name, fuel_type), rows in groups
    ]


def _ranges(section: object, where: str, is_synthetic: bool) -> dict:
    """{feature: {min, max, is_synthetic}} from one section of feature_ranges.json.

    `where` names the section ("overall", or "by_fuel_type.solid") in the error messages.
    """
    if not isinstance(section, dict):
        raise MetaUnavailableError(
            f"feature_ranges.json has no {where!r} section: run `make train`"
        )
    ranges = {}
    for feature in RANGE_FEATURES:
        entry = section.get(feature)
        # Fail loudly: a missing or broken range would silently remove the slider's tested band.
        if not isinstance(entry, dict) or entry.get("min") is None or entry.get("max") is None:
            raise MetaUnavailableError(
                f"feature_ranges.json has no min/max for {feature!r} ({where})"
            )
        ranges[feature] = {
            "min": float(entry["min"]),
            "max": float(entry["max"]),
            "is_synthetic": is_synthetic,
        }
    return ranges


def _ranges_by_fuel_type(ranges_file: dict, table: pd.DataFrame) -> dict:
    """{fuel_type: ranges} for every fuel type in the ranges file.

    A fuel type missing here (e.g. a new material before `make train`) is simply absent: the
    predictor then calls every input extrapolated, and the UI falls back to the overall band.
    """
    by_fuel = ranges_file.get("by_fuel_type", {})
    if not isinstance(by_fuel, dict):
        raise MetaUnavailableError("feature_ranges.json 'by_fuel_type' must be an object")
    return {
        # Synthetic if any test of that fuel type is (rule 5), same as the overall section.
        str(fuel): _ranges(
            section,
            f"by_fuel_type.{fuel}",
            bool(table.loc[table["fuel_type"] == fuel, "is_synthetic"].any()),
        )
        for fuel, section in by_fuel.items()
    }


def _investigations() -> list[dict]:
    # No DAT-06 file yet: return [] rather than invent investigation summaries.
    if not INVESTIGATIONS_PATH.is_file():
        return []
    try:
        data = json.loads(INVESTIGATIONS_PATH.read_text())
    except (OSError, ValueError) as exc:
        raise MetaUnavailableError(f"cannot read {INVESTIGATIONS_PATH.name}: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise MetaUnavailableError(f"{INVESTIGATIONS_PATH.name} must be a JSON list of objects")
    return data
