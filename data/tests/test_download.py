"""DAT-04: download.py logs every table and never crashes. No network: the fetcher is faked."""

import csv
import urllib.error

import download
from psi_sources import Source

TABLE = b"Test #,O2\nB1,21\n"
A = Source("BASS-II", "PSI-25", "a.csv")
B = Source("FLEX", "PSI-69", "b.csv")
NO_ID = Source("Saffire-III", None, "c.csv", note="no PSI study id found for Saffire-III yet")


def refused(url: str) -> bytes:
    raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)


def read_log(raw):
    with (raw / "downloads.csv").open() as f:
        return list(csv.DictReader(f))


def test_every_table_is_logged_and_failures_are_not_fatal(tmp_path):
    rows = download.run(raw_dir=tmp_path, sources=[A, B, NO_ID], fetcher=refused)
    assert [r["name"] for r in rows] == ["BASS-II", "FLEX", "Saffire-III"]
    assert rows[0]["status"].startswith("failed: HTTP 403")
    assert "signed-in" in rows[0]["status"]
    assert rows[2]["status"] == "failed: no PSI study id found for Saffire-III yet"
    logged = read_log(tmp_path)
    assert [r["status"] for r in logged] == [r["status"] for r in rows]
    assert set(logged[0]) == {"name", "url", "status", "file", "checked_at"}
    assert logged[0]["url"] == "https://psi.nasa.gov/geode-py/ws/studies/PSI-25"


def test_downloads_when_psi_answers(tmp_path):
    rows = download.run(raw_dir=tmp_path, sources=[A], fetcher=lambda url: TABLE)
    assert rows[0]["status"] == "downloaded"
    assert (tmp_path / "a.csv").read_bytes() == TABLE


def test_copies_tables_downloaded_by_hand(tmp_path):
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "a.csv").write_bytes(TABLE)
    raw = tmp_path / "raw"
    rows = download.run(raw_dir=raw, manual_dir=manual, sources=[A], fetcher=refused)
    assert rows[0]["status"] == "copied"
    assert rows[0]["url"] == "https://psi.nasa.gov/physci/repo/data/investigations/PSI-25"
    assert (raw / "a.csv").read_bytes() == TABLE


def test_keeps_a_table_already_in_raw(tmp_path):
    (tmp_path / "a.csv").write_bytes(TABLE)
    rows = download.run(raw_dir=tmp_path, sources=[A], fetcher=refused)
    assert rows[0]["status"] == "present"


def test_a_web_page_instead_of_a_table_is_a_failure(tmp_path, monkeypatch):
    def page(url):
        raise ValueError("got text/html, not a CSV table")

    rows = download.run(raw_dir=tmp_path, sources=[A], fetcher=page)
    assert rows[0]["status"] == "failed: got text/html, not a CSV table"
    assert not (tmp_path / "a.csv").exists()
