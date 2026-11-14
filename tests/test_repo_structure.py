"""Repo structure checks (OPS-01, Phase 0).

Makes sure the folders and root files from the "Repo structure" section of the
Implementation Tasks doc exist, so nobody deletes one by accident. It also gives
`make test` something real to run before any layer has its own tests.
"""

from pathlib import Path

import pytest

# Repo root, built from this file's location so the tests work from any working directory.
ROOT = Path(__file__).resolve().parents[1]

# Every folder in the planned tree (one per layer, plus their sub-folders).
REQUIRED_DIRS = [
    "data/raw",
    "data/clean",
    "data/processed",
    "data/docs",
    "data/pipeline",
    "data/tests",
    "ml/artifacts",
    "ml/tests",
    "backend/app/routers",
    "backend/app/services",
    "backend/app/mocks",
    "backend/tests",
    "frontend/src/api",
    "frontend/src/store",
    "frontend/src/scene",
    "frontend/src/tabs",
    "frontend/src/components",
    "docs",
    "tests",
]

# Root-level files that OPS-01 is responsible for.
REQUIRED_FILES = [
    "Makefile",
    ".env.example",
    ".gitignore",
    "pyproject.toml",
    ".python-version",
    "docker-compose.yml",
    "docs/CHANGELOG.md",
    "docs/contract.md",
    "CLAUDE.md",
    "AGENTS.md",
]

# The Makefile targets the plan asks for.
REQUIRED_MAKE_TARGETS = ["setup", "data", "train", "dev", "test", "lint"]


@pytest.mark.parametrize("folder", REQUIRED_DIRS)
def test_required_folder_exists(folder: str) -> None:
    assert (ROOT / folder).is_dir(), f"missing folder: {folder}"


@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_required_file_exists(filename: str) -> None:
    assert (ROOT / filename).is_file(), f"missing file: {filename}"


@pytest.mark.parametrize("target", REQUIRED_MAKE_TARGETS)
def test_makefile_has_target(target: str) -> None:
    # A make target is a line that starts with "<name>:".
    lines = (ROOT / "Makefile").read_text().splitlines()
    assert any(line.startswith(f"{target}:") for line in lines), f"no make target: {target}"


def test_agents_md_matches_claude_md() -> None:
    # AGENTS.md is a copy of CLAUDE.md so other coding agents get the same rules; keep them in sync.
    claude = (ROOT / "CLAUDE.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    assert agents == claude, "AGENTS.md differs from CLAUDE.md: copy CLAUDE.md over it"


def test_env_example_has_no_secret_value() -> None:
    # The template is committed, so its API key line must stay empty.
    lines = (ROOT / ".env.example").read_text().splitlines()
    assert "OPENAI_API_KEY=" in lines, "OPENAI_API_KEY must be present and left empty"
