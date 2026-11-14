"""BE-04: suppressor service (action effects, scoring, ranking)."""

import pytest

from app.schemas import ScenarioIn, SuppressOut
from app.services import suppressor
from ml.pipeline import config

BASE = ScenarioIn(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def _by_action(inputs: ScenarioIn = BASE) -> dict:
    return {a.action: a for a in suppressor.rank_actions(inputs)}


def test_all_five_actions_are_listed() -> None:
    assert set(_by_action()) == {"fans_off", "co2", "fans_off_co2", "cut_power", "water_mist"}


def test_actions_change_the_inputs_as_configured() -> None:
    actions = _by_action()
    assert actions["fans_off"].new_inputs.flow_speed_cm_s == 0.0
    assert actions["fans_off"].new_inputs.o2_pct == 21.0
    assert actions["co2"].new_inputs.o2_pct == 21.0 - config.CO2_O2_DROP_PCT
    assert actions["co2"].new_inputs.flow_speed_cm_s == 10.0
    both = actions["fans_off_co2"].new_inputs
    assert (both.flow_speed_cm_s, both.o2_pct) == (0.0, 21.0 - config.CO2_O2_DROP_PCT)
    assert actions["cut_power"].new_inputs == BASE
    assert actions["water_mist"].new_inputs == BASE


def test_fans_off_beats_water_mist_with_default_data() -> None:
    ranked = [a.action for a in suppressor.rank_actions(BASE)]
    assert ranked.index("fans_off") < ranked.index("water_mist")
    assert ranked[-1] == "water_mist"


def test_cut_power_and_water_mist_have_no_data_support() -> None:
    actions = _by_action()
    assert actions["cut_power"].data_support == "none"
    assert actions["cut_power"].explanation == "standard procedure, removes ignition source"
    assert actions["water_mist"].data_support == "none"
    assert "no direct NASA data" in actions["water_mist"].explanation


def test_supported_actions_are_sorted_by_score_and_come_first() -> None:
    ranked = suppressor.rank_actions(BASE)
    backed = [a for a in ranked if a.data_support != "none"]
    assert ranked[: len(backed)] == backed
    assert [a.score for a in backed] == sorted((a.score for a in backed), reverse=True)


def test_score_is_extinction_minus_weighted_crew_risk_and_detection_delay() -> None:
    co2 = _by_action()["co2"]  # fans stay on, so there is no detection delay
    assert co2.score == pytest.approx(
        co2.extinction_probability - co2.crew_risk * config.CREW_RISK_WEIGHT
    )
    fans = _by_action()["fans_off"]  # smoke can no longer reach a vent: full delay penalty
    assert fans.score == pytest.approx(
        fans.extinction_probability
        - fans.crew_risk * config.CREW_RISK_WEIGHT
        - config.DETECTION_DELAY_WEIGHT
    )
    assert "smoke cannot reach vents" in fans.explanation


def test_lowering_oxygen_raises_the_extinction_probability() -> None:
    actions = _by_action()
    assert actions["co2"].extinction_probability > actions["cut_power"].extinction_probability
    assert actions["fans_off_co2"].extinction_probability > actions["co2"].extinction_probability


def test_sources_are_the_nearest_tests_at_the_new_inputs() -> None:
    for action in _by_action().values():
        assert len(action.sources) == 3


def test_suppress_recommends_the_best_data_backed_action() -> None:
    out = suppressor.suppress("abc", BASE)
    assert isinstance(out, SuppressOut)
    assert out.scenario_id == "abc"
    assert out.recommended == out.actions[0].action
    assert out.actions[0].data_support != "none"


def test_extrapolated_new_inputs_are_flagged_in_the_explanation() -> None:
    low_o2 = BASE.model_copy(update={"o2_pct": 15.0})
    assert "outside tested range" in _by_action(low_o2)["co2"].explanation


def test_unknown_action_raises_a_clear_error() -> None:
    with pytest.raises(ValueError, match="unknown action"):
        suppressor.new_inputs_for(BASE, "halon")
