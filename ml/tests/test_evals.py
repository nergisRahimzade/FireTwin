"""ML-09: retrieval evals. Ten questions, each with the investigation(s) that must be cited.

A question passes when one of its expected investigations is among the top 5 retrieved chunks.
Target: at least 8 of 10. Run on the committed documents (data/docs + investigations.json):
- keyword search: always (no vector store).
- vector search: with a prepared bundle (`FIRETWIN_RAG_BUNDLE=<dir from docker/rag_bundle.py>`)
  or a local `chroma_db/` built by `python ml/ingest_rag.py`; skipped when neither exists.
  Keyword fallback is switched off for these tests, so a broken or stale vector store fails
  instead of being scored on keyword hits (package 6: test retrieval modes separately).
"""

import os
from pathlib import Path
from runpy import run_path

import pytest

from app.services import rag
from ml.pipeline import config

ROOT = Path(__file__).resolve().parents[2]

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


def _forbid_keyword_fallback(monkeypatch) -> None:
    # rag.retrieve() quietly switches to keyword search when vector search is unavailable.
    # In a vector eval that would score keyword hits as "vector", so make the switch an error.
    def no_fallback(query: str, k: int) -> list[dict]:
        raise AssertionError(
            "vector search was unavailable and rag.retrieve() used the keyword fallback; "
            "rebuild the store (python ml/ingest_rag.py) or re-prepare the bundle"
        )

    monkeypatch.setattr(rag, "_keyword_search", no_fallback)


@pytest.fixture
def vector_store(monkeypatch, tmp_path: Path):
    bundle = os.getenv("FIRETWIN_RAG_BUNDLE", "").strip()
    if bundle:
        # A prepared bundle is verified, then copied to a writable folder, as the container
        # does (queries write Chroma bookkeeping; the bundle itself must stay untouched).
        stage_bundle = run_path(str(ROOT / "docker/rag_bundle.py"))["stage_bundle"]
        store = tmp_path / "chroma_db"
        assert stage_bundle(Path(bundle), store), f"FIRETWIN_RAG_BUNDLE={bundle} has no bundle.json"
        monkeypatch.setenv("FIRETWIN_EMBEDDING_CACHE", str(Path(bundle) / "model"))
    elif (config.CHROMA_DIR / "CURRENT.json").is_file():
        store = config.CHROMA_DIR  # a local index published by ml/ingest_rag.py
    else:
        pytest.skip("no vector store: set FIRETWIN_RAG_BUNDLE or run `python ml/ingest_rag.py`")
    _forbid_keyword_fallback(monkeypatch)
    monkeypatch.setattr(rag, "CHROMA_DIR", store)


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


def test_unusable_vector_store_fails_instead_of_scoring_keywords(monkeypatch, tmp_path) -> None:
    # Runs without any bundle: a store whose published generation is missing makes vector
    # search unavailable, and the guard must turn the keyword fallback into a failure.
    store = tmp_path / "chroma_db"
    store.mkdir()
    (store / "CURRENT.json").write_text('{"generation": "' + "0" * 32 + '"}')
    _forbid_keyword_fallback(monkeypatch)
    monkeypatch.setattr(rag, "CHROMA_DIR", store)
    with pytest.raises(AssertionError, match="keyword fallback"):
        rag.retrieve(QUESTIONS[0][0], rag.CHAT_TOP_K)
