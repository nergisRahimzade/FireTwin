"""Grounded LLM service (ML-06 explain, ML-07 answer).

The LLM only ever sees the nearest NASA tests and retrieved report passages, and its output is
checked against them. With no GEMINI_API_KEY or OPENAI_API_KEY, or when a call fails, a template
built from the same data is returned instead, so the demo never crashes. No FastAPI imports.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.schemas import ChatOut
from app.services import fallback
from ml import ingest_rag
from ml.agents import llm
from ml.pipeline import config, grounding, model

log = logging.getLogger(__name__)

PROMPTS_DIR = config.ROOT / "ml" / "prompts"
EXPLAIN_PROMPT = PROMPTS_DIR / "explain_v1.txt"
# LLM providers, in order of preference: the first one whose key is set is used.
# Gemini is reached through its OpenAI-compatible endpoint, so the same SDK and (in Phase B)
# the same tool-calling format work for both.
PROVIDERS = llm.PROVIDERS  # Gemini first, then OpenAI: see ml/agents/llm.py
EXPLAIN_TOP_K = 3
DOCS_DIR = config.DOCS_DIR  # data/docs/<investigation>/*.txt (DAT-07)
CHAT_PROMPT = PROMPTS_DIR / "chat_v1.txt"
CHAT_TOP_K = 5
CHAT_MAX_WORDS = 120
NOTHING_RELEVANT = fallback.NOTHING_RELEVANT
INVESTIGATIONS_PATH = config.INVESTIGATIONS_PATH  # one extra chunk per investigation
CHROMA_DIR = config.CHROMA_DIR  # vector store built by ml/ingest_rag.py (ML-08)
SNIPPET_CHARS = 400
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


def llm_provider() -> dict | None:
    """The provider to call: {name, api_key, model, base_url}; None when no key is set."""
    return llm.provider()


def llm_available() -> bool:
    """True when a Gemini or OpenAI key is set."""
    return llm.available()


def _chat(system: str, user: str) -> str:
    """One chat call to the configured provider. Raises on any failure; callers fall back."""
    return llm.chat(system, user)


def _ask_llm(system: str, user: str, context: str) -> str | None:
    """LLM text, or None when there is no key or the call failed (the failure is logged)."""
    if not llm_available():
        return None
    try:
        return _chat(system, user) or None
    except Exception:
        log.exception("rag: LLM call failed for %s; using the offline template instead", context)
        return None


def _keywords(message: str) -> str:
    """The question without filler words, so "the" alone never makes a passage relevant."""
    words = "".join(c.lower() if c.isalnum() else " " for c in message).split()
    return " ".join(w for w in words if len(w) > 2 and w not in STOPWORDS)


def _words(text: str) -> set[str]:
    return set("".join(c.lower() if c.isalnum() else " " for c in text).split())


def _snippet(text: str, query_words: set[str]) -> str:
    """Up to SNIPPET_CHARS of the chunk, starting at the sentence that best matches the query."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    best = max(range(len(sentences)), key=lambda i: len(query_words & _words(sentences[i])))
    return " ".join(sentences[best:])[:SNIPPET_CHARS]


def _citation(chunk: dict, query_words: set[str]) -> dict:
    return {
        "title": chunk["title"],
        "investigation": chunk["investigation"],
        "source_url": chunk["source_url"],
        "snippet": _snippet(chunk["text"], query_words),
    }


def _keyword_search(query: str, k: int) -> list[dict]:
    """Chunks sharing the most keywords with the query; none shared = not relevant."""
    query_words = set(_keywords(query).split())
    if not query_words:
        return []
    scored = []
    for chunk in ingest_rag.load_chunks(DOCS_DIR, INVESTIGATIONS_PATH):
        overlap = len(query_words & _words(chunk["text"]))
        if overlap:
            scored.append((overlap, chunk))
    scored.sort(key=lambda pair: -pair[0])
    return [_citation(chunk, query_words) for _, chunk in scored[:k]]


def retrieve(query: str, k: int) -> list[dict]:
    """Top-k report chunks as {title, investigation, source_url, snippet}; [] if none relevant.

    Uses the Chroma vector store when it has been built (ML-08). Without a store, or if the
    store cannot be searched, it falls back to keyword search over the same documents.
    """
    hits = None
    try:
        hits = ingest_rag.search(query, k, CHROMA_DIR)
    except Exception:
        log.exception(
            "rag.retrieve: vector search failed for query=%r; using keyword search", query
        )
    try:
        if hits is None:
            return _keyword_search(query, k)
        query_words = set(_keywords(query).split())
        return [_citation(h, query_words) for h in hits if h["distance"] <= config.RAG_MAX_DISTANCE]
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


def _explain_sentence(result: Any) -> str:
    """One grounded sentence for a prediction.

    `result` is a SimulateOut or a dict with: inputs, state, burn_probability, trust,
    extrapolated, nearest_tests. The LLM gets only those tests and the top retrieved chunks;
    an answer with any number, test or investigation not in that input, or that names none
    of the given tests, is discarded for the template (see ml/pipeline/grounding.py).
    """
    try:
        data = _plain(result)
        tests = data.get("nearest_tests") or []
        template = fallback.explanation(data)
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
    ids = [str(t["test_id"]) for t in tests]
    problems = grounding.check_explanation(answer, payload, ids)
    if problems:
        log.warning("rag.explain: LLM answer not grounded (%s); using the template", problems)
        return template
    return " ".join(answer.split())


def _material_note(result: Any) -> str:
    """Says so when the chosen material has too few tests for its own term in the model."""
    try:
        material = _plain(result)["inputs"]["material"]
        own = model.material_has_own_term(material)
        fuel = model.fuel_type_of(material)
    except Exception:
        log.exception("rag._material_note failed; leaving the explanation without it")
        return ""
    if own is False:
        return f" Too few NASA tests of {material} for its own term: the {fuel} average is used."
    return ""


def explain(result: Any) -> str:
    """One grounded sentence for a prediction, plus a note when the material uses its fuel average.

    `result` is a SimulateOut or a dict with: inputs, state, burn_probability, trust,
    extrapolated, nearest_tests. See _explain_sentence for how the LLM output is checked.
    """
    return _explain_sentence(result) + _material_note(result)


# ---------- ML-07: answer ----------


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
        chunks = retrieve(message, CHAT_TOP_K)
    except Exception:
        log.exception("rag.answer: retrieval failed for message=%r", message)
        raise
    offline_text, offline_citations = fallback.chat_answer(chunks, CHAT_MAX_WORDS)
    if not chunks:
        return ChatOut(answer=offline_text, citations=offline_citations)
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
        return ChatOut(answer=offline_text, citations=offline_citations)
    problems = grounding.check(text, payload) + grounding.check_citations(text, len(chunks))
    if problems:
        log.warning("rag.answer: LLM answer not grounded (%s); using the top passage", problems)
        return ChatOut(answer=offline_text, citations=offline_citations)
    return ChatOut(answer=_limit_words(" ".join(text.split())), citations=chunks)
