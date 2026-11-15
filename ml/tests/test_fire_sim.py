"""Physics-shaped fire simulation (runs on the seed fixture, where the outcomes are known)."""

from dataclasses import replace

import pytest

from ml.pipeline import config, fire_sim
from ml.pipeline.types import Scenario

BASE = Scenario(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


@pytest.fixture(autouse=True)
def _fresh_cache():
    fire_sim._burn_probability.cache_clear()  # the seed fixture swaps the model per session
    yield


def test_airflow_towards_a_vent_trips_the_alarm_and_the_fire_keeps_burning() -> None:
    trace = fire_sim.simulate_fire(BASE)
    assert trace.alarm_time_s is not None and trace.alarm_detector in {"vent_fwd", "vent_mid"}
    assert trace.extinguished_at_s is None
    assert trace.flame_radius_mm[-1] == config.SIM_MAX_FLAME_RADIUS_MM
    assert len(trace.times_s) == len(trace.o2_pct) == len(trace.detector_level["vent_fwd"])


def test_airflow_pointing_away_from_every_vent_never_trips_it() -> None:
    trace = fire_sim.simulate_fire(replace(BASE, flow_dir=(0.0, -1.0, 0.0)))
    assert trace.alarm_time_s is None


def test_fans_off_slows_detection() -> None:
    fans_on = fire_sim.simulate_fire(BASE).alarm_time_s
    fans_off = fire_sim.simulate_fire(BASE, [(0.0, "fans_off")]).alarm_time_s
    assert fans_off is None or fans_off > fans_on


def test_co2_lowers_oxygen_until_the_flame_goes_out() -> None:
    trace = fire_sim.simulate_fire(BASE, [(30.0, "co2")])
    assert min(trace.o2_pct) == pytest.approx(21.0 - config.CO2_O2_DROP_PCT, abs=0.2)
    assert trace.extinguished_at_s is not None and trace.extinguished_at_s > 30.0
    assert any(e["event"] == "flame out" for e in trace.events)


def test_water_mist_is_logged_as_not_modelled() -> None:
    trace = fire_sim.simulate_fire(BASE, [(10.0, "water_mist")], duration_s=20)
    assert any("no NASA data" in e.get("note", "") for e in trace.events)


def test_zero_flow_does_not_crash_and_unknown_actions_are_refused() -> None:
    assert fire_sim.simulate_fire(replace(BASE, flow_speed_cm_s=0.0), duration_s=20).times_s
    with pytest.raises(ValueError, match="unknown action"):
        fire_sim.simulate_fire(BASE, [(1.0, "halon")])


def test_spread_rate_falls_back_when_no_test_states_one() -> None:
    assert fire_sim.reference_spread_rate() == config.SIM_DEFAULT_SPREAD_MM_S  # seed table


def test_summary_has_the_key_numbers_only() -> None:
    summary = fire_sim.summarize(fire_sim.simulate_fire(BASE, duration_s=60))
    assert set(summary) == {
        "alarm_time_s",
        "alarm_detector",
        "extinguished_at_s",
        "final_flame_radius_mm",
        "spread_rate_mm_s",
        "events",
    }
