"""OPS-03: the CI workflow keeps running the checks the plan asks for.

Plain-text checks on purpose: PyYAML isn't a project dependency, so CI couldn't import it.
"""

from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


@pytest.mark.parametrize(
    "command",
    [
        "uv sync --locked --dev",  # dependencies exactly as locked
        "make lint",  # ruff check + format check
        "make test",  # pytest for data, ml, backend and repo-wide tests
        "npm ci",
        "npm run typecheck",  # tsc
        "npm test",  # vitest
        "npm run build",
    ],
)
def test_ci_runs_planned_check(command: str) -> None:
    assert f"run: {command}\n" in WORKFLOW.read_text(), f"CI no longer runs: {command}"


def test_ci_runs_on_pull_requests_and_pushes_to_main() -> None:
    text = WORKFLOW.read_text()
    assert "  pull_request:\n" in text
    assert "  push:\n    branches: [main]\n" in text


def test_ci_token_is_read_only() -> None:
    # CI never needs to write to the repo; a read-only token limits damage from a bad dependency.
    assert "permissions:\n  contents: read\n" in WORKFLOW.read_text()


@pytest.mark.parametrize("name", ["Python (ruff + pytest)", "Frontend (tsc + vitest + build)"])
def test_required_check_names_are_unchanged(name: str) -> None:
    # Branch protection requires checks by these exact names; renaming one blocks every PR.
    assert f"    name: {name}\n" in WORKFLOW.read_text()


def test_windows_job_runs_the_startup_tests() -> None:
    text = WORKFLOW.read_text()
    assert "    runs-on: windows-latest\n" in text
    assert "run: uv run pytest tests/test_dev.py tests/test_container_startup.py\n" in text
