"""A2/A3: detector, analyze, plan, critique, report and the full run_pipeline loop."""

import json
import os
from dataclasses import replace
from pathlib import Path

from ml.pipeline import config, stages
from ml.pipeline.detector import detect
from ml.pipeline.types import Scenario, ToolLog

BASE = Scenario(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def _plans(scenario: Scenario = BASE):
    tl = ToolLog()
    evidence = stages.analyze(scenario, tl)
    return stages.plan(scenario, evidence, tl), tl, evidence


def _by_steps(plans, *steps):
    return next(p for p in plans if p.steps == steps)


# ---------- detector ----------


def test_detect_flow_on_trips_downstream_vent() -> None:
    d = detect(BASE)
    assert d.detected and d.detector_id == "vent_fwd"
    assert d.time_to_detect_s == 40.0  # 4.0 m downstream at 0.10 m/s


def test_detect_flow_off_never_reaches_vents() -> None:
    d = detect(replace(BASE, flow_speed_cm_s=0.0))
    assert not d.detected and d.time_to_detect_s is None
    assert d.note == config.NOTE_FANS_OFF


def test_detect_flow_pointing_away_from_all_detectors() -> None:
    d = detect(replace(BASE, flow_dir=(0.0, -1.0, 0.0)))
    assert not d.detected and d.detector_id is None
    assert len(d.detectors) == len(config.DETECTORS)


# ---------- analyze ----------


def test_analyze_returns_nearest_tests_and_logs_tools() -> None:
    tl = ToolLog()
    evidence = stages.analyze(BASE, tl)
    assert len(evidence.nearest) == config.NEAREST_K
    assert [e["tool"] for e in tl.entries] == ["nearest_tests", "retrieve"]


def test_retrieve_reads_docs_with_source_header(tmp_path: Path) -> None:
    doc = tmp_path / "FLEX" / "abstract.txt"
    doc.parent.mkdir()
    doc.write_text("https://example.test/flex\nCO2 suppression of heptane droplets.\n\nOther.")
    hits = stages.retrieve("co2 suppression", docs_dir=tmp_path)
    assert hits[0].investigation == "FLEX"
    assert hits[0].source_url == "https://example.test/flex"


# ---------- plan ----------


def test_cut_power_is_always_step_one_and_max_three_steps() -> None:
    plans, _, _ = _plans()
    assert plans
    assert all(p.steps[0] == "cut_power" for p in plans)
    assert all(len(p.steps) <= config.MAX_PLAN_STEPS for p in plans)


def test_fans_off_beats_water_mist_with_default_data() -> None:
    plans, _, _ = _plans()
    fans = _by_steps(plans, "cut_power", "fans_off")
    mist = _by_steps(plans, "cut_power", "water_mist")
    assert plans.index(fans) < plans.index(mist)
    assert fans.extinction_probability > mist.extinction_probability
    assert mist.data_support == "none"


def test_plans_without_data_support_rank_last() -> None:
    plans, _, _ = _plans()
    supports = [p.data_support == "none" for p in plans]
    assert supports == sorted(supports)


def test_fans_off_pays_a_detection_delay_penalty() -> None:
    plans, _, _ = _plans()
    assert _by_steps(plans, "cut_power", "fans_off").detection_delay_penalty == 1.0
    assert _by_steps(plans, "cut_power", "co2").detection_delay_penalty == 0.0


def test_plan_handles_zero_flow_scenario() -> None:
    plans, _, _ = _plans(replace(BASE, flow_speed_cm_s=0.0))
    assert all(0.0 <= p.extinction_probability <= 1.0 for p in plans)


# ---------- critique ----------


def test_critique_approves_traceable_plans() -> None:
    plans, tl, _ = _plans()
    result = stages.critique(plans, tl)
    assert result.approved
    assert result.recommended is not None
    assert result.recommended.data_support != "none"
    assert not [i for i in result.issues if i["rule"] == "traceable_numbers"]


def test_critique_rejects_a_number_that_is_not_in_the_tool_log() -> None:
    plans, tl, _ = _plans()
    fake = replace(plans[0], extinction_probability=0.999, score=0.999)
    result = stages.critique([fake, *plans[1:]], tl)
    assert any(i["plan"] == fake.label and i["rule"] == "traceable_numbers" for i in result.issues)
    assert result.recommended.steps != fake.steps


def test_critique_rejects_plans_with_an_empty_tool_log() -> None:
    plans, _, _ = _plans()
    assert not stages.critique(plans, ToolLog()).approved


def test_extrapolated_inputs_give_low_trust() -> None:
    plans, tl, evidence = _plans(replace(BASE, o2_pct=34.0))
    assert evidence.extrapolated and evidence.trust == "weak"
    result = stages.critique(plans, tl)
    assert all(p.trust == "weak" for p in result.plans if p.extrapolated)
    assert _by_steps(result.plans, "cut_power", "water_mist").trust == "weak"


def test_critique_lowers_trust_when_a_plan_overstates_it() -> None:
    plans, tl, _ = _plans(replace(BASE, o2_pct=34.0))
    overstated = [replace(p, trust="strong") for p in plans]
    result = stages.critique(overstated, tl)
    assert all(p.trust == "weak" for p in result.plans if p.extrapolated)


def test_critique_rejects_crew_risk_over_threshold() -> None:
    plans, tl, _ = _plans()
    risky = [p for p in plans if p.crew_risk > config.CREW_RISK_MAX]
    result = stages.critique(plans, tl)
    flagged = {i["plan"] for i in result.issues if i["rule"] == "crew_risk"}
    assert flagged == {p.label for p in risky}
    assert result.recommended.crew_risk <= config.CREW_RISK_MAX


# ---------- report + full loop ----------


def test_report_exports_pdf_csv_json(tmp_path: Path) -> None:
    plans, _, evidence = _plans()
    rep = stages.report(BASE, plans, evidence, out_dir=tmp_path)
    assert Path(rep.pdf_path).read_bytes().startswith(b"%PDF")
    assert Path(rep.csv_path).read_text().splitlines()[0].startswith("rank,plan")
    saved = json.loads(Path(rep.json_path).read_text())
    assert {"methods", "scenario", "results", "evidence_table", "data_gaps"} <= set(saved)


def test_run_pipeline_full_loop_without_llm_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert "OPENAI_API_KEY" not in os.environ
    result = stages.run_pipeline(BASE, out_dir=tmp_path)
    assert result.simulation["state"] == "burning"
    assert result.detection.detected
    assert result.critic.approved
    assert result.applied["state"] == "extinguished"
    assert [r["step"] for r in result.results_rows] == ["simulate", "detect", "apply"]
    assert Path(result.report.pdf_path).stat().st_size > 0
    tools = {e["tool"] for e in result.tool_log}
    assert {"predict", "detect", "nearest_tests", "retrieve", "report"} <= tools
