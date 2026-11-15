"""POST /preview: the model's verdict for some inputs, without starting a scenario.

Live views call this while the user moves sliders (the 3D scene) or to draw a curve (the O2 chart).
/simulate would create a scenario, add a history row and write an explanation (possibly an LLM call)
for every point; this runs only the prediction, so it is fast and leaves /results untouched.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas import PreviewOut, ScenarioIn
from app.services import predictor
from ml.pipeline import config

log = logging.getLogger(__name__)

router = APIRouter(tags=["simulation"])


@router.post("/preview", response_model=PreviewOut)
def preview(inputs: ScenarioIn) -> PreviewOut:
    """Predict whether the fire keeps burning at these inputs; nothing is stored."""
    try:
        prob, _spread, trust, extrapolated, _nearest = predictor.predict(inputs)
    except ValueError as exc:  # e.g. a non-finite number: the same 422 as /simulate
        log.warning("/preview rejected inputs=%s: %s", inputs, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("/preview failed for inputs=%s", inputs)
        raise HTTPException(status_code=500, detail="preview failed; see server log") from exc
    return PreviewOut(
        # Same threshold as /simulate, so a preview never disagrees with the next Ignite.
        state="burning" if prob >= config.BURN_THRESHOLD else "extinguished",
        burn_probability=prob,
        trust=trust,
        extrapolated=extrapolated,
        is_synthetic=False,
        inputs=inputs,
    )
