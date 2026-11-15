"""RAG ingest and search (ML-08): chunk the NASA documents and store them in Chroma.

Corpus = every data/docs/<investigation>/*.txt (line 1 is "source_url: <url>") cut into chunks of
about 500 words with 50 overlap, plus each entry of data/processed/investigations.json as one
chunk. Embeddings: OpenAI text-embedding-3-small when OPENAI_API_KEY is set, otherwise the local
all-MiniLM-L6-v2 model that ships with Chroma (no key, no network after its first download).
The store lives in chroma_db/ (git-ignored): rebuild it with `python ml/ingest_rag.py`.

`load_chunks()` is also the corpus for the keyword search that backs the app when no store exists.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.pipeline import config  # noqa: E402

log = logging.getLogger("ingest_rag")

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


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


def _embedding(kind: str):
    """The Chroma embedding function for 'openai' or 'minilm'."""
    from chromadb.utils import embedding_functions

    if kind == "openai":
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=os.environ["OPENAI_API_KEY"], model_name=OPENAI_EMBEDDING_MODEL
        )
    return embedding_functions.DefaultEmbeddingFunction()  # all-MiniLM-L6-v2, runs locally


def ingest(persist_dir: Path | None = None, chunks: list[dict] | None = None) -> int:
    """(Re)build the Chroma collection from the corpus. Returns the number of chunks stored."""
    import chromadb

    persist_dir = persist_dir or config.CHROMA_DIR
    chunks = load_chunks() if chunks is None else chunks
    if not chunks:
        raise ValueError("ingest: no documents found in data/docs or investigations.json")
    kind = "openai" if os.getenv("OPENAI_API_KEY", "").strip() else "minilm"
    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
        if config.RAG_COLLECTION in [c.name for c in client.list_collections()]:
            client.delete_collection(config.RAG_COLLECTION)
        collection = client.create_collection(
            config.RAG_COLLECTION,
            embedding_function=_embedding(kind),
            metadata={"hnsw:space": "cosine", "embedding": kind},
        )
        collection.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[{k: c[k] for k in ("title", "investigation", "source_url")} for c in chunks],
        )
    except Exception:
        log.exception(
            "ingest failed (persist_dir=%s, %d chunks, %s)", persist_dir, len(chunks), kind
        )
        raise
    return len(chunks)


def search(query: str, k: int, persist_dir: Path | None = None) -> list[dict] | None:
    """Top-k chunks by embedding distance, each with a `distance` (cosine, lower = closer).

    Returns None when there is no store to search (not built yet), so callers can fall back.
    """
    persist_dir = persist_dir or config.CHROMA_DIR
    if not Path(persist_dir).is_dir():
        return None
    import chromadb

    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
        if config.RAG_COLLECTION not in [c.name for c in client.list_collections()]:
            return None
        kind = (client.get_collection(config.RAG_COLLECTION).metadata or {}).get("embedding")
        collection = client.get_collection(
            config.RAG_COLLECTION, embedding_function=_embedding(kind)
        )
        found = collection.query(query_texts=[query], n_results=k)
    except Exception:
        log.exception("search failed (query=%r, k=%d, persist_dir=%s)", query, k, persist_dir)
        raise
    return [
        {"id": id_, "text": text, **meta, "distance": float(distance)}
        for id_, text, meta, distance in zip(
            found["ids"][0], found["documents"][0], found["metadatas"][0], found["distances"][0]
        )
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    log.info("stored %d chunks in %s", ingest(), config.CHROMA_DIR)
