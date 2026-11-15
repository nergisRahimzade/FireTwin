"""ML-10: offline fallback texts (no LLM, no network)."""

from app.services import fallback

TEST = {
    "test_id": "FLEX-4",
    "investigation": "FLEX",
    "o2_pct": 21.0,
    "flow_cm_s": 0.0,
    "outcome": "extinguished",
    "is_synthetic": False,
}
RESULT = {
    "state": "extinguished",
    "burn_probability": 0.16,
    "trust": "strong",
    "extrapolated": False,
    "nearest_tests": [TEST],
}
CHUNK = {"title": "t", "investigation": "FLEX", "source_url": "https://x", "snippet": "A b c."}


def test_explanation_names_the_nearest_nasa_test() -> None:
    text = fallback.explanation(RESULT)
    assert "goes out" in text and "0.16" in text and "trust strong" in text
    assert "NASA test FLEX-4 (FLEX, 21 % O2, 0 cm/s flow) extinguished" in text


def test_explanation_handles_missing_values_and_unknown_outcomes() -> None:
    test = {**TEST, "flow_cm_s": None, "outcome": "unknown"}
    text = fallback.explanation({**RESULT, "nearest_tests": [test]})
    assert "(FLEX, 21 % O2) has no recorded outcome" in text
    assert "None" not in text


def test_explanation_labels_synthetic_tests_and_extrapolation() -> None:
    test = {**TEST, "is_synthetic": True}
    text = fallback.explanation({**RESULT, "extrapolated": True, "nearest_tests": [test]})
    assert "synthetic placeholder test" in text
    assert "no direct NASA data" in text


def test_explanation_without_any_test_says_so() -> None:
    assert "no nearby NASA test" in fallback.explanation({**RESULT, "nearest_tests": []})


def test_chat_answer_is_the_top_chunk_with_its_citation() -> None:
    text, citations = fallback.chat_answer([CHUNK, {**CHUNK, "snippet": "other"}], 120)
    assert text == "A b c. (source: FLEX)"
    assert citations == [CHUNK]


def test_chat_answer_is_cut_to_the_word_limit() -> None:
    long_chunk = {**CHUNK, "snippet": "word " * 300}
    text, _ = fallback.chat_answer([long_chunk], 120)
    assert len(text.split()) == 121 and text.endswith("...")


def test_chat_answer_without_chunks_says_nothing_relevant() -> None:
    assert fallback.chat_answer([], 120) == (fallback.NOTHING_RELEVANT, [])
