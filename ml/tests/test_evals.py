"""ML-09: retrieval evals. Ten questions, each with the investigation(s) that must be cited.

A question passes when one of its expected investigations is among the top 5 retrieved chunks.
Target: at least 8 of 10. Run on the committed documents (data/docs + investigations.json), with
keyword search always and with the Chroma vector store when it has been built locally.
"""

from pathlib import Path

import pytest

from app.services import rag
from ml.pipeline import config

QUESTIONS = [
    ("Which experiment studied extinguishing burning fuel droplets with carbon dioxide?",
     {"FLEX", "FLEX-2"}),
    ("What did the Flame Extinguishment Experiment aim to map?", {"FLEX"}),
    ("Which investigation burned large samples inside the Cygnus vehicle?",
     {"Saffire-I", "Saffire-II", "Saffire-III"}),
    ("Which experiment studied burning and suppression of solids?", {"BASS", "BASS-II"}),
    ("Which experiment measured smoke from Teflon and Kapton?", {"SAME", "SAME-R"}),
    ("What is the primary goal of the FLEX-2 flight experiments?", {"FLEX-2"}),
    ("Which tests burned PMMA rods and Nomex?", {"BASS-II"}),
    ("Which investigation used heptane and methanol droplets?", {"FLEX", "FLEX-2"}),
    ("Which investigation tested silicone samples at 20 cm/s air flow?", {"Saffire-II"}),
    ("Which experiment recorded inlet velocity and aging time for Pyrell smoke?", {"SAME-R"}),
]  # fmt: skip
OFF_TOPIC = ["What is the best pizza topping?", "Who won the football world cup?"]
TARGET = 8


def _pass_rate(label: str) -> int:
    passed = 0
    for question, expected in QUESTIONS:
        cited = {c["investigation"] for c in rag.retrieve(question, rag.CHAT_TOP_K)}
        ok = bool(expected & cited)
        passed += ok
        print(f"[{label}] {'PASS' if ok else 'FAIL'}: {question} -> {sorted(cited)}")
    print(f"[{label}] pass rate: {passed}/{len(QUESTIONS)}")
    return passed


@pytest.fixture
def keyword_only(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(rag, "CHROMA_DIR", tmp_path / "no_chroma_db")


@pytest.fixture
def vector_store(monkeypatch):
    if not config.CHROMA_DIR.is_dir():
        pytest.skip("no chroma_db/ here: build it with `python ml/ingest_rag.py`")
    monkeypatch.setattr(rag, "CHROMA_DIR", config.CHROMA_DIR)


def test_keyword_retrieval_meets_the_target(keyword_only) -> None:
    assert _pass_rate("keyword") >= TARGET


def test_vector_retrieval_meets_the_target(vector_store) -> None:
    assert _pass_rate("vector") >= TARGET


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_keyword_retrieval_returns_nothing_for_off_topic_questions(keyword_only, question) -> None:
    assert rag.retrieve(question, rag.CHAT_TOP_K) == []


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_vector_retrieval_returns_nothing_for_off_topic_questions(vector_store, question) -> None:
    assert rag.retrieve(question, rag.CHAT_TOP_K) == []
