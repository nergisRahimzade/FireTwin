"""Grounded LLM service (ML-06 explain, ML-07 answer).

The LLM only ever sees the nearest NASA tests and retrieved report passages, and its output is
checked against them. With no GEMINI_API_KEY or OPENAI_API_KEY, or when a call fails, a template
built from the same data is returned instead, so the demo never crashes. No FastAPI imports.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.schemas import ChatOut
from app.services import fallback
from ml import ingest_rag
from ml.pipeline import config

log = logging.getLogger(__name__)

PROMPTS_DIR = config.ROOT / "ml" / "prompts"
EXPLAIN_PROMPT = PROMPTS_DIR / "explain_v1.txt"
# LLM providers, in order of preference: the first one whose key is set is used.
# Gemini is reached through its OpenAI-compatible endpoint, so the same SDK and (in Phase B)
# the same tool-calling format work for both.
PROVIDERS = (
    {
        "name": "gemini",
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.8-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    {
        "name": "openai",
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "base_url": None,  # the SDK's default
    },
)
LLM_TIMEOUT_S = 20.0
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
    """The provider to call: {name, api_key, model, base_url}; None when no key is set.

    GEMINI_API_KEY wins over OPENAI_API_KEY. An empty value counts as missing.
    """
    for provider in PROVIDERS:
        key = os.getenv(provider["key_env"], "").strip()
        if key:
            model = os.getenv(provider["model_env"], "").strip() or provider["default_model"]
            return {
                "name": provider["name"],
                "api_key": key,
                "model": model,
                "base_url": provider["base_url"],
            }
    return None


def llm_available() -> bool:
    """True when a Gemini or OpenAI key is set."""
    return llm_provider() is not None


def _chat(system: str, user: str) -> str:
    """One chat call to the configured provider. Raises on any failure; callers fall back."""
    from openai import OpenAI  # imported here so the offline path never needs the SDK

    provider = llm_provider()
    if provider is None:
        raise RuntimeError("rag._chat: no GEMINI_API_KEY or OPENAI_API_KEY is set")
    client = OpenAI(
        api_key=provider["api_key"], base_url=provider["base_url"], timeout=LLM_TIMEOUT_S
    )
    response = client.chat.completions.create(
        model=provider["model"],
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
    if tests and not _cites_a_given_test(answer, tests):
        log.warning("rag.explain: LLM answer cited none of the given tests; using the template")
        return template
    return " ".join(answer.split())


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
    return ChatOut(answer=_limit_words(" ".join(text.split())), citations=chunks)
