"""Optional vector-bundle startup, then the unchanged Linux API entrypoint."""

import os
import sys
from pathlib import Path

from backend_entrypoint import main as start_api
from rag_bundle import stage_bundle


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    bundle = Path(os.environ.get("FIRETWIN_RAG_BUNDLE", "/app/rag_bundle"))
    try:
        ready = stage_bundle(bundle, root / "chroma_db")
    except (OSError, ValueError) as error:
        raise SystemExit(f"RAG bundle startup failed: {error}") from None
    if ready:
        os.environ["FIRETWIN_EMBEDDING_CACHE"] = str(bundle / "model")
        print("RAG: verified local vector bundle; writable index copy ready", flush=True)
    else:
        print("RAG: no bundle manifest; using keyword fallback", flush=True)
    start_api(sys.argv[1:])


if __name__ == "__main__":
    main()
