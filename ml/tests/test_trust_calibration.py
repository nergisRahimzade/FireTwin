"""ML-04: "strong" trust is given only when the calibration earned it at some distance."""

import json

import pytest

from ml import calibrate_trust
from ml.pipeline import config, model
from ml.pipeline.types import Scenario

PMMA_ROD = Scenario(material="PMMA rod", o2_pct=21.0, flow_speed_cm_s=10.0)


@pytest.fixture
def calibration_file(tmp_path, monkeypatch):
    """Point the model at a calibration file written by the test."""

    def write(data: dict) -> None:
        path = tmp_path / "trust_calibration.json"
        path.write_text(json.dumps(data))
        monkeypatch.setattr(config, "TRUST_CALIBRATION_PATH", path)
        model.trust_thresholds.cache_clear()

    yield write
    model.trust_thresholds.cache_clear()


def test_uncalibrated_strong_distance_means_no_strong_threshold(calibration_file) -> None:
    calibration_file(
        {
            "strong_distance": None,
            "medium_distance": 0.02,
            "calibrated": {"strong": False, "medium": True},
        }
    )
    assert model.trust_thresholds() == (None, 0.02)


def test_an_old_file_that_says_strong_failed_is_not_trusted(calibration_file) -> None:
    # Files written before this fix kept a number even though "strong" was not calibrated.
    calibration_file(
        {
            "strong_distance": 0.02,
            "medium_distance": 0.02,
            "calibrated": {"strong": False, "medium": True},
        }
    )
    assert model.trust_thresholds()[0] is None


def test_a_calibrated_strong_distance_is_used(calibration_file) -> None:
    calibration_file(
        {
            "strong_distance": 0.05,
            "medium_distance": 0.1,
            "calibrated": {"strong": True, "medium": True},
        }
    )
    assert model.trust_thresholds() == (0.05, 0.1)


def test_without_a_strong_distance_trust_is_never_strong(real_artifacts, calibration_file) -> None:
    calibration_file(
        {
            "strong_distance": 10.0,  # would accept any test if it were used
            "medium_distance": 10.0,
            "calibrated": {"strong": True, "medium": True},
        }
    )
    assert model.trust_level(PMMA_ROD) == "strong"  # the real solid model has skill
    calibration_file(
        {
            "strong_distance": None,
            "medium_distance": 10.0,
            "calibrated": {"strong": False, "medium": True},
        }
    )
    assert model.trust_level(PMMA_ROD) == "medium"


def test_committed_calibration_matches_what_calibrate_produces(real_artifacts) -> None:
    fresh = calibrate_trust.calibrate()
    committed = json.loads(config.TRUST_CALIBRATION_PATH.read_text())
    assert fresh["strong_distance"] == committed["strong_distance"]
    assert fresh["medium_distance"] == committed["medium_distance"]
    # A strong distance exists exactly when the strong accuracy target was met.
    assert (committed["strong_distance"] is None) == (not committed["calibrated"]["strong"])
