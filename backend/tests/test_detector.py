"""BE-03: detector service with the flow on, off, and pointing away from every detector."""

from app.schemas import DetectOut, ScenarioIn
from app.services import detector

BASE = ScenarioIn(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def test_flow_on_trips_the_downstream_vent() -> None:
    out = detector.detect(BASE)
    assert isinstance(out, DetectOut)
    assert out.detected is True
    assert out.detector_id == "vent_fwd"
    assert out.time_to_detect_s == 40.0  # 4.0 m downstream at 10 cm/s


def test_faster_flow_is_detected_sooner() -> None:
    fast = detector.detect(BASE.model_copy(update={"flow_speed_cm_s": 20.0}))
    assert fast.time_to_detect_s < detector.detect(BASE).time_to_detect_s


def test_flow_off_smoke_cannot_reach_vents() -> None:
    out = detector.detect(BASE.model_copy(update={"flow_speed_cm_s": 0.0}))
    assert out.detected is False
    assert out.detector_id is None and out.time_to_detect_s is None
    assert out.note == "fans off: smoke cannot reach vents"


def test_flow_pointing_away_from_all_detectors() -> None:
    out = detector.detect(BASE.model_copy(update={"flow_dir": (0.0, -1.0, 0.0)}))
    assert out.detected is False
    assert out.time_to_detect_s is None
    assert "away" in out.note


def test_reversed_flow_trips_the_other_vent() -> None:
    out = detector.detect(BASE.model_copy(update={"flow_dir": (-1.0, 0.0, 0.0)}))
    assert out.detector_id == "vent_aft"


def test_every_detector_reports_id_position_and_peak_concentration() -> None:
    out = detector.detect(BASE)
    assert len(out.detectors) == 3
    for det in out.detectors:
        assert {"id", "position", "peak_concentration"} <= set(det)
        assert len(det["position"]) == 3
        assert 0.0 <= det["peak_concentration"] <= 1.0


def test_fire_next_to_a_vent_is_detected_with_fans_off() -> None:
    out = detector.detect(
        BASE.model_copy(update={"flow_speed_cm_s": 0.0}), fire_position=(3.8, 1.37, 0.0)
    )
    assert out.detected is True and out.detector_id == "vent_fwd"


def test_detection_holds_across_the_whole_flow_slider() -> None:
    times = [
        detector.detect(BASE.model_copy(update={"flow_speed_cm_s": speed})).time_to_detect_s
        for speed in (2.0, 5.0, 10.0, 20.0, 40.0)
    ]
    assert all(t is not None for t in times)
    assert times == sorted(times, reverse=True)


def test_very_slow_flow_times_out_with_its_own_note() -> None:
    out = detector.detect(BASE.model_copy(update={"flow_speed_cm_s": 1.0}))
    assert out.detected is False
    assert "too slow" in out.note
