"""ML-08: chunking and corpus loading for the RAG store (no embedding model needed)."""

import json
from pathlib import Path

import pytest

from ml import ingest_rag


def test_chunks_have_the_requested_size_and_overlap() -> None:
    words = [f"w{i}" for i in range(1200)]
    chunks = ingest_rag.chunk_text(" ".join(words), size=500, overlap=50)
    assert [len(c.split()) for c in chunks] == [500, 500, 300]
    assert chunks[1].split()[:50] == chunks[0].split()[-50:]
    assert chunks[-1].split()[-1] == "w1199"


def test_short_text_is_one_chunk_and_empty_text_is_none() -> None:
    assert ingest_rag.chunk_text("only a few words") == ["only a few words"]
    assert ingest_rag.chunk_text("   ") == []


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        ingest_rag.chunk_text("a b c", size=10, overlap=10)


def test_load_chunks_reads_the_source_url_header_and_investigation(tmp_path: Path) -> None:
    folder = tmp_path / "docs" / "FLEX"
    folder.mkdir(parents=True)
    (folder / "abstract.txt").write_text("source_url: https://example.test/flex\n\nDroplets burn.")
    chunks = ingest_rag.load_chunks(tmp_path / "docs", tmp_path / "missing.json")
    assert chunks == [
        {
            "id": "FLEX/abstract#0",
            "text": "Droplets burn.",
            "title": "abstract",
            "investigation": "FLEX",
            "source_url": "https://example.test/flex",
        }
    ]


def test_each_investigation_summary_becomes_one_chunk(tmp_path: Path) -> None:
    summary = {
        "name": "SAME",
        "pillar": "detection",
        "objective": None,
        "materials": ["Teflon"],
        "conditions": {"flow_cm_s": {"min": 5.0, "max": 10.0}, "o2_pct": None},
        "source_url": "https://example.test/same",
    }
    path = tmp_path / "investigations.json"
    path.write_text(json.dumps([summary]))
    (tmp_path / "docs").mkdir()
    chunks = ingest_rag.load_chunks(tmp_path / "docs", path)
    assert len(chunks) == 1
    assert chunks[0]["investigation"] == "SAME"
    assert chunks[0]["source_url"] == "https://example.test/same"
    assert "Teflon" in chunks[0]["text"] and "from 5 to 10" in chunks[0]["text"]
    assert "None" not in chunks[0]["text"]


def test_search_returns_none_when_no_store_exists(tmp_path: Path) -> None:
    assert ingest_rag.search("smoke", 3, tmp_path / "no_chroma_db") is None


def test_ingest_refuses_an_empty_corpus(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no documents"):
        ingest_rag.ingest(tmp_path / "db", chunks=[])
