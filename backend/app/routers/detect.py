"""POST /detect: when and where the smoke alarm trips for a scenario.

Thin router over services/detector.py (BE-03). The plan has the detector service but no task for
this router, so it was added to close the e2e loop (OPS-04). It also appends the "detect" history
row that /results and the PDF read (BE-01: every simulate, detect and apply step adds a row).
"""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas import DetectOut, ScenarioRef
from app.services import detector, store

log = logging.getLogger(__name__)

router = APIRouter(tags=["simulation"])


def _current_sources(scenario_id: str) -> list[str]:
    # The detect row carries the sources behind the current verdict (the latest row that has any),
    # so the results table can still badge synthetic sources on it (docs/contract.md).
    for row in reversed(store.history(scenario_id)):
        if row["sources"]:
            return list(row["sources"])
    return []


@router.post("/detect", response_model=DetectOut)
def detect(body: ScenarioRef) -> DetectOut:
    """Run the smoke model at the scenario's current inputs and record the detection step."""
    try:
        inputs = store.get_inputs(body.scenario_id)
        result = detector.detect(inputs)
        store.append(
            body.scenario_id,
            "detect",
            inputs=inputs,
            detection_s=result.time_to_detect_s,  # None = smoke never reached a detector
            sources=_current_sources(body.scenario_id),
        )
        return result
    except store.ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        log.warning("/detect rejected body=%s: %s", body, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("/detect failed for body=%s", body)
        raise HTTPException(status_code=500, detail="detection failed; see server log") from exc
