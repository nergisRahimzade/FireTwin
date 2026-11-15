"""RAG ingest and search (ML-08): chunk the NASA documents and store them in Chroma.

Corpus = every data/docs/<investigation>/*.txt (line 1 is "source_url: <url>") cut into chunks of
about 500 words with 50 overlap, plus each entry of data/processed/investigations.json as one
chunk. Embeddings: explicit --embedding minilm|openai, default local all-MiniLM-L6-v2.
Ambient provider keys never change the chosen build provider.
The store lives in chroma_db/ (git-ignored): rebuild it with `python ml/ingest_rag.py`.
Ingest is a provisioning step that may download weights. Local query embeddings are cache-only;
missing/incomplete caches or index metadata/corpus mismatches raise so RAG can use keyword fallback.
OpenAI-backed indexes still require a key and network for query embeddings, separate from the LLM.

`load_chunks()` is also the corpus for the keyword search that backs the app when no store exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.pipeline import config  # noqa: E402

log = logging.getLogger("ingest_rag")

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
STORE_FORMAT = 2
CACHE_FILES = (
    "config.json",
    "model.onnx",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "vocab.txt",
)


def corpus_fingerprint(chunks: list[dict]) -> str:
    """Identify the exact text and source metadata independently of discovery order."""
    canonical = json.dumps(
        sorted(chunks, key=lambda c: c["id"]),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def embedding_model(kind: str) -> str:
    if kind == "openai":
        return OPENAI_EMBEDDING_MODEL
    if kind == "minilm":
        return LOCAL_EMBEDDING_MODEL
    raise ValueError(f"unsupported embedding kind: {kind!r}; rebuild the RAG store")


def chunk_text(
    text: str, size: int = config.RAG_CHUNK_WORDS, overlap: int = config.RAG_CHUNK_OVERLAP
) -> list[str]:
    """Split text into chunks of `size` words; each chunk repeats the last `overlap` words."""
    if size <= overlap:
        raise ValueError(f"chunk_text: size ({size}) must be larger than overlap ({overlap})")
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
        start += size - overlap
    return chunks


def _split_header(text: str) -> tuple[str, str]:
    """('source url', 'body') from a document whose first line is 'source_url: <url>'."""
    header, _, body = text.partition("\n")
    return header.removeprefix("source_url:").strip(), body.strip()


def _investigation_text(entry: dict) -> str:
    """One readable paragraph from an investigations.json entry, skipping empty fields."""
    parts = [f"{entry['name']} is a NASA {entry.get('pillar') or 'fire'} investigation."]
    if entry.get("objective"):
        parts.append(f"Objective: {entry['objective']}")
    for label, key in (
        ("Fuel types", "fuel"),
        ("Materials", "materials"),
        ("Hardware", "hardware"),
    ):
        if entry.get(key):
            parts.append(f"{label}: {', '.join(map(str, entry[key]))}.")
    for feature, span in (entry.get("conditions") or {}).items():
        if span:
            parts.append(f"Tested {feature} from {span['min']:g} to {span['max']:g}.")
    if entry.get("psi_table_columns"):
        parts.append(f"Its PSI table records: {', '.join(entry['psi_table_columns'])}.")
    return " ".join(parts)


def load_chunks(
    docs_dir: Path | None = None, investigations_path: Path | None = None
) -> list[dict]:
    """Every chunk of the corpus as {id, text, title, investigation, source_url}."""
    docs_dir = docs_dir or config.DOCS_DIR
    investigations_path = investigations_path or config.INVESTIGATIONS_PATH
    chunks = []
    for path in sorted(docs_dir.glob("*/*.txt")):
        try:
            source_url, body = _split_header(path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("load_chunks: cannot read %s", path)
            raise
        for i, text in enumerate(chunk_text(body)):
            chunks.append(
                {
                    "id": f"{path.parent.name}/{path.stem}#{i}",
                    "text": text,
                    "title": path.stem,
                    "investigation": path.parent.name,
                    "source_url": source_url,
                }
            )
    if investigations_path.is_file():
        try:
            entries = json.loads(investigations_path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("load_chunks: cannot read %s", investigations_path)
            raise
        for entry in entries:
            chunks.append(
                {
                    "id": f"{entry['name']}/summary",
                    "text": _investigation_text(entry),
                    "title": f"{entry['name']} summary",
                    "investigation": entry["name"],
                    "source_url": entry.get("source_url") or "",
                }
            )
    return chunks


class StoreUnavailable(ValueError):
    """Expected missing/stale/incomplete retrieval resources; use keyword fallback."""


@lru_cache(maxsize=128)
def _warn_unavailable(path: str, reason: str) -> None:
    log.warning("RAG store unavailable at %s: %s; using keyword fallback", path, reason)


def _embedding(kind: str, *, allow_download: bool = True, cache_dir: Path | None = None):
    """The Chroma embedding function for 'openai' or 'minilm'."""
    embedding_model(kind)  # Unknown metadata must not silently select a different model.
    from chromadb.utils import embedding_functions

    if kind == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise StoreUnavailable("OpenAI embedding index requires OPENAI_API_KEY")
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=key, model_name=OPENAI_EMBEDDING_MODEL
        )

    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    class CachedMiniLM(ONNXMiniLM_L6_V2):
        def _download_model_if_not_exists(self) -> None:
            if allow_download:
                return super()._download_model_if_not_exists()
            # Override the library's download hook, not just a one-time existence check:
            # removing a cached file between construction and inference cannot start HTTP.
            folder = Path(self.DOWNLOAD_PATH) / self.EXTRACTED_FOLDER_NAME
            missing = [
                name
                for name in CACHE_FILES
                if not (folder / name).is_file() or (folder / name).stat().st_size == 0
            ]
            if missing:
                raise StoreUnavailable(
                    "local embedding cache is incomplete; prepare the model "
                    "before offline queries (missing: " + ", ".join(missing) + ")"
                )

    embedding = CachedMiniLM()
    selected_cache = cache_dir or os.getenv("FIRETWIN_EMBEDDING_CACHE")
    if selected_cache:
        embedding.DOWNLOAD_PATH = Path(selected_cache)
    if not allow_download:
        embedding._download_model_if_not_exists()
    return embedding


def _active_directory(root: Path) -> Path:
    pointer = root / "CURRENT.json"
    if not pointer.exists():
        return root  # Legacy indexes are rejected by metadata validation, never deleted.
    try:
        generation = json.loads(pointer.read_text())["generation"]
        if (
            not isinstance(generation, str)
            or len(generation) != 32
            or any(c not in "0123456789abcdef" for c in generation)
        ):
            raise ValueError("invalid generation")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise StoreUnavailable("invalid CURRENT.json; rebuild the index") from exc
    selected = root / "generations" / generation
    if not selected.is_dir():
        raise StoreUnavailable("published generation directory is missing")
    return selected


def _publish(root: Path, generation: str) -> None:
    # Only this small pointer is replaced atomically. Existing generation directories are
    # immutable after build and retained so readers already using one remain valid.
    temporary = root / f".CURRENT.{generation}.tmp"
    try:
        with temporary.open("x") as stream:
            json.dump({"generation": generation}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / "CURRENT.json")
    finally:
        temporary.unlink(missing_ok=True)


def ingest(
    persist_dir: Path | None = None,
    chunks: list[dict] | None = None,
    *,
    embedding_kind: str = "minilm",
    cache_dir: Path | None = None,
) -> int:
    """Build an isolated generation, then atomically publish it. Defaults to local embeddings.

    Failed/interrupted candidates and old generations are retained for offline cleanup;
    no writer deletes the active generation. Concurrent successful writers are last-publish-wins.
    """
    root = Path(persist_dir or config.CHROMA_DIR)
    source = "default" if chunks is None else "explicit"
    chunks = load_chunks() if chunks is None else chunks
    if not chunks:
        raise ValueError("ingest: no documents found in data/docs or investigations.json")
    embedding_model(embedding_kind)
    import chromadb

    generation = uuid.uuid4().hex
    candidate = root / "generations" / generation
    candidate.mkdir(parents=True)
    collection = chromadb.PersistentClient(path=str(candidate)).create_collection(
        config.RAG_COLLECTION,
        embedding_function=_embedding(embedding_kind, cache_dir=cache_dir),
        metadata={
            "hnsw:space": "cosine",
            "embedding": embedding_kind,
            "embedding_model": embedding_model(embedding_kind),
            "store_format": STORE_FORMAT,
            "corpus_sha256": corpus_fingerprint(chunks),
            "corpus_source": source,
            "chunk_count": len(chunks),
            "complete": False,
        },
    )
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[{k: c[k] for k in ("title", "investigation", "source_url")} for c in chunks],
    )
    if collection.count() != len(chunks):
        raise StoreUnavailable("candidate chunk count mismatch; previous index remains active")
    collection.modify(
        metadata={
            **{k: v for k, v in collection.metadata.items() if k != "hnsw:space"},
            "complete": True,
        }
    )
    _publish(root, generation)
    return len(chunks)


def _stored_chunks(collection) -> list[dict]:
    rows = collection.get(include=["documents", "metadatas"])
    return [
        {"id": id_, "text": text, **metadata}
        for id_, text, metadata in zip(rows["ids"], rows["documents"], rows["metadatas"])
    ]


def search(
    query: str,
    k: int,
    persist_dir: Path | None = None,
    *,
    chunks: list[dict] | None = None,
    cache_dir: Path | None = None,
) -> list[dict] | None:
    """Query a complete matching snapshot, or None for expected unavailable resources.

    Default-source indexes are checked against current source files. Explicit/custom indexes
    are checked against their saved content, or the caller's expected chunks when supplied.
    Unexpected database/inference errors still raise; the RAG service owns final fallback.
    """
    root = Path(persist_dir or config.CHROMA_DIR)
    if not root.is_dir():
        return None
    import chromadb

    try:
        selected = _active_directory(root)
        client = chromadb.PersistentClient(path=str(selected))
        if config.RAG_COLLECTION not in [c.name for c in client.list_collections()]:
            return None
        snapshot = client.get_collection(config.RAG_COLLECTION)
        metadata = snapshot.metadata or {}
        kind = metadata.get("embedding")
        try:
            expected_model = embedding_model(kind)
        except ValueError as exc:
            raise StoreUnavailable(str(exc)) from exc
        if (
            metadata.get("store_format") != STORE_FORMAT
            or metadata.get("embedding_model") != expected_model
            or metadata.get("complete") is not True
            or metadata.get("chunk_count") != snapshot.count()
        ):
            raise StoreUnavailable("index metadata/count incomplete or incompatible; rebuild")
        if chunks is None:
            source = metadata.get("corpus_source")
            if source == "default":
                chunks = load_chunks()
            elif source == "explicit":
                chunks = _stored_chunks(snapshot)
            else:
                raise StoreUnavailable("unknown corpus source; rebuild")
        if metadata.get("corpus_sha256") != corpus_fingerprint(chunks):
            raise StoreUnavailable("corpus mismatch; rebuild the index")
        collection = client.get_collection(
            config.RAG_COLLECTION,
            embedding_function=_embedding(kind, allow_download=False, cache_dir=cache_dir),
        )
        found = collection.query(query_texts=[query], n_results=k)
    except StoreUnavailable as exc:
        _warn_unavailable(str(root), str(exc))
        return None
    except Exception:
        log.exception("RAG search failed (persist_dir=%s, k=%d)", root, k)
        raise
    return [
        {"id": id_, "text": text, **meta, "distance": float(distance)}
        for id_, text, meta, distance in zip(
            found["ids"][0], found["documents"][0], found["metadatas"][0], found["distances"][0]
        )
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--persist-dir", type=Path, default=config.CHROMA_DIR)
    parser.add_argument("--embedding", choices=("minilm", "openai"), default="minilm")
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args(argv)
    count = ingest(args.persist_dir, embedding_kind=args.embedding, cache_dir=args.cache_dir)
    print(f"RAG ingest: published {count} chunks ({args.embedding}) at {args.persist_dir}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    raise SystemExit(main())
