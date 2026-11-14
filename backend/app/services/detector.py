"""Detector service (BE-03): when and where the smoke alarm trips.

Adapter over ml/pipeline/detector.py, which holds the smoke maths (module box, vent detector
positions, airflow + diffusion; all numbers in ml/pipeline/config.py). No FastAPI imports.
"""

from __future__ import annotations

import logging

from app.schemas import DetectOut, ScenarioIn
from app.services.predictor import to_scenario
from ml.pipeline import config
from ml.pipeline import detector as smoke

log = logging.getLogger(__name__)


def detect(
    inputs: ScenarioIn, fire_position: tuple[float, float, float] = config.FIRE_POSITION
) -> DetectOut:
    """Time for smoke to reach the first vent detector; detected=False if it never does.

    fire_position defaults to the module centre. With the fans off the smoke only diffuses,
    which takes longer than the timeout, so the note says it cannot reach the vents.
    """
    try:
        result = smoke.detect(to_scenario(inputs), fire_position)
        return DetectOut(
            detected=result.detected,
            detector_id=result.detector_id,
            time_to_detect_s=result.time_to_detect_s,
            detectors=result.detectors,
            note=result.note,
        )
    except Exception:
        log.exception(
            "detector.detect failed for inputs=%s fire_position=%s", inputs, fire_position
        )
        raise
