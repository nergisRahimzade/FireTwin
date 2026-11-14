"""Scenario store (BE-01): in-memory dict scenario_id -> {inputs, history[]}.

Each step (simulate, detect, apply) appends one history row. /results and /export read the
history, so the table and the PDF always match. Data is lost when the server restarts.
"""

from __future__ import annotations

import logging
import threading
import uuid
from copy import deepcopy

from app.schemas import ScenarioIn

log = logging.getLogger(__name__)

# The columns of one results-table row (ResultsOut.rows in the contract).
ROW_KEYS = ("step", "inputs", "state", "probability", "trust", "detection_s", "action", "sources")
STEPS = ("simulate", "detect", "apply")


class ScenarioNotFound(KeyError):
    """Raised when a scenario_id is not in the store (routers turn this into a 404)."""

    def __init__(self, scenario_id: str) -> None:
        super().__init__(scenario_id)
        self.scenario_id = scenario_id

    def __str__(self) -> str:
        return f"scenario {self.scenario_id!r} not found (it may predate a server restart)"


_lock = threading.Lock()
_scenarios: dict[str, dict] = {}


def create(inputs: ScenarioIn) -> str:
    """Store a new scenario and return its id."""
    scenario_id = uuid.uuid4().hex[:12]
    with _lock:
        _scenarios[scenario_id] = {"inputs": inputs, "history": []}
    return scenario_id


def _entry(scenario_id: str) -> dict:
    try:
        return _scenarios[scenario_id]
    except KeyError:
        log.warning("store: unknown scenario_id=%r", scenario_id)
        raise ScenarioNotFound(scenario_id) from None


def get_inputs(scenario_id: str) -> ScenarioIn:
    """The scenario's CURRENT inputs (they change when an action is applied)."""
    with _lock:
        return _entry(scenario_id)["inputs"]


def set_inputs(scenario_id: str, inputs: ScenarioIn) -> None:
    """Replace the current inputs, e.g. after /apply turned the fans off."""
    with _lock:
        _entry(scenario_id)["inputs"] = inputs


def append(
    scenario_id: str,
    step: str,
    *,
    inputs: ScenarioIn | None = None,
    state: str | None = None,
    probability: float | None = None,
    trust: str | None = None,
    detection_s: float | None = None,
    action: str | None = None,
    sources: list[str] | None = None,
) -> dict:
    """Append one history row for a step and return it. Unknown steps are rejected."""
    if step not in STEPS:
        raise ValueError(f"store.append: step {step!r} is not one of {STEPS}")
    with _lock:
        entry = _entry(scenario_id)
        row = {
            "step": step,
            "inputs": (inputs or entry["inputs"]).model_dump(),
            "state": state,
            "probability": probability,
            "trust": trust,
            "detection_s": detection_s,
            "action": action,
            "sources": list(sources or []),
        }
        entry["history"].append(row)
        return deepcopy(row)


def history(scenario_id: str) -> list[dict]:
    """A copy of the scenario's history rows, oldest first."""
    with _lock:
        return deepcopy(_entry(scenario_id)["history"])


def get(scenario_id: str) -> dict:
    """{inputs, history[]} for one scenario (a copy: editing it does not change the store)."""
    with _lock:
        entry = _entry(scenario_id)
        return {"inputs": entry["inputs"], "history": deepcopy(entry["history"])}


def clear() -> None:
    """Forget every scenario (used by tests)."""
    with _lock:
        _scenarios.clear()
