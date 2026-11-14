"""Prediction tools: predict(), nearest_tests(), trust and extrapolation (ML-03 to ML-05).

Pure functions over the unified test table and the trained artifacts. No FastAPI imports.
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache

import joblib
import pandas as pd

from ml.pipeline import config, physics
from ml.pipeline.types import Scenario, TestRef

log = logging.getLogger(__name__)

DIST_FEATURES = ["o2_pct", "pressure_kpa", "flow_cm_s"]


@lru_cache(maxsize=1)
def load_table() -> pd.DataFrame:
    try:
        return pd.read_parquet(config.TESTS_PARQUET)
    except Exception:
        log.exception("load_table: cannot read %s (run `make data`)", config.TESTS_PARQUET)
        raise


@lru_cache(maxsize=1)
def load_model() -> dict:
    try:
        return joblib.load(config.MODEL_PATH)
    except Exception:
        log.exception("load_model: cannot read %s (run `make train`)", config.MODEL_PATH)
        raise


@lru_cache(maxsize=1)
def load_ranges() -> dict:
    try:
        return json.loads(config.RANGES_PATH.read_text())
    except Exception:
        log.exception("load_ranges: cannot read %s (run `make train`)", config.RANGES_PATH)
        raise


def fuel_type_of(material: str) -> str | None:
    """fuel_type for a material name from the table; None if the material is unknown."""
    table = load_table()
    match = table.loc[table["material"].str.lower() == material.lower(), "fuel_type"]
    return None if match.empty else str(match.iloc[0])


def _scenario_values(scenario: Scenario) -> dict:
    return {
        "o2_pct": scenario.o2_pct,
        "pressure_kpa": scenario.pressure_kpa,
        "flow_cm_s": scenario.flow_speed_cm_s,
    }


def is_extrapolated(scenario: Scenario) -> bool:
    """True when any input is outside the tested range for this fuel_type (or it is unknown)."""
    fuel = fuel_type_of(scenario.material)
    ranges = load_ranges()["by_fuel_type"].get(fuel) if fuel else None
    if ranges is None:
        return True
    return any(
        not (ranges[f]["min"] <= value <= ranges[f]["max"])
        for f, value in _scenario_values(scenario).items()
    )


def nearest_with_distance(scenario: Scenario, k: int = config.NEAREST_K) -> list[tuple]:
    """(TestRef, distance, same_fuel) for the k closest tests; same fuel_type comes first.

    Distance is Euclidean over (o2, pressure, flow), each scaled by its range in the table.
    """
    table = load_table().dropna(subset=DIST_FEATURES)
    if table.empty:
        return []
    values = _scenario_values(scenario)
    sq = 0.0
    for f in DIST_FEATURES:
        span = float(table[f].max() - table[f].min()) or 1.0
        sq = sq + ((table[f] - values[f]) / span) ** 2
    fuel = fuel_type_of(scenario.material)
    ranked = table.assign(_dist=sq**0.5, _same=table["fuel_type"] == fuel).sort_values(
        ["_same", "_dist"], ascending=[False, True]
    )
    out = []
    for row in ranked.head(k).to_dict("records"):
        ref = TestRef(
            test_id=row["test_id"],
            investigation=row["investigation"],
            fuel_type=row["fuel_type"],
            o2_pct=row["o2_pct"],
            pressure_kpa=row["pressure_kpa"],
            flow_cm_s=row["flow_cm_s"],
            outcome=row["outcome"],
            source_url=row["source_url"],
            is_synthetic=bool(row["is_synthetic"]),
        )
        out.append((ref, float(row["_dist"]), bool(row["_same"])))
    return out


def nearest_tests(scenario: Scenario, k: int = config.NEAREST_K) -> list[TestRef]:
    """ML-04: the k nearest NASA tests to the scenario."""
    return [ref for ref, _, _ in nearest_with_distance(scenario, k)]


def trust_level(scenario: Scenario) -> str:
    """strong = >=3 same-fuel tests within 0.15; medium = >=1 within 0.30; else weak."""
    near = nearest_with_distance(scenario, k=max(config.NEAREST_K, config.TRUST_STRONG_COUNT))
    dists = [d for _, d, same in near if same]
    if sum(d <= config.TRUST_STRONG_DIST for d in dists) >= config.TRUST_STRONG_COUNT:
        return "strong"
    if any(d <= config.TRUST_MEDIUM_DIST for d in dists):
        return "medium"
    return "weak"


def data_support(scenario: Scenario) -> str:
    """direct = a same-fuel test within the medium distance; indirect = same fuel only."""
    near = nearest_with_distance(scenario)
    same = [d for _, d, is_same in near if is_same]
    if any(d <= config.TRUST_MEDIUM_DIST for d in same):
        return "direct"
    return "indirect" if same else "none"


def burn_probability(scenario: Scenario) -> float:
    """P(fire keeps burning) from the physics-shaped model."""
    for name, value in _scenario_values(scenario).items():
        if value is None or not math.isfinite(value):
            raise ValueError(f"burn_probability: {name}={value!r} is not a finite number")
    try:
        bundle = load_model()
        row = pd.DataFrame(
            [{**_scenario_values(scenario), "fuel_type": fuel_type_of(scenario.material)}]
        )
        return float(physics.predict_logistic(bundle["model"], row, bundle["variant"])[0])
    except Exception:
        log.exception("burn_probability failed for scenario=%s", scenario)
        raise


def spread_rate(scenario: Scenario) -> float | None:
    """ML-02: predicted spread rate in mm/s; None when too few tests report one."""
    try:
        bundle = load_model()
        row = pd.DataFrame(
            [{**_scenario_values(scenario), "fuel_type": fuel_type_of(scenario.material)}]
        )
        return physics.predict_spread(bundle.get("spread_model"), row, bundle["variant"])
    except Exception:
        log.exception("spread_rate failed for scenario=%s", scenario)
        raise


def predict(inputs: Scenario) -> tuple[float, float | None, str, bool, list[TestRef]]:
    """ML-05: (prob, spread, trust, extrapolated, nearest). Spread is None without ML-02 data."""
    extrapolated = is_extrapolated(inputs)
    trust = "weak" if extrapolated else trust_level(inputs)
    prob = burn_probability(inputs)
    return prob, spread_rate(inputs), trust, extrapolated, nearest_tests(inputs)
