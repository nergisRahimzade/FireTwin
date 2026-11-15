"""DAT-07: every RAG document starts with a source_url header line, for ML-08's ingest."""

from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
FILES = sorted(DOCS.glob("*/*.txt"))


def test_there_are_documents_for_each_cleaned_investigation():
    folders = {f.parent.name for f in FILES}
    assert {"FLEX", "Saffire-II", "BASS-II"} <= folders


def test_each_document_has_a_source_url_header_and_text():
    for path in FILES:
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("source_url: https://"), f"{path}: first line must be source_url"
        assert lines[1] == "", f"{path}: a blank line must follow the header"
        assert len(" ".join(lines[2:]).split()) >= 100, f"{path}: the text looks too short"
