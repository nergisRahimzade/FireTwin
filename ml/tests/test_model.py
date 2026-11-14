"""A1 / ML-01 to ML-05: physics-shaped model, feature ranges, nearest tests, trust."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from ml.pipeline import config, model, physics
from ml.pipeline.types import Scenario

BASE = Scenario(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def test_zero_flow_log_feature_is_finite() -> None:
    assert math.isfinite(float(physics.ln_flow(0.0)))
    assert float(physics.ln_flow(0.0)) == pytest.approx(math.log(config.U0_CM_S))
    df = pd.DataFrame(
        [{"o2_pct": 21.0, "pressure_kpa": 101.3, "flow_cm_s": 0.0, "fuel_type": "solid"}]
    )
    for variant in physics.VARIANTS:
        assert np.isfinite(physics.make_features(df, variant)).all()


def test_predict_zero_flow_does_not_crash() -> None:
    prob, spread, trust, extrapolated, nearest = model.predict(
        Scenario(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=0.0)
    )
    assert 0.0 <= prob <= 1.0
    assert trust in {"strong", "medium", "weak"}
    assert len(nearest) == config.NEAREST_K


def test_more_oxygen_means_more_likely_to_burn() -> None:
    low = model.burn_probability(Scenario("cable insulation", 15.0, 10.0))
    high = model.burn_probability(Scenario("cable insulation", 23.0, 10.0))
    assert high > low


def test_metrics_have_physics_and_baseline() -> None:
    metrics = json.loads(config.METRICS_PATH.read_text())
    assert metrics["n_rows"] > 0
    assert metrics["evaluation"] == "leave-one-investigation-out"
    for key in ("physics_model", "baseline_plain_logistic", "boundary_model_option_b"):
        assert "accuracy" in metrics[key]
    assert metrics["coefficient_check"]["u_shape_ok"] is True


def test_physics_params_saved_per_fuel_type() -> None:
    params = json.loads(config.PHYSICS_PARAMS_PATH.read_text())["by_fuel_type"]
    assert {"a", "u_star_cm_s", "c", "s"} <= set(params["solid"])


def test_extrapolated_inputs_give_weak_trust() -> None:
    _, _, trust, extrapolated, _ = model.predict(Scenario("cable insulation", 34.0, 10.0))
    assert extrapolated is True
    assert trust == "weak"


def test_in_range_inputs_are_not_extrapolated() -> None:
    assert model.is_extrapolated(BASE) is False


def test_nearest_tests_prefer_same_fuel_type() -> None:
    nearest = model.nearest_tests(BASE)
    assert [t.fuel_type for t in nearest] == ["solid"] * config.NEAREST_K


def test_unknown_material_is_extrapolated_not_a_crash() -> None:
    prob, _, trust, extrapolated, _ = model.predict(Scenario("unobtainium", 21.0, 10.0))
    assert extrapolated is True and trust == "weak"
    assert 0.0 <= prob <= 1.0


def _spread_rows(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    o2 = rng.uniform(16, 24, n)
    return pd.DataFrame(
        {
            "o2_pct": o2,
            "pressure_kpa": 101.3,
            "flow_cm_s": rng.uniform(0, 20, n),
            "fuel_type": "solid",
            "spread_rate_mm_s": 0.2 * o2,
        }
    )


def test_spread_model_is_none_with_fewer_than_15_rows() -> None:
    assert physics.fit_spread(_spread_rows(config.MIN_ROWS_SPREAD - 1), "physics") is None
    assert physics.predict_spread(None, _spread_rows(1), "physics") is None


def test_spread_model_fits_with_enough_rows() -> None:
    fitted = physics.fit_spread(_spread_rows(30), "physics")
    row = _spread_rows(1).assign(o2_pct=20.0)
    assert physics.predict_spread(fitted, row, "physics") == pytest.approx(4.0, abs=0.2)


def test_seed_data_has_no_spread_rates_so_spread_is_none() -> None:
    assert model.predict(BASE)[1] is None
