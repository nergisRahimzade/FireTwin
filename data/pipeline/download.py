"""DAT-04: put the PSI experiment tables in data/raw/ and log each one in data/raw/downloads.csv.

PSI's file API only answers a signed-in session, so a plain download is refused (HTTP 403).
For each table in psi_sources.SOURCES, in this order:
  1. already in data/raw/                     -> status "present"
  2. found in the --from folder (tables you    -> status "copied"
     downloaded from PSI while signed in)
  3. fetched from the PSI API                  -> status "downloaded", or "failed: <why>"
Failures are logged, never fatal: the script always finishes and writes the log.

    uv run python data/pipeline/download.py --from ~/Downloads
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from psi_sources import RAW_DIR, SOURCES, Source

log = logging.getLogger("download")
LOG_COLUMNS = ["name", "url", "status", "file", "checked_at"]
TIMEOUT_S = 30


def fetch(url: str) -> bytes:
    """GET a URL. Raises on HTTP errors and when PSI sends a web page instead of a table."""
    req = urllib.request.Request(url, headers={"User-Agent": "FireTwin-data-pipeline"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
        kind = res.headers.get("Content-Type", "")
        body = res.read()
    if "html" in kind or "json" in kind:
        raise ValueError(f"got {kind or 'a web page'}, not a CSV table")
    return body


def get_one(source: Source, raw_dir: Path, manual_dir: Path | None, fetcher) -> tuple[str, str]:
    """Bring one table into raw_dir. Returns (status, url); never raises."""
    target = raw_dir / source.file_name
    if target.exists():
        return "present", source.page_url
    if manual_dir is not None and (manual_dir / source.file_name).is_file():
        shutil.copyfile(manual_dir / source.file_name, target)
        return "copied", source.page_url
    if not source.api_url:
        return f"failed: {source.note or 'no PSI study id'}", ""
    try:
        target.write_bytes(fetcher(source.api_url))
        return "downloaded", source.api_url
    except urllib.error.HTTPError as err:
        why = f"HTTP {err.code}"
        if err.code in (401, 403):
            why += " (PSI needs a signed-in session: download by hand, then use --from)"
        return f"failed: {why}", source.api_url
    except Exception as err:  # network down, timeout, a web page instead of a table, ...
        return f"failed: {err}", source.api_url


def run(
    raw_dir: Path = RAW_DIR,
    manual_dir: Path | None = None,
    sources: list[Source] = SOURCES,
    fetcher: Callable[[str], bytes] = fetch,
) -> list[dict]:
    """Try every source and write raw_dir/downloads.csv. Returns the log rows."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in sources:
        status, url = get_one(source, raw_dir, manual_dir, fetcher)
        (log.info if not status.startswith("failed") else log.warning)(
            "%s: %s", source.name, status
        )
        rows.append(
            {
                "name": source.name,
                "url": url or source.page_url,
                "status": status,
                "file": source.file_name,
                "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    with (raw_dir / "downloads.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--from", dest="manual_dir", type=Path, help="folder with tables downloaded from PSI"
    )
    args = parser.parse_args(argv)
    rows = run(manual_dir=args.manual_dir.expanduser() if args.manual_dir else None)
    ok = sum(not r["status"].startswith("failed") for r in rows)
    log.info("%d of %d tables in %s (log: downloads.csv)", ok, len(rows), RAW_DIR)


if __name__ == "__main__":
    sys.exit(main())
