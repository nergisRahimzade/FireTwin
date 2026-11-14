"""Predictor service (ML-05): the burn model behind /simulate, /apply and /suppress.

A thin adapter: it turns the API's ScenarioIn into the ML layer's Scenario, calls the model in
ml/pipeline/model.py, and turns the nearest tests back into the contract's TestRef.
Pure functions, no FastAPI imports.
"""

from __future__ import annotations

import logging
import math

from app.schemas import ScenarioIn, TestRef
from ml.pipeline import model
from ml.pipeline.types import Scenario
from ml.pipeline.types import TestRef as MlTestRef

log = logging.getLogger(__name__)


def to_scenario(inputs: ScenarioIn) -> Scenario:
    """API request model -> the ML layer's frozen Scenario."""
    return Scenario(
        material=inputs.material,
        o2_pct=inputs.o2_pct,
        flow_speed_cm_s=inputs.flow_speed_cm_s,
        pressure_kpa=inputs.pressure_kpa,
        flow_dir=tuple(inputs.flow_dir),
        module=inputs.module,
    )


def _number(value: float | None) -> float | None:
    """NaN (pandas' "missing") -> None, so the JSON says null instead of NaN."""
    return None if value is None or not math.isfinite(value) else float(value)


def to_test_ref(ref: MlTestRef) -> TestRef:
    """ML-layer test row -> the contract's TestRef."""
    return TestRef(
        test_id=str(ref.test_id),
        investigation=str(ref.investigation),
        fuel_type=str(ref.fuel_type),
        o2_pct=_number(ref.o2_pct),
        pressure_kpa=_number(ref.pressure_kpa),
        flow_cm_s=_number(ref.flow_cm_s),
        outcome=ref.outcome if ref.outcome in ("burned", "extinguished") else "unknown",
        source_url=str(ref.source_url),
        is_synthetic=bool(ref.is_synthetic),
    )


def predict(inputs: ScenarioIn) -> tuple[float, float | None, str, bool, list[TestRef]]:
    """Return (prob, spread, trust, extrapolated, nearest) for one scenario.

    prob = P(fire keeps burning), spread = mm/s or None, trust = strong|medium|weak,
    extrapolated = any input is outside the tested range, nearest = top 3 NASA tests.
    """
    try:
        prob, spread, trust, extrapolated, nearest = model.predict(to_scenario(inputs))
        return prob, spread, trust, extrapolated, [to_test_ref(ref) for ref in nearest]
    except Exception:
        log.exception("predictor.predict failed for inputs=%s", inputs)
        raise
