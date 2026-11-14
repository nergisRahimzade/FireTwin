"""ML-05: predictor service returns (prob, spread, trust, extrapolated, nearest)."""

import inspect

import pytest

from app.schemas import ScenarioIn, TestRef
from app.services import predictor

BASE = ScenarioIn(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def test_predict_returns_the_five_values() -> None:
    prob, spread, trust, extrapolated, nearest = predictor.predict(BASE)
    assert 0.0 <= prob <= 1.0
    assert spread is None or spread >= 0.0
    assert trust in {"strong", "medium", "weak"}
    assert extrapolated is False
    assert len(nearest) == 3
    assert all(isinstance(ref, TestRef) for ref in nearest)


def test_predict_signature_is_predict_inputs() -> None:
    assert list(inspect.signature(predictor.predict).parameters) == ["inputs"]


def test_zero_flow_does_not_crash() -> None:
    prob, *_ = predictor.predict(BASE.model_copy(update={"flow_speed_cm_s": 0.0}))
    assert 0.0 <= prob <= 1.0


def test_outside_tested_range_is_extrapolated_with_weak_trust() -> None:
    _, _, trust, extrapolated, _ = predictor.predict(BASE.model_copy(update={"o2_pct": 34.0}))
    assert extrapolated is True
    assert trust == "weak"


def test_non_finite_input_raises_a_clear_error() -> None:
    with pytest.raises(ValueError, match="o2_pct"):
        predictor.predict(BASE.model_copy(update={"o2_pct": float("nan")}))


def test_services_do_not_import_fastapi() -> None:
    assert "fastapi" not in inspect.getsource(predictor)
