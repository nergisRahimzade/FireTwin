"""Physics-shaped fire simulation: the scenario over time, with actions applied mid-fire.

What it adds to a single prediction is TIME: when the alarm trips, when an action takes effect,
when the flame dies. Each step:
1. Air: fans-off spins the airflow down and CO2 dilutes oxygen, each over a time constant.
2. Flame: the per-fuel model (O2 and the U-shaped ln-airflow terms) decides whether a flame can
   survive the CURRENT oxygen and airflow. While it can, it spreads at the microgravity spread
   rate measured in Saffire-II, scaled with oxygen; when it cannot, it shrinks and goes out.
3. Smoke: the flame releases smoke in proportion to its area. Each release is a puff carried by
   the airflow and spread by diffusion (an exact 3-D Gaussian solution); a vent detector trips
   when the summed concentration reaches its threshold. In microgravity smoke does not rise.

Honesty: whether the flame survives comes from the model trained on NASA tests; the spread rate
is the mean of the Saffire-II micro-g rates in the table. Time constants, diffusion and the alarm
threshold are illustrative engineering values (config), so times are estimates, not measurements.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from functools import lru_cache

import numpy as np

from ml.pipeline import config, model
from ml.pipeline.types import Scenario

log = logging.getLogger(__name__)

ACTIONS = ("fans_off", "co2", "cut_power", "water_mist")


@dataclass(frozen=True)
class FireTrace:
    times_s: list[float]
    o2_pct: list[float]
    flow_cm_s: list[float]
    burn_probability: list[float]
    flame_radius_mm: list[float]
    detector_level: dict[str, list[float]]  # concentration / alarm threshold (1.0 = trips)
    alarm_time_s: float | None
    alarm_detector: str | None
    extinguished_at_s: float | None
    spread_rate_mm_s: float
    events: list[dict] = field(default_factory=list)


def reference_spread_rate() -> float:
    """Mean micro-g spread rate of the solid tests that state one (Saffire-II), else the default."""
    try:
        table = model.load_table()
        rates = table.loc[table["fuel_type"] == "solid", "spread_rate_mm_s"].dropna()
        return float(rates.mean()) if len(rates) else config.SIM_DEFAULT_SPREAD_MM_S
    except Exception:
        log.exception("reference_spread_rate: table unavailable; using the default")
        return config.SIM_DEFAULT_SPREAD_MM_S


@lru_cache(maxsize=4096)
def _burn_probability(material: str, pressure: float, o2: float, flow: float) -> float:
    return model.burn_probability(Scenario(material, o2, flow, pressure_kpa=pressure))


def simulate_fire(
    scenario: Scenario,
    actions: list[tuple[float, str]] | None = None,
    duration_s: float = config.SIM_DURATION_S,
    dt_s: float = config.SIM_DT_S,
) -> FireTrace:
    """Run the fire for `duration_s`; `actions` are (time in s, action name) applied in order."""
    try:
        return _run(scenario, sorted(actions or []), duration_s, dt_s)
    except Exception:
        log.exception("simulate_fire failed for scenario=%s actions=%s", scenario, actions)
        raise


def _run(scenario: Scenario, actions: list, duration_s: float, dt: float) -> FireTrace:
    for _, name in actions:
        if name not in ACTIONS:
            raise ValueError(f"simulate_fire: unknown action {name!r}, expected {ACTIONS}")
    norm = math.sqrt(sum(c * c for c in scenario.flow_dir)) or 1.0
    direction = np.array(scenario.flow_dir, dtype=float) / norm
    fire = np.array(config.FIRE_POSITION, dtype=float)
    vents = {d["id"]: np.array(d["position"], dtype=float) for d in config.DETECTORS}
    spread = reference_spread_rate()

    o2, flow = scenario.o2_pct, max(scenario.flow_speed_cm_s, 0.0)
    o2_target, flow_target = o2, flow
    radius_mm = config.SIM_IGNITION_RADIUS_MM
    burning = True
    # Puffs: centre (m), variance (m^2), mass. Stored as arrays that grow by one per step.
    centres = np.empty((0, 3))
    variances = np.empty(0)
    masses = np.empty(0)

    out = {"t": [], "o2": [], "flow": [], "p": [], "r": []}
    levels: dict[str, list[float]] = {k: [] for k in vents}
    events, alarm_t, alarm_id, out_t = [], None, None, None
    pending = list(actions)
    steps = int(round(duration_s / dt))
    for step in range(steps + 1):
        t = step * dt
        while pending and pending[0][0] <= t:
            _, name = pending.pop(0)
            if name == "fans_off":
                flow_target = 0.0
            elif name == "co2":
                o2_target = max(o2_target - config.CO2_O2_DROP_PCT, 0.0)
            events.append({"time_s": round(t, 2), "event": f"action {name}"})
            if name == "water_mist":
                events[-1]["note"] = "no NASA data for water mist: not modelled, no effect"

        # 1. Air relaxes towards its targets (first-order lag).
        flow += (flow_target - flow) * (1 - math.exp(-dt / config.SIM_FAN_SPINDOWN_S))
        o2 += (o2_target - o2) * (1 - math.exp(-dt / config.SIM_CO2_MIXING_S))

        # 2. Flame: the trained model decides whether it can live at the current conditions.
        p = _burn_probability(
            scenario.material, scenario.pressure_kpa, round(o2, 1), round(flow, 1)
        )
        if burning and p < config.BURN_THRESHOLD:
            burning = False
            events.append({"time_s": round(t, 2), "event": "flame cannot survive these conditions"})
        if burning:
            radius_mm += spread * (o2 / config.SIM_SPREAD_REF_O2_PCT) * dt
            radius_mm = min(radius_mm, config.SIM_MAX_FLAME_RADIUS_MM)
        else:
            radius_mm *= math.exp(-dt / config.SIM_FLAME_DECAY_S)
            if out_t is None and radius_mm < config.SIM_IGNITION_RADIUS_MM:
                out_t = t
                events.append({"time_s": round(t, 2), "event": "flame out"})

        # 3. Smoke: release a puff, move every puff with the air, spread it by diffusion.
        area_m2 = (
            math.pi * (radius_mm / 1000) ** 2 if radius_mm >= config.SIM_IGNITION_RADIUS_MM else 0.0
        )
        diffusion = (
            config.DIFFUSION_M2_S
            if flow > config.SIM_STILL_AIR_CM_S
            else config.STILL_AIR_DIFFUSION_M2_S
        )
        centres = np.vstack([centres, fire]) + direction * (flow / 100) * dt
        variances = np.append(variances, max(radius_mm / 1000, 0.005) ** 2) + 2 * diffusion * dt
        masses = np.append(masses, area_m2 * config.SIM_SMOKE_PER_M2_S * dt)

        for vent_id, position in vents.items():
            d2 = ((centres - position) ** 2).sum(axis=1)
            conc = float(
                (masses / (2 * math.pi * variances) ** 1.5 * np.exp(-d2 / (2 * variances))).sum()
            )
            level = conc / config.SIM_ALARM_CONCENTRATION
            levels[vent_id].append(round(level, 4))
            if alarm_t is None and level >= 1.0:
                alarm_t, alarm_id = t, vent_id
                events.append({"time_s": round(t, 2), "event": f"alarm at {vent_id}"})
        for key, value in (("t", t), ("o2", o2), ("flow", flow), ("p", p), ("r", radius_mm)):
            out[key].append(round(value, 4))

    return FireTrace(
        times_s=out["t"],
        o2_pct=out["o2"],
        flow_cm_s=out["flow"],
        burn_probability=out["p"],
        flame_radius_mm=out["r"],
        detector_level=levels,
        alarm_time_s=alarm_t,
        alarm_detector=alarm_id,
        extinguished_at_s=out_t,
        spread_rate_mm_s=round(spread, 3),
        events=events,
    )


def summarize(trace: FireTrace) -> dict:
    """The few numbers an agent or the UI needs, without the time series."""
    return {
        "alarm_time_s": trace.alarm_time_s,
        "alarm_detector": trace.alarm_detector,
        "extinguished_at_s": trace.extinguished_at_s,
        "final_flame_radius_mm": trace.flame_radius_mm[-1] if trace.flame_radius_mm else None,
        "spread_rate_mm_s": trace.spread_rate_mm_s,
        "events": trace.events,
    }


def with_inputs(scenario: Scenario, **changes) -> Scenario:
    return replace(scenario, **changes)
