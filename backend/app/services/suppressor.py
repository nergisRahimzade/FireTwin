"""Suppressor service (BE-04): rank the suppression actions for a burning scenario.

Each action is a change to the model inputs (fans off -> flow 0, CO2 -> lower O2). The changed
inputs go through the same burn model as /simulate, so every ranking is backed by the same data.
Score = extinction probability - crew_risk * weight - detection-delay penalty * weight.
All numbers (O2 drop, crew risk, weights) live in ml/pipeline/config.py. No FastAPI imports.
"""

from __future__ import annotations

import logging

from app.schemas import ActionResult, ScenarioIn, SuppressOut
from app.services import predictor
from ml.pipeline import config, model, stages
from ml.pipeline import detector as smoke

log = logging.getLogger(__name__)

# API action -> the basic steps it is made of.
ACTION_STEPS: dict[str, tuple[str, ...]] = {
    "fans_off": ("fans_off",),
    "co2": ("co2",),
    "fans_off_co2": ("fans_off", "co2"),
    "cut_power": ("cut_power",),
    "water_mist": ("water_mist",),
}
LABELS = {
    "fans_off": "Fans off",
    "co2": "CO2 extinguisher",
    "fans_off_co2": "Fans off + CO2",
    "cut_power": "Cut power (required first step)",
    "water_mist": "Water mist",
}
CUT_POWER_EXPLANATION = "standard procedure, removes ignition source"
WATER_MIST_EXPLANATION = "no direct NASA data for water mist; ranked last until data is added"


def new_inputs_for(inputs: ScenarioIn, action: str) -> ScenarioIn:
    """The scenario inputs after one action is applied (/apply re-predicts with these)."""
    if action not in ACTION_STEPS:
        raise ValueError(f"suppressor: unknown action {action!r}, expected {list(ACTION_STEPS)}")
    scenario = predictor.to_scenario(inputs)
    for step in ACTION_STEPS[action]:
        scenario = stages.apply_action(scenario, step)
    return inputs.model_copy(
        update={"o2_pct": scenario.o2_pct, "flow_speed_cm_s": scenario.flow_speed_cm_s}
    )


def _crew_risk(action: str) -> float:
    """Chance at least one step harms the crew, from the per-step placeholder risks."""
    safe = 1.0
    for step in ACTION_STEPS[action]:
        safe *= 1.0 - config.CREW_RISK[step]
    return 1.0 - safe


def _explain(action: str, new_inputs: ScenarioIn, extrapolated: bool, delayed: bool) -> str:
    if action == "cut_power":
        return CUT_POWER_EXPLANATION
    if action == "water_mist":
        return WATER_MIST_EXPLANATION
    parts = []
    if "fans_off" in ACTION_STEPS[action]:
        parts.append("stops the airflow that feeds the flame (flow 0 cm/s)")
    if "co2" in ACTION_STEPS[action]:
        parts.append(f"CO2 dilutes oxygen to {new_inputs.o2_pct:g} %")
    text = " and ".join(parts)
    if delayed:
        text += f"; trade-off: {config.NOTE_FANS_OFF}"
    if extrapolated:
        text += "; outside tested range: no direct NASA data"
    return text


def evaluate(inputs: ScenarioIn, action: str) -> ActionResult:
    """Score ONE action: re-predict at its new inputs and price in crew risk and detection."""
    try:
        new_inputs = new_inputs_for(inputs, action)
        prob, _, _, extrapolated, nearest = predictor.predict(new_inputs)
        before = smoke.detect(predictor.to_scenario(inputs))
        after = smoke.detect(predictor.to_scenario(new_inputs))
        penalty = stages.delay_penalty(before, after)
        extinction = 1.0 - prob
        crew_risk = _crew_risk(action)
        score = (
            extinction
            - crew_risk * config.CREW_RISK_WEIGHT
            - penalty * config.DETECTION_DELAY_WEIGHT
        )
        if action in ("cut_power", "water_mist"):
            support = "none"
        else:
            support = model.data_support(predictor.to_scenario(new_inputs))
        return ActionResult(
            action=action,
            label=LABELS[action],
            new_inputs=new_inputs,
            extinction_probability=extinction,
            crew_risk=crew_risk,
            score=score,
            data_support=support,
            sources=nearest,
            explanation=_explain(action, new_inputs, extrapolated, delayed=penalty > 0),
        )
    except Exception:
        log.exception("suppressor.evaluate failed for action=%s inputs=%s", action, inputs)
        raise


def rank_actions(inputs: ScenarioIn) -> list[ActionResult]:
    """All five actions, best first. Actions without NASA data go last, water mist very last."""
    results = [evaluate(inputs, action) for action in ACTION_STEPS]
    return sorted(
        results, key=lambda r: (r.data_support == "none", r.action == "water_mist", -r.score)
    )


def suppress(scenario_id: str, inputs: ScenarioIn) -> SuppressOut:
    """Ranked actions plus the recommended one (the best action that has data support)."""
    actions = rank_actions(inputs)
    backed = [a for a in actions if a.data_support != "none"]
    recommended = backed[0].action if backed else "cut_power"
    return SuppressOut(scenario_id=scenario_id, recommended=recommended, actions=actions)
