"""BE-05 contract regression tests, transcribed from the plan rather than generated from code.

A deliberate contract change requires team agreement, regenerated frontend types, a changelog
entry, and an update to these expectations.
"""

from typing import Literal, get_args

import pytest
from pydantic import ValidationError

from app import schemas

# Explicit types also pin the Literal values and the direction tuple's length.
CONTRACT_TYPES = {
    "TestRef": {
        "test_id": str,
        "investigation": str,
        "fuel_type": str,
        "o2_pct": float | None,
        "pressure_kpa": float | None,
        "flow_cm_s": float | None,
        "outcome": Literal["burned", "extinguished", "unknown"],
        "source_url": str,
        "is_synthetic": bool,
    },
    "ScenarioIn": {
        "module": Literal["iss_lab"],
        "material": str,
        "o2_pct": float,
        "pressure_kpa": float,
        "flow_speed_cm_s": float,
        "flow_dir": tuple[float, float, float],
    },
    "SimulateOut": {
        "scenario_id": str,
        "state": Literal["burning", "extinguished"],
        "burn_probability": float,
        "spread_rate_mm_s": float | None,
        "trust": Literal["strong", "medium", "weak"],
        "extrapolated": bool,
        "nearest_tests": list[schemas.TestRef],
        "explanation": str,
        "inputs": schemas.ScenarioIn,
    },
    "DetectOut": {
        "detected": bool,
        "detector_id": str | None,
        "time_to_detect_s": float | None,
        "detectors": list[dict],
        "note": str,
    },
    "ActionResult": {
        "action": Literal["fans_off", "cut_power", "co2", "water_mist", "fans_off_co2"],
        "label": str,
        "new_inputs": schemas.ScenarioIn,
        "extinction_probability": float,
        "crew_risk": float,
        "score": float,
        "data_support": Literal["direct", "indirect", "none"],
        "sources": list[schemas.TestRef],
        "explanation": str,
    },
    "SuppressOut": {"scenario_id": str, "recommended": str, "actions": list[schemas.ActionResult]},
    "ResultsOut": {"scenario_id": str, "rows": list[dict]},
    "ChatOut": {"answer": str, "citations": list[dict]},
    # ranges_by_fuel_type: added after the plan (FE-09 fixes, see docs/contract.md "GET /meta").
    "MetaOut": {
        "materials": list[dict],
        "ranges": dict,
        "ranges_by_fuel_type": dict[str, dict],
        "investigations": list[dict],
    },
    # Named versions of the endpoint table's inline bodies.
    "ScenarioRef": {"scenario_id": str},
    "ApplyIn": {
        "scenario_id": str,
        "action": Literal["fans_off", "cut_power", "co2", "water_mist", "fans_off_co2"],
    },
    "ChatIn": {"message": str, "scenario_id": str | None},
    "HealthOut": {"status": str},
}

CONTRACT_DEFAULTS = {
    ("TestRef", "is_synthetic"): False,
    ("ScenarioIn", "module"): "iss_lab",
    ("ScenarioIn", "pressure_kpa"): 101.3,
    ("ScenarioIn", "flow_dir"): (1, 0, 0),
    ("ChatIn", "scenario_id"): None,
}

SCENARIO = {"material": "cotton", "o2_pct": 21, "flow_speed_cm_s": 10}
PAYLOADS = {
    "TestRef": {
        "test_id": "synthetic-T1",
        "investigation": "fixture",
        "fuel_type": "solid",
        "o2_pct": None,
        "pressure_kpa": None,
        "flow_cm_s": None,
        "outcome": "unknown",
        "source_url": "https://example.com",
        "is_synthetic": True,
    },
    "ScenarioIn": SCENARIO,
    "SimulateOut": {
        "scenario_id": "s1",
        "state": "burning",
        "burn_probability": 0.5,
        "spread_rate_mm_s": None,
        "trust": "weak",
        "extrapolated": True,
        "nearest_tests": [],
        "explanation": "Synthetic test fixture.",
        "inputs": SCENARIO,
    },
    "DetectOut": {
        "detected": False,
        "detector_id": None,
        "time_to_detect_s": None,
        "detectors": [],
        "note": "Synthetic test fixture.",
    },
    "ActionResult": {
        "action": "fans_off",
        "label": "Fans off",
        "new_inputs": SCENARIO,
        "extinction_probability": 0.5,
        "crew_risk": 0,
        "score": 0.5,
        "data_support": "none",
        "sources": [],
        "explanation": "Synthetic test fixture.",
    },
    "ApplyIn": {"scenario_id": "s1", "action": "fans_off"},
    "ChatIn": {"message": "Why did fans off work?"},
}
NULLABLE_REQUIRED = [
    ("TestRef", "o2_pct"),
    ("TestRef", "pressure_kpa"),
    ("TestRef", "flow_cm_s"),
    ("SimulateOut", "spread_rate_mm_s"),
    ("DetectOut", "detector_id"),
    ("DetectOut", "time_to_detect_s"),
]
LITERAL_FIELDS = [
    ("TestRef", "outcome"),
    ("ScenarioIn", "module"),
    ("SimulateOut", "state"),
    ("SimulateOut", "trust"),
    ("ActionResult", "action"),
    ("ActionResult", "data_support"),
    ("ApplyIn", "action"),
]


@pytest.mark.parametrize("model_name", CONTRACT_TYPES)
def test_contract_fields_match_plan(model_name: str) -> None:
    assert list(getattr(schemas, model_name).model_fields) == list(CONTRACT_TYPES[model_name])


@pytest.mark.parametrize("model_name", CONTRACT_TYPES)
def test_contract_field_types_match_plan(model_name: str) -> None:
    fields = getattr(schemas, model_name).model_fields
    assert {name: field.annotation for name, field in fields.items()} == CONTRACT_TYPES[model_name]


@pytest.mark.parametrize("model_name", CONTRACT_TYPES)
def test_contract_required_fields_match_plan(model_name: str) -> None:
    fields = getattr(schemas, model_name).model_fields
    optional = {field for model, field in CONTRACT_DEFAULTS if model == model_name}
    assert {name for name, field in fields.items() if field.is_required()} == (
        set(CONTRACT_TYPES[model_name]) - optional
    )


@pytest.mark.parametrize("model_name,field_name", CONTRACT_DEFAULTS)
def test_contract_default_matches_plan(model_name: str, field_name: str) -> None:
    payload = {key: value for key, value in PAYLOADS[model_name].items() if key != field_name}
    result = getattr(schemas, model_name).model_validate(payload)
    assert getattr(result, field_name) == CONTRACT_DEFAULTS[model_name, field_name]


@pytest.mark.parametrize("model_name,field_name", NULLABLE_REQUIRED)
def test_required_nullable_field_accepts_null(model_name: str, field_name: str) -> None:
    payload = {**PAYLOADS[model_name], field_name: None}
    result = getattr(schemas, model_name).model_validate(payload)
    assert getattr(result, field_name) is None


@pytest.mark.parametrize("model_name,field_name", NULLABLE_REQUIRED)
def test_required_nullable_field_cannot_be_omitted(model_name: str, field_name: str) -> None:
    payload = {key: value for key, value in PAYLOADS[model_name].items() if key != field_name}
    with pytest.raises(ValidationError) as error:
        getattr(schemas, model_name).model_validate(payload)
    assert any(
        item["loc"] == (field_name,) and item["type"] == "missing" for item in error.value.errors()
    )


@pytest.mark.parametrize(
    "model_name,field_name,value",
    [
        (model, field, value)
        for model, field in LITERAL_FIELDS
        for value in get_args(CONTRACT_TYPES[model][field])
    ],
)
def test_contract_literal_accepts_planned_value(
    model_name: str, field_name: str, value: str
) -> None:
    result = getattr(schemas, model_name).model_validate(
        {**PAYLOADS[model_name], field_name: value}
    )
    assert getattr(result, field_name) == value


@pytest.mark.parametrize("model_name,field_name", LITERAL_FIELDS)
def test_contract_literal_rejects_unlisted_value(model_name: str, field_name: str) -> None:
    with pytest.raises(ValidationError):
        getattr(schemas, model_name).model_validate({**PAYLOADS[model_name], field_name: "invalid"})


@pytest.mark.parametrize("field_name", ["material", "o2_pct", "flow_speed_cm_s"])
def test_scenario_requires_input(field_name: str) -> None:
    with pytest.raises(ValidationError):
        schemas.ScenarioIn.model_validate(
            {key: value for key, value in SCENARIO.items() if key != field_name}
        )


@pytest.mark.parametrize("direction", [[], [1, 0], [1, 0, 0, 0], ["bad", 0, 0]])
def test_flow_direction_rejects_invalid_vector(direction: list) -> None:
    with pytest.raises(ValidationError):
        schemas.ScenarioIn.model_validate({**SCENARIO, "flow_dir": direction})


def test_flow_direction_accepts_three_json_numbers() -> None:
    result = schemas.ScenarioIn.model_validate({**SCENARIO, "flow_dir": [0, -1, 0]})
    assert result.flow_dir == (0, -1, 0)


@pytest.mark.parametrize("scenario_id", [None, "s1"])
def test_chat_accepts_optional_scenario_id(scenario_id: str | None) -> None:
    assert schemas.ChatIn(message="Why?", scenario_id=scenario_id).scenario_id == scenario_id
