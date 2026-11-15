"""Pydantic API contract (BE-05, Phase 0). SOURCE OF TRUTH for every layer.

Copied field for field from the "Shared API contract" in the Implementation Tasks doc.
The frontend generates its TypeScript types from /openapi.json, which FastAPI builds from these.

Rule 3: never change a model here without (1) all three teammates agreeing, (2) regenerating
the frontend types (npm run gen:api), and (3) noting the change in docs/CHANGELOG.md.
"""

from typing import Literal

from pydantic import BaseModel

# The five suppression actions. Shared by ActionResult (output) and ApplyIn (input) so they match.
ActionName = Literal["fans_off", "cut_power", "co2", "water_mist", "fans_off_co2"]


# --- Contract models (exactly as in the plan) ---


class TestRef(BaseModel):
    """One NASA test row, shown as a source/citation next to a verdict."""

    # Not a pytest test class, despite the name: stops pytest trying to collect it.
    __test__ = False

    test_id: str
    investigation: str
    fuel_type: str
    o2_pct: float | None  # None = the source didn't report it
    pressure_kpa: float | None
    flow_cm_s: float | None
    outcome: Literal["burned", "extinguished", "unknown"]
    source_url: str
    is_synthetic: bool = False  # True = placeholder row; the UI must show a "synthetic" badge


class ScenarioIn(BaseModel):
    """What the user sets up before pressing Ignite."""

    module: Literal["iss_lab"] = "iss_lab"  # only the ISS lab module in the 24-hour scope
    material: str  # from MetaOut.materials
    o2_pct: float  # 10-40
    pressure_kpa: float = 101.3
    flow_speed_cm_s: float  # 0-40
    flow_dir: tuple[float, float, float] = (1, 0, 0)


class SimulateOut(BaseModel):
    """The model's verdict for one scenario (from /simulate and /apply)."""

    scenario_id: str
    state: Literal["burning", "extinguished"]
    burn_probability: float  # 0-1
    spread_rate_mm_s: float | None  # None = not enough data to predict spread
    trust: Literal["strong", "medium", "weak"]
    extrapolated: bool  # outside tested ranges
    nearest_tests: list[TestRef]  # top 3
    explanation: str  # one grounded sentence
    inputs: ScenarioIn


class PreviewOut(BaseModel):
    """The model's verdict for some inputs, without starting a scenario (POST /preview).

    For live views (the 3D scene while sliders move, the O2 chart): no scenario_id, no history
    row and no written explanation, so it is fast and leaves /results untouched.
    """

    state: Literal["burning", "extinguished"]
    burn_probability: float  # 0-1, the same model and threshold as /simulate
    trust: Literal["strong", "medium", "weak"]
    extrapolated: bool  # outside tested ranges
    is_synthetic: bool  # true only in mock mode (rule 5: label placeholder numbers)
    inputs: ScenarioIn


class DetectOut(BaseModel):
    """When and where the smoke alarm trips."""

    detected: bool
    detector_id: str | None  # None = no detector tripped
    time_to_detect_s: float | None  # None = never reaches a detector
    detectors: list[dict]  # id, position [x,y,z], peak_concentration
    note: str  # e.g. "fans off: smoke cannot reach vents"


class ActionResult(BaseModel):
    """One ranked suppression option."""

    action: ActionName
    label: str
    new_inputs: ScenarioIn
    extinction_probability: float
    crew_risk: float
    score: float
    data_support: Literal["direct", "indirect", "none"]
    sources: list[TestRef]
    explanation: str


class SuppressOut(BaseModel):
    """All suppression options for a scenario, best first."""

    scenario_id: str
    recommended: str
    # Best first: actions with NASA data support by score, then those without (water_mist last).
    actions: list[ActionResult]


class ResultsOut(BaseModel):
    """The results table for one scenario."""

    scenario_id: str
    rows: list[dict]  # step, inputs, state, probability, trust, detection_s, action, sources


class ChatOut(BaseModel):
    """A chatbot answer plus the NASA sources it used."""

    answer: str
    citations: list[dict]  # title, investigation, source_url, snippet


class MetaOut(BaseModel):
    """Options the UI needs to build its controls."""

    materials: list[dict]  # name, fuel_type, n_tests
    ranges: dict  # min/max per feature in training data
    investigations: list[dict]


# --- Request/response bodies the contract table writes inline (e.g. "{scenario_id}") ---


class ScenarioRef(BaseModel):
    """Body of POST /detect and POST /suppress: {scenario_id}."""

    scenario_id: str


class ApplyIn(BaseModel):
    """Body of POST /apply: {scenario_id, action}."""

    scenario_id: str
    action: ActionName


class ChatIn(BaseModel):
    """Body of POST /chat: {message, scenario_id?}."""

    message: str
    scenario_id: str | None = None  # None = general question, not about a running scenario


class HealthOut(BaseModel):
    """Response of GET /health: {status}."""

    status: str
