"""BE-06 fixtures. All scientific-looking values are synthetic UI placeholders.

The scenario, inputs, action outcomes and history are fixed, regardless of request contents.
Reserved example.com links identify placeholders; they do not cite NASA investigations.
"""

from app.schemas import (
    ActionResult,
    ChatOut,
    DetectOut,
    MetaOut,
    ResultsOut,
    ScenarioIn,
    SimulateOut,
    SuppressOut,
    TestRef,
)

SCENARIO_ID = "synthetic-scenario-001"
INPUTS = ScenarioIn(material="Synthetic cotton", o2_pct=21, flow_speed_cm_s=10)
SOURCES = [
    TestRef(
        test_id=f"synthetic-test-{number:03d}",
        investigation="Synthetic fixture (not NASA data)",
        fuel_type="solid",
        o2_pct=21,
        pressure_kpa=101.3,
        flow_cm_s=10,
        outcome="unknown",
        source_url="https://example.com",
        is_synthetic=True,
    )
    for number in range(1, 4)
]

META = MetaOut(
    materials=[{"name": INPUTS.material, "fuel_type": "solid", "n_tests": 3, "is_synthetic": True}],
    ranges={
        "o2_pct": {"min": 10, "max": 40, "is_synthetic": True},
        "pressure_kpa": {"min": 80, "max": 110, "is_synthetic": True},
        "flow_cm_s": {"min": 0, "max": 40, "is_synthetic": True},
    },
    investigations=[
        {
            "name": "Synthetic fixture (not NASA data)",
            "pillar": "prevention",
            "objective": "Synthetic mock data for UI development only.",
            "source_url": "https://example.com",
            "is_synthetic": True,
        }
    ],
)
SIMULATE = SimulateOut(
    scenario_id=SCENARIO_ID,
    state="burning",
    burn_probability=0.8,
    spread_rate_mm_s=0.5,
    trust="weak",
    extrapolated=True,
    nearest_tests=SOURCES,
    explanation="Synthetic mock: fixed inputs and fire outcome for UI development, not NASA data.",
    inputs=INPUTS,
)
DETECT = DetectOut(
    detected=True,
    detector_id="synthetic-vent-1",
    time_to_detect_s=12.5,
    detectors=[
        {
            "id": "synthetic-vent-1",
            "position": [4, 0, 0],
            "peak_concentration": 0.8,
            "is_synthetic": True,
        },
        {
            "id": "synthetic-vent-2",
            "position": [-4, 0, 0],
            "peak_concentration": 0.02,
            "is_synthetic": True,
        },
    ],
    note="Synthetic mock: detector positions, concentrations and timing are fixed placeholders.",
)

FANS_OFF_INPUTS = INPUTS.model_copy(update={"flow_speed_cm_s": 0})
CO2_INPUTS = INPUTS.model_copy(update={"o2_pct": 15})
COMBINED_INPUTS = INPUTS.model_copy(update={"o2_pct": 15, "flow_speed_cm_s": 0})
SUPPRESS = SuppressOut(
    scenario_id=SCENARIO_ID,
    recommended="fans_off_co2",
    actions=[
        ActionResult(
            action=action,
            label=f"Synthetic: {label}",
            new_inputs=inputs,
            extinction_probability=extinction,
            crew_risk=risk,
            score=score,
            data_support="none",
            sources=SOURCES,
            explanation=(
                "Synthetic mock: fixed ranking and scores; no NASA evidence or safety advice."
            ),
        )
        for action, label, inputs, extinction, risk, score in [
            ("fans_off_co2", "Fans off + CO2", COMBINED_INPUTS, 0.9, 0.1, 0.8),
            ("fans_off", "Fans off", FANS_OFF_INPUTS, 0.75, 0.05, 0.7),
            ("co2", "CO2", CO2_INPUTS, 0.8, 0.2, 0.6),
            ("cut_power", "Cut power", INPUTS, 0.2, 0, 0.2),
            ("water_mist", "Water mist", INPUTS, 0.1, 0.1, 0),
        ]
    ],
)
APPLY = SimulateOut(
    scenario_id=SCENARIO_ID,
    state="extinguished",
    burn_probability=0.1,
    spread_rate_mm_s=None,
    trust="weak",
    extrapolated=True,
    nearest_tests=SOURCES,
    explanation=(
        "Synthetic mock: this fixed fans-off + CO2 outcome ignores the selected action; "
        "it is not a prediction."
    ),
    inputs=COMBINED_INPUTS,
)
# Same shape as rows from the real store (services/store.py, BE-01): the plan's 8 keys, `step`
# named "simulate"/"detect"/"apply", `sources` as test ids, None where a step made no value.
# test_mocks.py checks this by feeding each row through the real store.
_SOURCE_IDS = [source.test_id for source in SOURCES]
RESULTS = ResultsOut(
    scenario_id=SCENARIO_ID,
    rows=[
        {  # 1: simulate
            "step": "simulate",
            "inputs": INPUTS.model_dump(mode="json"),
            "state": SIMULATE.state,
            "probability": SIMULATE.burn_probability,
            "trust": SIMULATE.trust,
            "detection_s": None,
            "action": None,
            "sources": _SOURCE_IDS,
        },
        {  # 2: detect (no new verdict, only the detection time)
            "step": "detect",
            "inputs": INPUTS.model_dump(mode="json"),
            "state": None,
            "probability": None,
            "trust": None,
            "detection_s": DETECT.time_to_detect_s,
            "action": None,
            "sources": _SOURCE_IDS,
        },
        {  # 3: apply the recommended action
            "step": "apply",
            "inputs": APPLY.inputs.model_dump(mode="json"),
            "state": APPLY.state,
            "probability": APPLY.burn_probability,
            "trust": APPLY.trust,
            "detection_s": None,
            "action": SUPPRESS.recommended,
            "sources": _SOURCE_IDS,
        },
    ],
)
CHAT = ChatOut(
    answer=(
        "Synthetic mock: this fixed answer and its citations are placeholders for UI development. "
        "No NASA data or language model was consulted."
    ),
    citations=[
        {
            "title": "Synthetic fixture (not NASA evidence)",
            "investigation": "Synthetic fixture (not NASA data)",
            "source_url": "https://example.com",
            "snippet": "Synthetic mock citation for layout testing only.",
            "is_synthetic": True,
        }
    ],
)
