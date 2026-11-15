"""OPS-02: artifact fallback and explicit overrides without Docker, keys or ML loading."""

import os
import subprocess
import sys
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Load the standalone entrypoint without depending on (or shadowing) the Docker Python SDK.
STARTUP = run_path(str(ROOT / "docker/backend_entrypoint.py"))
REQUIRED_FILES = STARTUP["REQUIRED_FILES"]
select_mode = STARTUP["select_mode"]


@pytest.fixture
def ready_root(tmp_path: Path) -> Path:
    # File contents are deliberately not valid models: startup checks presence, not pickle data.
    for name in REQUIRED_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic test fixture")
    return tmp_path


def test_missing_artifacts_select_synthetic_mocks(tmp_path: Path) -> None:
    assert select_mode(tmp_path, "") == "1"


def test_complete_artifacts_select_real_mode(ready_root: Path) -> None:
    assert select_mode(ready_root, "") == "0"


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_each_missing_runtime_file_selects_mocks(ready_root: Path, name: str) -> None:
    (ready_root / name).unlink()
    assert select_mode(ready_root, "") == "1"


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_empty_runtime_file_selects_mocks(ready_root: Path, name: str) -> None:
    (ready_root / name).write_bytes(b"")
    assert select_mode(ready_root, "") == "1"


@pytest.mark.parametrize("requested", ["1", " 1 "])
def test_explicit_mock_mode_works_without_artifacts(tmp_path: Path, requested: str) -> None:
    assert select_mode(tmp_path, requested) == "1"


def test_explicit_mock_mode_overrides_available_artifacts(ready_root: Path) -> None:
    assert select_mode(ready_root, "1") == "1"


def test_explicit_real_mode_with_artifacts(ready_root: Path) -> None:
    assert select_mode(ready_root, "0") == "0"


def test_explicit_real_mode_rejects_missing_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MOCK_MODE=0 requires nonempty files"):
        select_mode(tmp_path, "0")


@pytest.mark.parametrize("requested", ["true", "false", "auto", "2"])
def test_bad_mode_fails_loudly(tmp_path: Path, requested: str) -> None:
    with pytest.raises(ValueError, match="MOCK_MODE"):
        select_mode(tmp_path, requested)


def test_entrypoint_passes_chosen_mode_to_command(tmp_path: Path) -> None:
    env = {**os.environ, "MOCK_MODE": "1"}
    env.pop("OPENAI_API_KEY", None)
    env.pop("GEMINI_API_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "docker/backend_entrypoint.py"),
            sys.executable,
            "-c",
            "import os; print('child-mode=' + os.environ['MOCK_MODE'])",
        ],
        env=env,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "child-mode=1" in result.stdout


def test_entrypoint_does_not_run_command_on_invalid_mode(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "docker/backend_entrypoint.py"),
            sys.executable,
            "-c",
            "print('SHOULD NOT RUN')",
        ],
        env={**os.environ, "MOCK_MODE": "bad"},
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "SHOULD NOT RUN" not in result.stdout
    assert "MOCK_MODE" in result.stderr
