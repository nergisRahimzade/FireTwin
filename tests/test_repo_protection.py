"""OPS-01: raw uploads/private plans stay local; demo artifacts remain publishable."""

import os
import subprocess
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]
RAW_DIRS = (
    "BASS",
    "BASS2",
    "FLEX",
    "FLEX2",
    "SAFFIRE-II_F1C1_DistortionGrid-30mmBlock_1280x916_color",
    "SAME",
    "SAME-R",
    "Saffire",
    "Saffire2",
    "Saffire3",
    "raw-uploads",
    "uploads",
)
PRIVATE_PLANS = (
    "FireTwin — Project Overview.pdf",
    "FireTwin — Implementation Tasks (2).pdf",
    "docs/plan/Mentor Notes.pdf",
    "notes/FireTwin - Project Overview (copy).pdf",
)
PUBLIC_FILES = (
    ".env.example",
    "data/raw/.gitkeep",
    "data/clean/bass_ii.csv",
    "data/processed/tests.parquet",
    "data/processed/investigations.json",
    "data/docs/FLEX/flex_psi_description.txt",
    "data/pipeline/download.py",
    "data/tests/test_clean.py",
    "ml/artifacts/model.joblib",
)


def git(*args: str, cwd: Path = ROOT, input: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-c", f"core.excludesFile={os.devnull}", *args],
        cwd=cwd,
        input=input,
        capture_output=True,
        check=True,
    ).stdout


@pytest.fixture
def ignore_repo(tmp_path: Path) -> Path:
    git("init", "--quiet", cwd=tmp_path)
    (tmp_path / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
    return tmp_path


def test_local_source_and_secret_paths_are_ignored(ignore_repo: Path) -> None:
    paths = [
        *PRIVATE_PLANS,
        *(f"data/{folder}/nested/source.mp4" for folder in RAW_DIRS),
        "data/raw/download.csv",
        ".local/rag-bundle/bundle.json",
        ".local/.rag-bundle-build/model/onnx/model.onnx",
        ".env",
        ".env.local",
    ]
    ignored = git(
        "check-ignore",
        "--no-index",
        "-z",
        "--stdin",
        cwd=ignore_repo,
        input=b"\0".join(p.encode() for p in paths) + b"\0",
    )
    assert set(ignored.decode().split("\0")) - {""} == set(paths)


def test_runtime_and_pipeline_files_remain_publishable(ignore_repo: Path) -> None:
    # A public file can be force-added even if ignored. Ask Git about ignore status directly.
    for path in PUBLIC_FILES:
        result = subprocess.run(
            ["git", "-c", f"core.excludesFile={os.devnull}", "check-ignore", "--no-index", path],
            cwd=ignore_repo,
            capture_output=True,
        )
        assert result.returncode == 1, f"required public file is ignored: {path}"


def test_index_contains_no_private_plans_or_raw_uploads() -> None:
    paths = git("ls-files", "-z").decode().split("\0")
    forbidden = []
    for name in filter(None, paths):
        path = PurePosixPath(name)
        private_plan = path.suffix.lower() == ".pdf" and (
            path.parts[:2] == ("docs", "plan")
            or (
                path.name.startswith("FireTwin")
                and any(
                    title in path.name for title in ("Project Overview", "Implementation Tasks")
                )
            )
        )
        raw = (
            path.parts[0] == "data"
            and len(path.parts) > 1
            and (
                path.parts[1] in RAW_DIRS
                or (path.parts[1] == "raw" and name != "data/raw/.gitkeep")
            )
        )
        if private_plan or raw:
            forbidden.append(name)
    assert not forbidden, f"untrack local-only files before committing: {forbidden}"


def test_index_contains_no_blobs_over_github_limit() -> None:
    entries = git("ls-files", "--stage", "-z").split(b"\0")
    blobs = {}
    for entry in filter(None, entries):
        metadata, path = entry.split(b"\t", 1)
        blobs[metadata.split()[1]] = path.decode()
    sizes = git("cat-file", "--batch-check", input=b"\n".join(blobs) + b"\n")
    oversized = []
    for row in sizes.splitlines():
        oid, kind, size = row.split()
        if kind == b"blob" and int(size) > 100 * 1024 * 1024:
            oversized.append(blobs[oid])
    assert not oversized, f"blobs exceed GitHub's 100 MiB limit: {oversized}"
