"""OPS-02: artifact fallback and explicit overrides without Docker, keys or ML loading.

Mode selection and command dispatch are checked on every OS. Real process replacement (exec) and
signal delivery are POSIX behaviour, so those tests run on Linux/macOS/WSL, like the container.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = str(ROOT / "docker/backend_entrypoint.py")
# Load the standalone entrypoint without depending on (or shadowing) the Docker Python SDK.
STARTUP = run_path(ENTRYPOINT)
REQUIRED_FILES = STARTUP["REQUIRED_FILES"]
select_mode = STARTUP["select_mode"]
# Real exec semantics (same pid, signals, exit status) exist only on POSIX, as in the container.
posix_only = pytest.mark.skipif(os.name != "posix", reason="needs POSIX exec semantics")


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


@posix_only
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


def test_entrypoint_hands_the_exact_command_to_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    # Any OS: replace the exec boundary and check what it receives, without replacing pytest.
    calls = []
    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setattr(
        os, "execvp", lambda file, args: calls.append((file, list(args), os.environ["MOCK_MODE"]))
    )
    command = ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0"]
    STARTUP["main"](command, os_name="posix")
    assert calls == [("uvicorn", command, "1")]


def test_entrypoint_refuses_native_windows_before_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_exec(*args):
        raise AssertionError("exec was called")

    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setattr(os, "execvp", no_exec)
    with pytest.raises(SystemExit, match="runs inside the Linux container"):
        STARTUP["main"](["uvicorn", "app.main:app"], os_name="nt")


# The stand-in server: report its pid, then exit 7 from its own SIGTERM handler.
SERVER = """import os, signal, sys
signal.signal(signal.SIGTERM, lambda *_: sys.exit(7))
print(os.getpid(), flush=True)
signal.pause()
"""


@posix_only
def test_exec_keeps_the_pid_so_termination_reaches_the_server(tmp_path: Path) -> None:
    # docker stop signals the container's main process: after exec that must be the server.
    output = tmp_path / "server.stdout"
    with output.open("w") as stdout:
        process = subprocess.Popen(
            [sys.executable, ENTRYPOINT, sys.executable, "-c", SERVER],
            env={**os.environ, "MOCK_MODE": "1"},
            cwd=tmp_path,
            stdout=stdout,
            text=True,
        )
    try:
        deadline = time.monotonic() + 5
        while len(lines := output.read_text().splitlines()) < 2:
            assert process.poll() is None, f"entrypoint exited before server readiness: {lines}"
            assert time.monotonic() < deadline, f"server readiness timed out: {lines}"
            time.sleep(0.02)
        assert lines[0] == "startup: synthetic mock mode"
        assert int(lines[1]) == process.pid  # replaced, not a child process
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 7  # the server's own handler ran; its status came back
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


@pytest.mark.skipif(os.name == "posix", reason="checks the real entrypoint on native Windows")
def test_native_windows_entrypoint_does_not_run_the_command(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, ENTRYPOINT, sys.executable, "-c", "print('SHOULD NOT RUN')"],
        env={**os.environ, "MOCK_MODE": "1"},
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "SHOULD NOT RUN" not in result.stdout
    assert "runs inside the Linux container" in result.stderr
