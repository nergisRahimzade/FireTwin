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

    def embedding(kind, *, allow_download=True, cache_dir=None):
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
    assert ingest_rag.search("smoke", 1, db) is None
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
    collection = chromadb.PersistentClient(
        path=str(ingest_rag._active_directory(db))
    ).get_collection(ingest_rag.config.RAG_COLLECTION)
    collection.modify(metadata=metadata)
    assert ingest_rag.search("smoke", 1, db) is None
    assert calls == [("minilm", True)]


def test_missing_model_cache_never_invokes_a_download(monkeypatch, tmp_path: Path):
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    monkeypatch.setattr(ONNXMiniLM_L6_V2, "DOWNLOAD_PATH", tmp_path / "missing-model")

    def forbid_download(*args, **kwargs):
        pytest.fail("query attempted a model download")

    monkeypatch.setattr(ONNXMiniLM_L6_V2, "_download", forbid_download)
    with pytest.raises(ingest_rag.StoreUnavailable, match="cache is incomplete"):
        ingest_rag._embedding("minilm", allow_download=False)
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


@pytest.mark.parametrize("failure", ["embedding", "add", "publication"])
def test_failed_rebuild_preserves_previous_complete_snapshot(synthetic_store, monkeypatch, failure):
    db, chunks, _ = synthetic_store
    before = (db / "CURRENT.json").read_bytes()
    original_embedding = ingest_rag._embedding
    if failure == "embedding":

        def fail(*args, **kwargs):
            raise RuntimeError("synthetic embedding setup failure")

        monkeypatch.setattr(ingest_rag, "_embedding", fail)
    elif failure == "add":
        from chromadb.api.models.Collection import Collection

        def fail_add(*args, **kwargs):
            raise RuntimeError("synthetic add failure")

        monkeypatch.setattr(Collection, "add", fail_add)
    else:
        monkeypatch.setattr(
            ingest_rag,
            "_publish",
            lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic publication failure")),
        )
    with pytest.raises(RuntimeError, match="synthetic"):
        ingest_rag.ingest(db)
    assert (db / "CURRENT.json").read_bytes() == before
    monkeypatch.setattr(ingest_rag, "_embedding", original_embedding)
    assert ingest_rag.search("smoke", 1, db)[0]["id"] == chunks[0]["id"]


def test_partial_active_collection_falls_back_instead_of_returning_no_evidence(synthetic_store):
    import chromadb

    db, chunks, _ = synthetic_store
    client = chromadb.PersistentClient(path=str(ingest_rag._active_directory(db)))
    client.get_collection(ingest_rag.config.RAG_COLLECTION).delete(ids=[chunks[0]["id"]])
    assert ingest_rag.search("smoke", 1, db) is None


def test_custom_corpus_queries_without_default_loader_override(synthetic_store, monkeypatch):
    db, chunks, _ = synthetic_store
    ingest_rag.ingest(db, chunks=chunks)
    monkeypatch.setattr(
        ingest_rag,
        "load_chunks",
        lambda: (_ for _ in ()).throw(AssertionError("default corpus loader was used")),
    )
    assert ingest_rag.search("smoke", 1, db)[0]["id"] == chunks[0]["id"]
    assert ingest_rag.search("smoke", 1, db, chunks=[{**chunks[0], "text": "changed"}]) is None


def test_successful_rebuild_retains_generation_for_existing_readers(synthetic_store):
    db, chunks, _ = synthetic_store
    old = ingest_rag._active_directory(db)
    ingest_rag.ingest(db)
    assert old.is_dir()
    assert ingest_rag._active_directory(db) != old
    assert ingest_rag.search("smoke", 1, db)[0]["id"] == chunks[0]["id"]


def test_expected_index_failure_logs_once_without_traceback(synthetic_store, caplog):
    db, chunks, _ = synthetic_store
    chunks[0]["text"] = "Changed synthetic corpus"
    ingest_rag._warn_unavailable.cache_clear()
    for _ in range(2):
        assert ingest_rag.search("smoke", 1, db) is None
    records = [r for r in caplog.records if "using keyword fallback" in r.message]
    assert len(records) == 1
    assert records[0].exc_info is None


def test_openai_build_requires_explicit_provider_despite_ambient_key(synthetic_store, monkeypatch):
    db, _, calls = synthetic_store
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-must-not-select-provider")
    ingest_rag.ingest(db)
    assert calls[-1][0] == "minilm"
    ingest_rag.ingest(db, embedding_kind="openai")
    assert calls[-1][0] == "openai"


def test_production_local_embedding_identity_survives_reopening(monkeypatch, tmp_path, caplog):
    """Real EF configuration, precomputed build vectors; no fake EF name can mask a conflict."""
    from chromadb.api.models.Collection import Collection
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    cache = tmp_path / "model"
    monkeypatch.setattr(ONNXMiniLM_L6_V2, "DOWNLOAD_PATH", cache)
    original_add = Collection.add

    def add_precomputed(self, **kwargs):
        vectors = [[1.0] + [0.0] * 383 for _ in kwargs["ids"]]
        return original_add(self, embeddings=vectors, **kwargs)

    monkeypatch.setattr(Collection, "add", add_precomputed)
    chunks = [
        {
            "id": "synthetic-real-ef/0",
            "text": "synthetic smoke",
            "title": "fixture",
            "investigation": "SYNTHETIC",
            "source_url": "https://example.test/ef",
        }
    ]
    db = tmp_path / "db"
    ingest_rag.ingest(db, chunks=chunks)
    assert ingest_rag.search("smoke", 1, db) is None
    assert "cache is incomplete" in caplog.text
    assert "Embedding function conflict" not in caplog.text
    for name in ingest_rag.CACHE_FILES:
        p = cache / "onnx" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("synthetic cache; inference is stubbed")
    monkeypatch.setattr(
        ONNXMiniLM_L6_V2, "__call__", lambda self, input: [[1.0] + [0.0] * 383 for _ in input]
    )
    hits = ingest_rag.search("smoke", 1, db)
    assert hits is not None and hits[0]["id"] == chunks[0]["id"]


def test_custom_extra_scalar_metadata_is_preserved_for_fingerprint_validation(synthetic_store):
    db, chunks, _ = synthetic_store
    custom = [{**chunks[0], "is_synthetic": True}]
    ingest_rag.ingest(db, chunks=custom)
    hits = ingest_rag.search("smoke", 1, db)
    assert hits is not None and hits[0]["is_synthetic"] is True
