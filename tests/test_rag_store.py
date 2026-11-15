"""ML-08: synthetic local Chroma integration and cache-only query behavior; no model download."""

from pathlib import Path

import pytest

from ml import ingest_rag


@pytest.fixture
def synthetic_store(monkeypatch, tmp_path):
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from chromadb.api.types import EmbeddingFunction

    class SyntheticEmbedding(EmbeddingFunction):
        def __init__(self):
            pass

        def __call__(self, input):
            return [[1.0, 0.0, 0.0] for _ in input]

        @staticmethod
        def name():
            return "synthetic-test-only"

        def get_config(self):
            return {}

        @staticmethod
        def build_from_config(config):
            return SyntheticEmbedding()

    calls = []

    def embedding(kind, *, allow_download=True):
        calls.append((kind, allow_download))
        return SyntheticEmbedding()

    chunks = [
        {
            "id": "synthetic/0",
            "text": "Synthetic smoke evidence.",
            "title": "fixture",
            "investigation": "SYNTHETIC",
            "source_url": "https://example.test/fixture",
        }
    ]
    monkeypatch.setattr(ingest_rag, "_embedding", embedding)
    monkeypatch.setattr(ingest_rag, "load_chunks", lambda *args, **kwargs: chunks)
    db = tmp_path / "db"
    assert ingest_rag.ingest(db) == 1
    return db, chunks, calls


def test_query_uses_recorded_provider_and_disables_local_downloads(synthetic_store, monkeypatch):
    db, chunks, calls = synthetic_store
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-must-not-change-provider")
    hits = ingest_rag.search("smoke", 1, db)
    assert hits[0]["id"] == chunks[0]["id"]
    assert calls == [("minilm", True), ("minilm", False)]


def test_changed_corpus_rejects_stale_vectors(synthetic_store):
    db, chunks, calls = synthetic_store
    chunks[0]["source_url"] = "https://example.test/changed-source"
    with pytest.raises(ValueError, match="metadata/corpus mismatch"):
        ingest_rag.search("smoke", 1, db)
    assert calls == [("minilm", True)]


@pytest.mark.parametrize(
    "metadata",
    [
        {"embedding": "unknown"},
        {"embedding": "minilm"},  # legacy index needs rebuilding with a fingerprint
        {"embedding": "minilm", "embedding_model": "other-model", "store_format": 1},
    ],
)
def test_incompatible_metadata_cannot_select_a_silent_embedding_fallback(synthetic_store, metadata):
    import chromadb

    db, _, calls = synthetic_store
    collection = chromadb.PersistentClient(path=str(db)).get_collection(
        ingest_rag.config.RAG_COLLECTION
    )
    collection.modify(metadata=metadata)
    with pytest.raises(ValueError, match="unsupported embedding|metadata/corpus mismatch"):
        ingest_rag.search("smoke", 1, db)
    assert calls == [("minilm", True)]


def test_missing_model_cache_never_invokes_a_download(monkeypatch, tmp_path: Path):
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    monkeypatch.setattr(ONNXMiniLM_L6_V2, "DOWNLOAD_PATH", tmp_path / "missing-model")

    def forbid_download(*args, **kwargs):
        pytest.fail("query attempted a model download")

    monkeypatch.setattr(ONNXMiniLM_L6_V2, "_download", forbid_download)
    embedding = ingest_rag._embedding("minilm", allow_download=False)
    with pytest.raises(RuntimeError, match="cache is incomplete"):
        embedding(["synthetic smoke question"])
    assert not (tmp_path / "missing-model").exists()


def test_fingerprint_is_order_independent_but_tracks_text_and_sources():
    a = {"id": "a", "text": "one", "source_url": "https://example.test/a"}
    b = {"id": "b", "text": "two", "source_url": "https://example.test/b"}
    fingerprint = ingest_rag.corpus_fingerprint([a, b])
    assert fingerprint == ingest_rag.corpus_fingerprint([b, a])
    assert fingerprint != ingest_rag.corpus_fingerprint([a, {**b, "text": "changed"}])


def test_rag_falls_back_to_cited_keywords_when_index_metadata_is_stale(
    synthetic_store, monkeypatch
):
    from app.services import rag

    db, chunks, _ = synthetic_store
    chunks[0]["text"] = "Synthetic smoke evidence changed after ingest."
    monkeypatch.setattr(rag, "CHROMA_DIR", db)
    hits = rag.retrieve("smoke", 1)
    assert len(hits) == 1
    assert hits[0]["source_url"] == "https://example.test/fixture"
    assert "changed after ingest" in hits[0]["snippet"]
