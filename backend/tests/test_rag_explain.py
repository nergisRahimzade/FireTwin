"""ML-06: grounded explainer, with and without an LLM key (the LLM itself is faked)."""

import pytest

from app.schemas import ScenarioIn
from app.services import predictor, rag

BASE = ScenarioIn(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def _result(inputs: ScenarioIn = BASE) -> dict:
    prob, spread, trust, extrapolated, nearest = predictor.predict(inputs)
    return {
        "inputs": inputs,
        "state": "burning" if prob >= 0.5 else "extinguished",
        "burn_probability": prob,
        "trust": trust,
        "extrapolated": extrapolated,
        "nearest_tests": nearest,
    }


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


def test_without_a_key_the_template_names_the_nearest_test(no_key) -> None:
    result = _result()
    text = rag.explain(result)
    first = result["nearest_tests"][0]
    assert first.test_id in text and first.investigation in text
    assert f"{result['burn_probability']:.2f}" in text
    assert text.count(".") >= 1 and text.endswith(".")


def test_template_labels_synthetic_rows(no_key) -> None:
    assert "synthetic placeholder" in rag.explain(_result())


def test_template_flags_extrapolation(no_key) -> None:
    text = rag.explain(_result(BASE.model_copy(update={"o2_pct": 34.0})))
    assert "no direct NASA data" in text


def test_an_empty_key_counts_as_missing(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    assert rag.llm_available() is False


def test_llm_sees_only_the_given_tests_and_its_answer_is_used(with_key, monkeypatch) -> None:
    result = _result()
    test_id = result["nearest_tests"][0].test_id
    seen = {}

    def fake_chat(system: str, user: str) -> str:
        seen["system"], seen["user"] = system, user
        return f"Test {test_id} burned under similar conditions."

    monkeypatch.setattr(rag, "_chat", fake_chat)
    assert rag.explain(result) == f"Test {test_id} burned under similar conditions."
    assert "ONE sentence" in seen["system"]
    assert all(t.test_id in seen["user"] for t in result["nearest_tests"])


def test_llm_answer_citing_no_given_test_is_replaced_by_the_template(with_key, monkeypatch) -> None:
    monkeypatch.setattr(rag, "_chat", lambda system, user: "Apollo test 99 proves it burns.")
    result = _result()
    assert result["nearest_tests"][0].test_id in rag.explain(result)


def test_llm_failure_falls_back_to_the_template(with_key, monkeypatch) -> None:
    def boom(system: str, user: str) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(rag, "_chat", boom)
    result = _result()
    assert result["nearest_tests"][0].test_id in rag.explain(result)


def test_bad_payload_raises_instead_of_hiding_the_bug(no_key) -> None:
    with pytest.raises(KeyError):
        rag.explain({"inputs": BASE})
