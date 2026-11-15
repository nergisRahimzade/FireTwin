"""BE-01: in-memory scenario store."""

import pytest

from app.schemas import ScenarioIn
from app.services import store

BASE = ScenarioIn(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


@pytest.fixture(autouse=True)
def _empty_store():
    store.clear()
    yield
    store.clear()


def test_create_returns_unique_ids_and_keeps_inputs() -> None:
    first, second = store.create(BASE), store.create(BASE)
    assert first != second
    assert store.get_inputs(first) == BASE
    assert store.history(first) == []


def test_each_step_appends_a_row_with_all_result_columns() -> None:
    sid = store.create(BASE)
    store.append(sid, "simulate", state="burning", probability=0.9, trust="medium", sources=["T1"])
    store.append(sid, "detect", detection_s=40.0)
    store.append(sid, "apply", state="extinguished", probability=0.1, action="fans_off")
    rows = store.history(sid)
    assert [r["step"] for r in rows] == ["simulate", "detect", "apply"]
    assert all(tuple(r) == store.ROW_KEYS for r in rows)
    assert rows[0]["inputs"]["o2_pct"] == 21.0
    assert rows[1]["detection_s"] == 40.0
    assert rows[2]["action"] == "fans_off"


def test_set_inputs_changes_the_current_inputs() -> None:
    sid = store.create(BASE)
    fans_off = BASE.model_copy(update={"flow_speed_cm_s": 0.0})
    store.set_inputs(sid, fans_off)
    assert store.get_inputs(sid).flow_speed_cm_s == 0.0
    assert store.append(sid, "apply")["inputs"]["flow_speed_cm_s"] == 0.0


def test_history_is_a_copy() -> None:
    sid = store.create(BASE)
    store.append(sid, "simulate")
    store.history(sid)[0]["step"] = "tampered"
    assert store.history(sid)[0]["step"] == "simulate"


def test_unknown_scenario_raises_scenario_not_found() -> None:
    with pytest.raises(store.ScenarioNotFound, match="nope"):
        store.get_inputs("nope")
    with pytest.raises(store.ScenarioNotFound):
        store.append("nope", "simulate")


def test_unknown_step_is_rejected() -> None:
    sid = store.create(BASE)
    with pytest.raises(ValueError, match="step"):
        store.append(sid, "explode")
