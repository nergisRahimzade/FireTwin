"""POST /simulate and POST /apply (BE-02).

Both run the same path: predictor.predict -> rag.explain -> one history row in the store.
/simulate starts a new scenario; /apply changes an existing one with a suppression action.
The router stays thin: all logic lives in app/services.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas import ApplyIn, ScenarioIn, SimulateOut
from app.services import cache, store, suppressor
from ml.pipeline import config

log = logging.getLogger(__name__)

router = APIRouter(tags=["simulation"])


def run_step(scenario_id: str, inputs: ScenarioIn, step: str, action: str | None) -> SimulateOut:
    """Predict, explain, and record one history row. Shared by /simulate and /apply."""
    (prob, spread, trust, extrapolated, nearest), explanation = cache.predict_and_explain(inputs)
    state = "burning" if prob >= config.BURN_THRESHOLD else "extinguished"
    store.append(
        scenario_id,
        step,
        inputs=inputs,
        state=state,
        probability=prob,
        trust=trust,
        action=action,
        sources=[ref.test_id for ref in nearest],
    )
    return SimulateOut(
        scenario_id=scenario_id,
        state=state,
        burn_probability=prob,
        spread_rate_mm_s=spread,
        trust=trust,
        extrapolated=extrapolated,
        nearest_tests=nearest,
        explanation=explanation,
        inputs=inputs,
    )


@router.post("/simulate", response_model=SimulateOut)
def simulate(inputs: ScenarioIn) -> SimulateOut:
    """Ignite a scenario and predict whether the fire keeps burning."""
    try:
        scenario_id = store.create(inputs)
        return run_step(scenario_id, inputs, "simulate", None)
    except ValueError as exc:
        log.warning("/simulate rejected inputs=%s: %s", inputs, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("/simulate failed for inputs=%s", inputs)
        raise HTTPException(status_code=500, detail="simulation failed; see server log") from exc


@router.post("/apply", response_model=SimulateOut)
def apply(body: ApplyIn) -> SimulateOut:
    """Apply one suppression action to a scenario and re-predict with the new inputs."""
    try:
        current = store.get_inputs(body.scenario_id)
        new_inputs = suppressor.new_inputs_for(current, body.action)
        result = run_step(body.scenario_id, new_inputs, "apply", body.action)
        store.set_inputs(body.scenario_id, new_inputs)
        return result
    except store.ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        log.warning("/apply rejected body=%s: %s", body, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("/apply failed for body=%s", body)
        raise HTTPException(status_code=500, detail="apply failed; see server log") from exc
