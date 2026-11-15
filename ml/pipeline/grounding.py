"""Grounding check: is every fact in an LLM's text present in the data it was given?

"Agents think, tools compute": an LLM may phrase and explain, but every number, test id and
investigation it writes must come from its input (the tool results). This module finds the ones
that do not, so callers can reject the text and use their offline template instead. Shared by the
explainer, the chat and (Phase B) the Safety & Evidence Critic.

What counts as grounded:
- a number, if some number in the input equals it after the rounding the text shows, either as
  is or as a percentage of a 0-1 value (0.514 grounds "51 %" and "0.51");
- a test id, if it is one of the given tests;
- an investigation name, if it appears anywhere in the input.
Chemical formulas (O2, CO2, N2) and the digits inside ids are not treated as numbers.
"""

from __future__ import annotations

import json
import re
from typing import Any

INVESTIGATIONS = (
    "BASS-II",
    "BASS",
    "Saffire-III",
    "Saffire-II",
    "Saffire-I",
    "FLEX-2",
    "FLEX",
    "SAME-R",
    "SAME",
)
FORMULAS = re.compile(r"\b(?:CO2|CO|O2|N2|H2O|He)\b")
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
TEST_ID = re.compile(r"(?<![\w-])(?:FLEX|BASS-II|BASS|Saffire-I{1,3})-[A-Za-z0-9]+(?:-\d+)?\b")


def _flatten(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _whole(test_id: str) -> str:
    return rf"(?<![\w-]){re.escape(test_id)}(?![\w-])"


def _without(text: str, ids: list[str]) -> str:
    """The text with the given test ids blanked out (longest first, whole ids only)."""
    for test_id in sorted(set(ids), key=len, reverse=True):
        text = re.sub(_whole(test_id), " ", text)
    return text


def numbers_in(text: str) -> list[str]:
    """Numbers written in the text, as written (so their decimals tell the rounding used)."""
    cleaned = FORMULAS.sub(" ", TEST_ID.sub(" ", text))
    return NUMBER.findall(cleaned)


def _values(payload: Any) -> list[float]:
    return [float(n) for n in numbers_in(_flatten(payload))]


def _grounded(written: str, values: list[float]) -> bool:
    decimals = len(written.split(".")[1]) if "." in written else 0
    tolerance = 0.5 * 10**-decimals + 1e-9
    n = float(written)
    for v in values:
        if abs(n - v) <= tolerance or abs(n - 100 * v) <= tolerance:
            return True
    return False


def check(text: str, payload: Any, given_test_ids: list[str] | None = None) -> list[str]:
    """Problems found in `text` against `payload` (empty list = every fact is grounded)."""
    problems = []
    source = _flatten(payload)
    values = _values(payload)
    allowed_ids = set(given_test_ids or [])
    text = _without(text, list(allowed_ids))  # given ids are fine, and their digits aren't numbers
    for written in numbers_in(text):
        if not _grounded(written, values):
            problems.append(f"number {written} is not in the input")
    for test_id in TEST_ID.findall(text):
        if test_id not in allowed_ids and test_id not in INVESTIGATIONS:
            problems.append(f"test {test_id} was not given")
    remaining = TEST_ID.sub(" ", text)
    for name in INVESTIGATIONS:
        pattern = rf"(?<![\w-]){re.escape(name)}(?![\w-])"
        if re.search(pattern, remaining):
            remaining = re.sub(pattern, " ", remaining)
            if not re.search(pattern, source):
                problems.append(f"investigation {name} is not in the input")
    return problems


def check_explanation(text: str, payload: Any, given_test_ids: list[str]) -> list[str]:
    """The explainer's rule: grounded, and it names at least one of the given tests."""
    problems = check(text, payload, given_test_ids)
    if given_test_ids and not any(re.search(_whole(t), text) for t in given_test_ids):
        problems.append("names none of the given tests")
    return problems


def check_citations(text: str, n_passages: int) -> list[str]:
    """Chat answers cite passages as [1]..[n]; a number outside that range is invented."""
    cited = [int(c) for c in re.findall(r"\[(\d+)\]", text)]
    return [f"citation [{c}] does not exist" for c in cited if not 1 <= c <= n_passages]
