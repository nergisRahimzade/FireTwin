"""Grounded LLM service (ML-06 explain, ML-07 answer).

The LLM only ever sees the nearest NASA tests and retrieved report passages, and its output is
checked against them. With no OPENAI_API_KEY, or when a call fails, a template built from the
same data is returned instead, so the demo never crashes. No FastAPI imports.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.schemas import ChatOut
from ml.pipeline import config, stages

log = logging.getLogger(__name__)

PROMPTS_DIR = config.ROOT / "ml" / "prompts"
EXPLAIN_PROMPT = PROMPTS_DIR / "explain_v1.txt"
DEFAULT_MODEL = "gpt-4o-mini"  # override with the OPENAI_MODEL environment variable
LLM_TIMEOUT_S = 20.0
EXPLAIN_TOP_K = 3
DOCS_DIR = config.DOCS_DIR  # data/docs/<investigation>/*.txt (DAT-07)
CHAT_PROMPT = PROMPTS_DIR / "chat_v1.txt"
CHAT_TOP_K = 5
CHAT_MAX_WORDS = 120
NOTHING_RELEVANT = "I could not find anything about that in the NASA documents I have."
# Words too common to show that a passage is about the question.
STOPWORDS = frozenset(
    "a an and are as at be but by can did do does for from had has have how i if in is it its "
    "of on or so than that the their them there these they this to was we were what when where "
    "which who why will with would you your about into over under not no".split()
)


# ---------- shared plumbing ----------


def _load_prompt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        log.exception("rag: cannot read prompt file %s", path)
        raise


def llm_available() -> bool:
    """True when an OpenAI key is set (an empty value counts as missing)."""
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _chat(system: str, user: str) -> str:
    """One OpenAI chat call. Raises on any failure; callers decide how to fall back."""
    from openai import OpenAI  # imported here so the offline path never needs the SDK

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=LLM_TIMEOUT_S)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return (response.choices[0].message.content or "").strip()


def _ask_llm(system: str, user: str, context: str) -> str | None:
    """LLM text, or None when there is no key or the call failed (the failure is logged)."""
    if not llm_available():
        return None
    try:
        return _chat(system, user) or None
    except Exception:
        log.exception("rag: LLM call failed for %s; using the offline template instead", context)
        return None


def retrieve(query: str, k: int) -> list[dict]:
    """Top-k report chunks as {title, investigation, source_url, snippet}.

    Keyword search over data/docs for now; swap in the Chroma store here once ML-08 lands.
    """
    try:
        return [
            {
                "title": p.title,
                "investigation": p.investigation,
                "source_url": p.source_url,
                "snippet": p.snippet,
            }
            for p in stages.retrieve(query, k=k, docs_dir=DOCS_DIR)
        ]
    except Exception:
        log.exception("rag.retrieve failed for query=%r k=%d", query, k)
        raise


def _plain(obj: Any) -> Any:
    """Pydantic models (and lists/dicts of them) -> plain JSON-ready data."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


# ---------- ML-06: explain ----------


def _template_explanation(result: dict) -> str:
    """One sentence built only from the prediction and its nearest tests (offline fallback)."""
    verdict = "keeps burning" if result["state"] == "burning" else "goes out"
    text = (
        f"The model predicts the fire {verdict} (burn probability "
        f"{result['burn_probability']:.2f}, trust {result['trust']})"
    )
    tests = result.get("nearest_tests") or []
    if tests:
        t = tests[0]
        kind = "synthetic placeholder test" if t.get("is_synthetic") else "NASA test"
        text += (
            f"; the nearest {kind} {t['test_id']} ({t['investigation']}, {t['o2_pct']:g} % O2, "
            f"{t['flow_cm_s']:g} cm/s flow) {t['outcome']}"
        )
    else:
        text += "; no nearby NASA test was found"
    if result.get("extrapolated"):
        text += ", and these conditions are outside the tested range: no direct NASA data"
    return text + "."


def _cites_a_given_test(text: str, tests: list[dict]) -> bool:
    return any(str(t["test_id"]) in text for t in tests)


def explain(result: Any) -> str:
    """One grounded sentence for a prediction.

    `result` is a SimulateOut or a dict with: inputs, state, burn_probability, trust,
    extrapolated, nearest_tests. The LLM gets only those tests and the top retrieved chunks;
    an answer that cites none of the given tests is discarded for the template.
    """
    try:
        data = _plain(result)
        tests = data.get("nearest_tests") or []
        template = _template_explanation(data)
    except Exception:
        log.exception("rag.explain: bad result payload %r", result)
        raise
    if not llm_available():
        return template
    try:
        material = data["inputs"]["material"]
        chunks = retrieve(f"{material} flammability oxygen flow extinction", EXPLAIN_TOP_K)
        payload = {
            "prediction": {k: data[k] for k in data if k not in ("nearest_tests", "explanation")},
            "nearest_tests": tests,
            "passages": chunks,
        }
        answer = _ask_llm(_load_prompt(EXPLAIN_PROMPT), json.dumps(payload, default=str), "explain")
    except Exception:
        log.exception("rag.explain: could not build the LLM request; using the template")
        return template
    if not answer:
        return template
    if tests and not _cites_a_given_test(answer, tests):
        log.warning("rag.explain: LLM answer cited none of the given tests; using the template")
        return template
    return " ".join(answer.split())


# ---------- ML-07: answer ----------


def _keywords(message: str) -> str:
    """The question without filler words, so "the" alone never makes a passage relevant."""
    words = "".join(c.lower() if c.isalnum() else " " for c in message).split()
    return " ".join(w for w in words if len(w) > 2 and w not in STOPWORDS)


def _limit_words(text: str, max_words: int = CHAT_MAX_WORDS) -> str:
    words = text.split()
    return text.strip() if len(words) <= max_words else " ".join(words[:max_words]) + " ..."


def answer(message: str, scenario: Any = None) -> ChatOut:
    """Answer a chat question from the top 5 retrieved chunks, in at most 120 words.

    `scenario` is an optional summary of the running simulation (dict or model). Citations are
    the chunks the answer was built from. If nothing relevant is retrieved, it says so.
    Without a key (or if the LLM call fails) the answer is the text of the top chunk.
    """
    try:
        keywords = _keywords(message)
        chunks = retrieve(keywords, CHAT_TOP_K) if keywords else []
    except Exception:
        log.exception("rag.answer: retrieval failed for message=%r", message)
        raise
    if not chunks:
        return ChatOut(answer=NOTHING_RELEVANT, citations=[])

    top = chunks[0]
    fallback = _limit_words(f"{top['snippet']} (source: {top['investigation']})")
    try:
        payload = {
            "question": message,
            "scenario": _plain(scenario),
            "passages": [{"number": i + 1, **c} for i, c in enumerate(chunks)],
        }
        text = _ask_llm(_load_prompt(CHAT_PROMPT), json.dumps(payload, default=str), "answer")
    except Exception:
        log.exception("rag.answer: could not build the LLM request for message=%r", message)
        text = None
    if not text:
        return ChatOut(answer=fallback, citations=[top])
    return ChatOut(answer=_limit_words(" ".join(text.split())), citations=chunks)
