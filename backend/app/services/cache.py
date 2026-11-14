"""BE-11: bounded, process-local memoization of prediction plus grounded explanation."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass

from app.schemas import ScenarioIn, TestRef
from app.services import predictor, rag
from ml.pipeline import config

MAX_ENTRIES = 256
TTL_S = 60.0
Prediction = tuple[float, float | None, str, bool, list[TestRef]]
Result = tuple[Prediction, str]


@dataclass
class _Entry:
    result: Result
    expires_at: float


_lock = threading.Lock()
_entries: OrderedDict[str, _Entry] = OrderedDict()
_pending: dict[tuple[int, str], Future[Result]] = {}
_generation = 0


def _normalized(inputs: ScenarioIn) -> ScenarioIn:
    # Validate explicit defaults too, so default (1, 0, 0) and explicit float vectors hash alike.
    return ScenarioIn.model_validate(inputs.model_dump())


def input_hash(inputs: ScenarioIn) -> str:
    """SHA-256 of every scenario field, independent of JSON field order or omitted defaults."""
    payload = json.dumps(
        _normalized(inputs).model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _key(inputs: ScenarioIn) -> str:
    # Explanations depend on online/offline mode and model selection. Never retain API keys.
    context = (
        input_hash(inputs),
        bool(os.getenv("OPENAI_API_KEY", "").strip()),
        bool(os.getenv("GEMINI_API_KEY", "").strip()),
        os.getenv("OPENAI_MODEL", ""),
        os.getenv("GEMINI_MODEL", ""),
        config.BURN_THRESHOLD,
    )
    return hashlib.sha256(json.dumps(context).encode()).hexdigest()


def _compute(inputs: ScenarioIn) -> Result:
    prediction = predictor.predict(inputs)
    prob, _, trust, extrapolated, nearest = prediction
    explanation = rag.explain(
        {
            "inputs": inputs,
            "state": "burning" if prob >= config.BURN_THRESHOLD else "extinguished",
            "burn_probability": prob,
            "trust": trust,
            "extrapolated": extrapolated,
            "nearest_tests": nearest,
        }
    )
    return prediction, explanation


def predict_and_explain(inputs: ScenarioIn) -> Result:
    """Reuse identical inputs for 60 s; concurrent identical misses share one computation.

    Every caller receives a deep copy. Failures are never cached. Expiry starts after the
    computation finishes; different inputs do not wait on one another's prediction/LLM call.
    """
    snapshot = _normalized(inputs)
    key = _key(snapshot)
    with _lock:
        now = time.monotonic()
        entry = _entries.get(key)
        if entry is not None:
            if entry.expires_at > now:
                _entries.move_to_end(key)
                return deepcopy(entry.result)
            del _entries[key]
        generation = _generation
        pending_key = (generation, key)
        future = _pending.get(pending_key)
        owner = future is None
        if owner:
            future = Future()
            _pending[pending_key] = future
    if not owner:
        return deepcopy(future.result())
    try:
        result = _compute(snapshot)
        stored = deepcopy(result)
    except BaseException as error:
        # Wake waiters even on cancellation; do not strand an in-flight key or cache an error.
        with _lock:
            _pending.pop(pending_key, None)
            future.set_exception(error)
        raise
    with _lock:
        if generation == _generation:
            _entries[key] = _Entry(stored, time.monotonic() + TTL_S)
            _entries.move_to_end(key)
            while len(_entries) > MAX_ENTRIES:
                _entries.popitem(last=False)
        _pending.pop(pending_key, None)
        future.set_result(stored)
    return deepcopy(stored)


def clear() -> None:
    """Invalidate entries and detach in-flight work; old computations cannot refill the cache.

    Callers already waiting on old work still receive its result. This does not reload model
    artifacts or data: restart the backend after rebuilding those files.
    """
    global _generation
    with _lock:
        _generation += 1
        _entries.clear()
        _pending.clear()
