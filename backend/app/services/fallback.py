"""Offline fallback (ML-10): what the explainer and the chat return when no LLM can be used.

Used by rag.py when no API key is set or an LLM call fails, so the demo never crashes. Both
answers are built only from data already in hand (nearest tests, retrieved chunks): nothing is
invented. No FastAPI imports, no network.
"""

from __future__ import annotations

NOTHING_RELEVANT = "I could not find anything about that in the NASA documents I have."


def explanation(result: dict) -> str:
    """One sentence from the prediction and its nearest test.

    `result` has: state, burn_probability, trust, extrapolated, nearest_tests (list of dicts).
    """
    verdict = "keeps burning" if result["state"] == "burning" else "goes out"
    text = (
        f"The model predicts the fire {verdict} (burn probability "
        f"{result['burn_probability']:.2f}, trust {result['trust']})"
    )
    tests = result.get("nearest_tests") or []
    if tests:
        t = tests[0]
        kind = "synthetic placeholder test" if t.get("is_synthetic") else "NASA test"
        conditions = [f"{t['o2_pct']:g} % O2" if t.get("o2_pct") is not None else None]
        conditions.append(
            f"{t['flow_cm_s']:g} cm/s flow" if t.get("flow_cm_s") is not None else None
        )
        where = ", ".join([t["investigation"], *[c for c in conditions if c]])
        outcome = "has no recorded outcome" if t["outcome"] == "unknown" else t["outcome"]
        text += f"; the nearest {kind} {t['test_id']} ({where}) {outcome}"
    else:
        text += "; no nearby NASA test was found"
    if result.get("extrapolated"):
        text += ", and these conditions are outside the tested range: no direct NASA data"
    return text + "."


def chat_answer(chunks: list[dict], max_words: int) -> tuple[str, list[dict]]:
    """(answer, citations): the top chunk's text, cut to max_words, cited to its source."""
    if not chunks:
        return NOTHING_RELEVANT, []
    top = chunks[0]
    words = f"{top['snippet']} (source: {top['investigation']})".split()
    text = " ".join(words) if len(words) <= max_words else " ".join(words[:max_words]) + " ..."
    return text, [top]
