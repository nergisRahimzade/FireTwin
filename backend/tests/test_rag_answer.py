"""ML-07: chat answerer over retrieved NASA passages (the LLM itself is faked)."""

from pathlib import Path

import pytest

from app.schemas import ChatOut
from app.services import rag

DOC = (
    "https://example.test/flex\n"
    "FLEX studied suppression of burning heptane droplets with carbon dioxide diluent.\n\n"
    "Radiative extinction was observed for large droplets.\n"
)


@pytest.fixture
def docs(tmp_path: Path, monkeypatch) -> Path:
    folder = tmp_path / "FLEX"
    folder.mkdir()
    (folder / "abstract.txt").write_text(DOC)
    monkeypatch.setattr(rag, "DOCS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


def test_without_a_key_the_answer_is_the_top_chunk_with_its_citation(docs, no_key) -> None:
    out = rag.answer("Which experiment studied suppression with carbon dioxide?")
    assert isinstance(out, ChatOut)
    assert "FLEX studied suppression" in out.answer
    assert out.citations[0]["investigation"] == "FLEX"
    assert out.citations[0]["source_url"] == "https://example.test/flex"
    assert set(out.citations[0]) == {"title", "investigation", "source_url", "snippet"}


def test_nothing_relevant_says_so(docs, no_key) -> None:
    out = rag.answer("What is the best pizza topping?")
    assert out.answer == rag.NOTHING_RELEVANT
    assert out.citations == []


def test_filler_words_alone_do_not_count_as_relevant(docs, no_key) -> None:
    assert rag.answer("What is the of with?").citations == []


def test_empty_docs_folder_does_not_crash(tmp_path, monkeypatch, no_key) -> None:
    monkeypatch.setattr(rag, "DOCS_DIR", tmp_path)
    assert rag.answer("carbon dioxide suppression").answer == rag.NOTHING_RELEVANT


def test_llm_gets_question_scenario_and_passages(docs, with_key, monkeypatch) -> None:
    seen = {}

    def fake_chat(system: str, user: str) -> str:
        seen["system"], seen["user"] = system, user
        return "FLEX used carbon dioxide as a diluent [1]."

    monkeypatch.setattr(rag, "_chat", fake_chat)
    out = rag.answer("carbon dioxide suppression?", {"state": "burning", "o2_pct": 21.0})
    assert out.answer == "FLEX used carbon dioxide as a diluent [1]."
    assert "120 words" in seen["system"]
    assert '"state": "burning"' in seen["user"]
    assert "FLEX studied suppression" in seen["user"]
    assert out.citations[0]["investigation"] == "FLEX"


def test_long_llm_answers_are_cut_to_120_words(docs, with_key, monkeypatch) -> None:
    monkeypatch.setattr(rag, "_chat", lambda system, user: "word " * 300)
    out = rag.answer("carbon dioxide suppression?")
    assert len(out.answer.split()) <= rag.CHAT_MAX_WORDS + 1


def test_llm_failure_falls_back_to_the_top_chunk(docs, with_key, monkeypatch) -> None:
    def boom(system: str, user: str) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(rag, "_chat", boom)
    assert "FLEX studied suppression" in rag.answer("carbon dioxide suppression?").answer
