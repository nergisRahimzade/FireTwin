"""OPS-02 container startup: choose mock mode before importing the backend, then exec it."""

import os
import sys
from pathlib import Path

# These are the files loaded by the predictor's table/model/range readers.
REQUIRED_FILES = (
    "data/processed/tests.parquet",
    "ml/artifacts/model.joblib",
    "ml/artifacts/feature_ranges.json",
)


def select_mode(root: Path, requested: str) -> str:
    """Respect explicit 0/1; auto-select on blank/unset without loading model contents."""
    requested = requested.strip()
    if requested not in {"", "0", "1"}:
        raise ValueError("MOCK_MODE must be blank (automatic), '0', or '1' in Docker")
    if requested == "1":
        return "1"
    missing = [
        name
        for name in REQUIRED_FILES
        if not (root / name).is_file() or (root / name).stat().st_size == 0
    ]
    if missing and requested == "0":
        raise ValueError("MOCK_MODE=0 requires nonempty files: " + ", ".join(missing))
    return "1" if missing else "0"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    try:
        mode = select_mode(root, os.environ.get("MOCK_MODE", ""))
    except ValueError as error:
        raise SystemExit(f"startup: {error}") from None
    os.environ["MOCK_MODE"] = mode
    print(
        "startup: synthetic mock mode" if mode == "1" else "startup: real mode (artifacts present)",
        flush=True,
    )
    command = sys.argv[1:]
    if not command:
        raise SystemExit("startup: no server command supplied")
    # Replace Python so Docker signals reach the server directly; no shell wrapper remains.
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
