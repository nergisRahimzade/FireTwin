"""BE-11: cache hits, complete input keys, expiry, isolation, failure and concurrent work."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.schemas import ScenarioIn, TestRef
from app.services import cache, predictor, rag

INPUTS = ScenarioIn(material="Synthetic cache fixture", o2_pct=21, flow_speed_cm_s=10)
SOURCE = TestRef(
    test_id="synthetic-cache-001",
    investigation="Synthetic cache fixture",
    fuel_type="solid",
    o2_pct=21,
    pressure_kpa=101.3,
    flow_cm_s=10,
    outcome="burned",
    source_url="https://example.com/synthetic-cache",
    is_synthetic=True,
)


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    cache.clear()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    yield
    cache.clear()


@pytest.fixture
def calls(monkeypatch):
    seen = {"predict": [], "explain": []}

    def predict(inputs):
        seen["predict"].append(inputs.model_copy(deep=True))
        return 0.8, None, "weak", True, [SOURCE.model_copy(deep=True)]

    def explain(result):
        seen["explain"].append(result)
        return "Synthetic cached explanation."

    monkeypatch.setattr(predictor, "predict", predict)
    monkeypatch.setattr(rag, "explain", explain)
    return seen


def test_repeated_inputs_reuse_prediction_and_explanation(calls):
    first = cache.predict_and_explain(INPUTS)
    second = cache.predict_and_explain(INPUTS.model_copy(deep=True))
    assert first == second
    assert len(calls["predict"]) == len(calls["explain"]) == 1


def test_hash_is_stable_for_defaults_and_json_field_order():
    explicit = ScenarioIn.model_validate(
        {
            "flow_dir": [1.0, 0.0, 0.0],
            "flow_speed_cm_s": 10.0,
            "pressure_kpa": 101.3,
            "o2_pct": 21.0,
            "material": "Synthetic cache fixture",
            "module": "iss_lab",
        }
    )
    assert cache.input_hash(INPUTS) == cache.input_hash(explicit)
    assert len(cache.input_hash(INPUTS)) == 64


@pytest.mark.parametrize(
    "update",
    [
        {"material": "Another synthetic fixture"},
        {"o2_pct": 22},
        {"pressure_kpa": 80},
        {"flow_speed_cm_s": 0},
        {"flow_dir": (0, 1, 0)},
    ],
)
def test_each_changed_input_gets_a_separate_entry(calls, update):
    cache.predict_and_explain(INPUTS)
    cache.predict_and_explain(INPUTS.model_copy(update=update))
    assert len(calls["predict"]) == len(calls["explain"]) == 2


def test_explainer_receives_the_original_prediction(calls):
    cache.predict_and_explain(INPUTS)
    result = calls["explain"][0]
    assert result == {
        "inputs": INPUTS,
        "state": "burning",
        "burn_probability": 0.8,
        "trust": "weak",
        "extrapolated": True,
        "nearest_tests": [SOURCE],
    }


def test_caller_cannot_mutate_the_cached_sources(calls):
    prediction, _ = cache.predict_and_explain(INPUTS)
    prediction[4][0].test_id = "synthetic-mutation"
    prediction[4].clear()
    second, _ = cache.predict_and_explain(INPUTS)
    assert second[4] == [SOURCE]


def test_cache_detaches_results_from_service_owned_objects(monkeypatch):
    sources = [SOURCE.model_copy(deep=True)]
    monkeypatch.setattr(predictor, "predict", lambda inputs: (0.8, None, "weak", True, sources))
    monkeypatch.setattr(rag, "explain", lambda result: "Synthetic explanation.")
    cache.predict_and_explain(INPUTS)
    sources[0].test_id = "synthetic-service-mutation"
    assert cache.predict_and_explain(INPUTS)[0][4] == [SOURCE]


def test_expired_entry_recomputes_both_services(calls, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: clock[0])
    cache.predict_and_explain(INPUTS)
    clock[0] += cache.TTL_S
    cache.predict_and_explain(INPUTS)
    assert len(calls["predict"]) == len(calls["explain"]) == 2


def test_expiry_starts_after_computation_finishes(calls, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: clock[0])
    explain = rag.explain

    def slow_explain(result):
        clock[0] += cache.TTL_S + 1
        return explain(result)

    monkeypatch.setattr(rag, "explain", slow_explain)
    cache.predict_and_explain(INPUTS)
    cache.predict_and_explain(INPUTS)
    assert len(calls["predict"]) == 1


def test_least_recently_used_entry_is_evicted(calls, monkeypatch):
    monkeypatch.setattr(cache, "MAX_ENTRIES", 2)
    second = INPUTS.model_copy(update={"o2_pct": 22})
    third = INPUTS.model_copy(update={"o2_pct": 23})
    for inputs in [INPUTS, second, INPUTS, third, second]:
        cache.predict_and_explain(inputs)
    assert [i.o2_pct for i in calls["predict"]] == [21, 22, 23, 22]


@pytest.mark.parametrize("service", ["predict", "explain"])
def test_service_failures_are_not_cached(calls, monkeypatch, service):
    module = predictor if service == "predict" else rag
    original = getattr(module, service)
    attempts = []

    def flaky(value):
        attempts.append(value)
        if len(attempts) == 1:
            raise RuntimeError("Synthetic transient error")
        return original(value)

    monkeypatch.setattr(module, service, flaky)
    with pytest.raises(RuntimeError, match="Synthetic transient"):
        cache.predict_and_explain(INPUTS)
    assert cache.predict_and_explain(INPUTS)[1] == "Synthetic cached explanation."
    assert len(attempts) == 2


@pytest.mark.parametrize(
    "name,value",
    [
        ("OPENAI_API_KEY", "synthetic-test-key-not-real"),
        ("GEMINI_API_KEY", "synthetic-test-key-not-real"),
        ("OPENAI_MODEL", "synthetic-other-model"),
        ("GEMINI_MODEL", "synthetic-other-model"),
    ],
)
def test_llm_mode_or_model_change_misses_the_old_entry(calls, monkeypatch, name, value):
    cache.predict_and_explain(INPUTS)
    monkeypatch.setenv(name, value)
    cache.predict_and_explain(INPUTS)
    assert len(calls["predict"]) == len(calls["explain"]) == 2


def test_blank_key_is_still_offline(calls, monkeypatch):
    cache.predict_and_explain(INPUTS)
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    cache.predict_and_explain(INPUTS)
    assert len(calls["predict"]) == 1


def test_clear_invalidates_completed_entries(calls):
    cache.predict_and_explain(INPUTS)
    cache.clear()
    cache.predict_and_explain(INPUTS)
    assert len(calls["predict"]) == 2


def test_concurrent_identical_requests_share_one_computation(calls, monkeypatch):
    started, release = threading.Event(), threading.Event()
    predict = predictor.predict

    def held(inputs):
        started.set()
        assert release.wait(3), "worker timed out"
        return predict(inputs)

    monkeypatch.setattr(predictor, "predict", held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.predict_and_explain, INPUTS)
        assert started.wait(3)
        second = pool.submit(cache.predict_and_explain, INPUTS)
        release.set()
        assert first.result(timeout=3) == second.result(timeout=3)
    assert len(calls["predict"]) == len(calls["explain"]) == 1


def test_different_inputs_compute_concurrently(calls, monkeypatch):
    barrier = threading.Barrier(2)
    predict = predictor.predict

    def together(inputs):
        barrier.wait(timeout=3)
        return predict(inputs)

    monkeypatch.setattr(predictor, "predict", together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = [
            pool.submit(cache.predict_and_explain, inputs)
            for inputs in [
                INPUTS,
                INPUTS.model_copy(update={"o2_pct": 22}),
            ]
        ]
        assert all(f.result(timeout=3)[1] for f in work)
    assert len(calls["predict"]) == 2


def test_clear_during_computation_does_not_restore_old_entry(calls, monkeypatch):
    started, release = threading.Event(), threading.Event()
    predict = predictor.predict

    def held(inputs):
        started.set()
        assert release.wait(3), "worker timed out"
        return predict(inputs)

    monkeypatch.setattr(predictor, "predict", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old = pool.submit(cache.predict_and_explain, INPUTS)
        assert started.wait(3)
        cache.clear()
        release.set()
        assert old.result(timeout=3)[1]
    cache.predict_and_explain(INPUTS)
    assert len(calls["predict"]) == 2
