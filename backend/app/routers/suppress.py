"""POST /suppress: rank the suppression actions for a scenario.

Thin router over services/suppressor.py (BE-04). The plan has the suppressor service but no task for
this router, so it was added to close the e2e loop (OPS-04). Ranking changes nothing, so it adds no
history row: the plan's steps are simulate, detect and apply (BE-01).
"""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas import ScenarioRef, SuppressOut
from app.services import store, suppressor

log = logging.getLogger(__name__)

router = APIRouter(tags=["simulation"])


@router.post("/suppress", response_model=SuppressOut)
def suppress(body: ScenarioRef) -> SuppressOut:
    """Every action re-predicted at its new inputs, best score first."""
    try:
        inputs = store.get_inputs(body.scenario_id)
        return suppressor.suppress(body.scenario_id, inputs)
    except store.ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        log.warning("/suppress rejected body=%s: %s", body, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("/suppress failed for body=%s", body)
        raise HTTPException(status_code=500, detail="suppression failed; see server log") from exc
