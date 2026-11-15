"""Agent tool registry: schemas, logging, traceability and errors returned as data."""

from ml.pipeline import tools
from ml.pipeline.types import Scenario

BASE = Scenario(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def test_every_tool_has_an_openai_function_schema() -> None:
    specs = tools.schemas(list(tools.TOOLS))
    assert len(specs) == len(tools.TOOLS)
    for spec in specs:
        assert spec["type"] == "function"
        assert spec["function"]["parameters"]["type"] == "object"
        assert spec["function"]["description"]


def test_a_call_is_logged_and_its_id_points_at_the_tool_itself() -> None:
    session = tools.Session(BASE)
    out = tools.call(session, "simulate", {"o2_pct": 15.0})
    entry = session.log.entries[out["call_id"]]
    assert entry["tool"] == "simulate" and entry["inputs"] == {"o2_pct": 15.0}
    assert entry["output"] == out["result"]
    assert 0.0 <= out["result"]["burn_probability"] <= 1.0


def test_plan_then_critique_then_report_run_in_one_session(tmp_path) -> None:
    session = tools.Session(BASE, out_dir=tmp_path)
    plans = tools.call(session, "plan")
    assert plans["result"][0]["steps"][0] == "cut_power"
    plan_entry = session.log.entries[plans["call_id"]]
    assert plan_entry["tool"] == "plan"  # inner predict/detect calls come after it
    verdict = tools.call(session, "critique")["result"]
    assert verdict["approved"] is True and verdict["recommended"][0] == "cut_power"
    report = tools.call(session, "report")["result"]
    assert report["pdf"].endswith(".pdf")


def test_simulate_fire_tool_returns_the_summary() -> None:
    session = tools.Session(BASE)
    out = tools.call(session, "simulate_fire", {"actions": [{"time_s": 5, "action": "co2"}]})
    assert "alarm_time_s" in out["result"] and "events" in out["result"]


def test_bad_names_and_bad_arguments_come_back_as_errors_not_exceptions() -> None:
    session = tools.Session(BASE)
    assert "unknown tool" in tools.call(session, "launch_rocket")["error"]
    bad = tools.call(session, "retrieve", {})  # missing the required query
    assert "error" in bad and session.log.entries[bad["call_id"]]["error"]
