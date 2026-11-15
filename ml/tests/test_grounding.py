"""Grounding check used by the explainer, the chat and the agents' critic."""

from ml.pipeline import grounding

PAYLOAD = {
    "prediction": {"state": "burning", "burn_probability": 0.5137, "trust": "medium"},
    "inputs": {"material": "Heptane", "o2_pct": 30.0, "pressure_kpa": 101.3},
    "nearest_tests": [
        {"test_id": "FLEX-44", "investigation": "FLEX", "o2_pct": 30.0, "outcome": "burned"}
    ],
}
IDS = ["FLEX-44"]


def test_a_faithful_sentence_passes() -> None:
    text = "At 30 % O2 the fire keeps burning (probability 0.51, 51 %), like FLEX test FLEX-44."
    assert grounding.check_explanation(text, PAYLOAD, IDS) == []


def test_an_invented_number_is_caught() -> None:
    problems = grounding.check("Spread is 4.7 mm/s near FLEX-44.", PAYLOAD, IDS)
    assert problems == ["number 4.7 is not in the input"]


def test_rounding_must_match_the_digits_shown() -> None:
    assert grounding.check("probability 0.514", PAYLOAD, IDS) == []
    assert grounding.check("probability 0.52", PAYLOAD, IDS) != []


def test_an_invented_test_and_investigation_are_caught() -> None:
    problems = grounding.check("Saffire-II test Saffire-II-2-5 also burned.", PAYLOAD, IDS)
    assert "test Saffire-II-2-5 was not given" in problems
    assert "investigation Saffire-II is not in the input" in problems


def test_formulas_and_id_digits_are_not_numbers() -> None:
    assert grounding.numbers_in("CO2 and O2 near FLEX-44 at 30 %") == ["30"]


def test_explanation_must_name_a_given_test() -> None:
    assert grounding.check_explanation("It burns at 30 % O2.", PAYLOAD, IDS) == [
        "names none of the given tests"
    ]


def test_citations_out_of_range_are_caught() -> None:
    assert grounding.check_citations("FLEX used CO2 [1][3].", 2) == ["citation [3] does not exist"]


def test_ids_that_contain_another_id_are_matched_whole() -> None:
    payload = {"nearest_tests": [{"test_id": "SYN-BASS-II-12", "o2_pct": 20.0}]}
    text = "Test SYN-BASS-II-12 burned at 20 % O2."
    assert grounding.check_explanation(text, payload, ["SYN-BASS-II-12"]) == []
