"""Smoke detector tool (BE-03): when and where the alarm trips.

In microgravity smoke does not rise: it is carried along the airflow towards the vent it points at,
and spreads sideways by diffusion. Time to detect = distance along the flow / flow speed.
The geometry and diffusion numbers are illustrative values from config, not NASA measurements.
"""

from __future__ import annotations

import logging
import math

from ml.pipeline import config
from ml.pipeline.types import Detection, Scenario

log = logging.getLogger(__name__)


def detect(
    scenario: Scenario, fire_position: tuple[float, float, float] = config.FIRE_POSITION
) -> Detection:
    """Time for smoke to reach the first detector; None = it never reaches one in time."""
    try:
        speed_m_s = max(scenario.flow_speed_cm_s, 0.0) / 100.0
        norm = math.sqrt(sum(c * c for c in scenario.flow_dir))
        moving = speed_m_s > 0 and norm > 0
        direction = tuple(c / norm for c in scenario.flow_dir) if moving else (0.0, 0.0, 0.0)

        detectors, best, too_slow = [], None, False
        cone = math.tan(math.radians(config.DOWNSTREAM_CONE_DEG))
        for det in config.DETECTORS:
            offset = tuple(p - f for p, f in zip(det["position"], fire_position))
            dist = math.sqrt(sum(c * c for c in offset))
            time_s, peak = None, 0.0
            if moving:
                along = sum(o * d for o, d in zip(offset, direction))
                lateral = math.sqrt(max(dist * dist - along * along, 0.0))
                if along > 0:
                    t = along / speed_m_s
                    radius = config.PLUME_RADIUS_M + math.sqrt(4 * config.DIFFUSION_M2_S * t)
                    peak = math.exp(-((lateral / radius) ** 2))
                    if lateral <= along * cone:  # the flow points at this vent
                        time_s = t
                        too_slow = too_slow or t > config.DETECT_TIMEOUT_S
            else:  # no airflow: diffusion only, very slow
                time_s = dist * dist / (4 * config.STILL_AIR_DIFFUSION_M2_S)
                peak = math.exp(-time_s / config.DETECT_TIMEOUT_S)
            reached = time_s is not None and time_s <= config.DETECT_TIMEOUT_S
            detectors.append(
                {
                    "id": det["id"],
                    "position": list(det["position"]),
                    "peak_concentration": round(peak, 4),
                    "time_s": round(time_s, 1) if reached else None,
                }
            )
            if reached and (best is None or time_s < best[1]):
                best = (det["id"], time_s)

        if best is not None:
            note = f"smoke reaches {best[0]} after {best[1]:.0f} s"
            return Detection(True, best[0], round(best[1], 1), detectors, note)
        if not moving:
            note = config.NOTE_FANS_OFF
        elif too_slow:
            limit = f"{config.DETECT_TIMEOUT_S:.0f} s"
            note = f"airflow too slow: smoke needs over {limit} to reach a vent"
        else:
            note = "airflow carries smoke away from all vents"
        return Detection(False, None, None, detectors, note)
    except Exception:
        log.exception("detect failed for scenario=%s fire_position=%s", scenario, fire_position)
        raise
