"""OPS-01 regression checks for make dev, using local processes instead of real servers."""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

# scripts/dev.py relies on POSIX process groups (os.killpg), which Windows doesn't have.
pytestmark = pytest.mark.skipif(os.name != "posix", reason="make dev is POSIX-only")

ROOT = Path(__file__).resolve().parents[1]

# Each fake server has a descendant, so killing only the wrapper cannot pass these checks.
SERVER = '''import os, signal, subprocess, sys, time
from pathlib import Path
role = "backend" if Path(sys.argv[0]).name == "uvicorn" else "frontend"
folder = Path(os.environ["DEV_TEST_DIR"])
child_code = """import os, signal, sys, time
from pathlib import Path
folder, role = Path(sys.argv[1]), sys.argv[2]
def stop(signum, frame):
    if os.environ.get("DEV_TEST_IGNORE_TERM"):
        return
    (folder / (role + ".stopped")).touch()
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
(folder / (role + ".ready")).touch()
while True: time.sleep(0.05)
"""
child = subprocess.Popen([sys.executable, "-c", child_code, str(folder), role])
def stop(signum, frame):
    child.wait(timeout=3)
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGUSR1, lambda *_: sys.exit(42))
# Record what this server got from .env, so tests can check where the file was loaded.
(folder / (role + ".secret")).write_text(os.environ.get("DEV_TEST_SECRET", ""))
(folder / (role + ".pid")).write_text(str(os.getpid()))
while True: time.sleep(0.05)
'''


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "Makefile").write_bytes((ROOT / "Makefile").read_bytes())
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/dev.py").write_bytes((ROOT / "scripts/dev.py").read_bytes())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Use the current interpreter; this uv stand-in never syncs or installs anything.
    uv = bin_dir / "uv"
    # Drops "run"; like real uv, --env-file loads KEY=value lines into the command's environment.
    # The outer command is `uv run python scripts/dev.py`, so `python` maps to this interpreter.
    uv.write_text(
        "#!/bin/sh\nshift\n"
        'if [ "$1" = --env-file ]; then set -a; . "$2"; set +a; shift 2; fi\n'
        f'if [ "$1" = python ]; then shift; exec "{sys.executable}" "$@"; fi\n'
        'exec "$@"\n'
    )
    uv.chmod(0o755)
    for name in ("uvicorn", "npm"):
        command = bin_dir / name
        command.write_text(f"#!{sys.executable}\n" + SERVER)
        command.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("DEV_TEST_DIR", str(tmp_path))
    # Only a .env file written by a test may set this.
    monkeypatch.delenv("DEV_TEST_SECRET", raising=False)
    return tmp_path


def _enable_server(project: Path, role: str) -> None:
    entry = project / ("backend/app/main.py" if role == "backend" else "frontend/package.json")
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("" if role == "backend" else "{}")


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 5
    while not path.exists():
        assert time.monotonic() < deadline, f"timed out waiting for {path.name}"
        time.sleep(0.02)


@pytest.fixture
def running_dev(project: Path):
    processes = []

    def start(roles: tuple[str, ...]) -> subprocess.Popen:
        for role in roles:
            _enable_server(project, role)
        process = subprocess.Popen(
            ["make", "dev"],
            cwd=project,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        processes.append(process)
        for role in roles:
            _wait_for(project / f"{role}.pid")
            _wait_for(project / f"{role}.ready")
        return process

    yield start
    # Keep a failed assertion from leaving any stand-in server running.
    for path in project.glob("*.pid"):
        try:
            os.killpg(int(path.read_text()), signal.SIGKILL)
        except ProcessLookupError:
            pass
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate(timeout=5)


def test_dev_skips_when_both_layers_are_missing(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make = shutil.which("make")
    # No uv anywhere on PATH: skipping must not call it (it would create .venv on a fresh clone).
    (project / "bin/uv").unlink()
    monkeypatch.setenv("PATH", str(project / "bin"))
    result = subprocess.run([make, "dev"], cwd=project, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert "skipping backend" in result.stdout
    assert "skipping frontend" in result.stdout


def test_missing_frontend_command_is_reported(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_server(project, "frontend")
    (project / "bin/npm").unlink()
    # Do not fall through to a real npm installation on a teammate's machine.
    monkeypatch.setenv("PATH", str(project / "bin"))
    result = subprocess.run(
        [sys.executable, str(project / "scripts/dev.py")],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 1
    assert "dev: could not start server" in result.stdout


@pytest.mark.parametrize("failed_role", ["backend", "frontend"])
def test_server_failure_stops_both_process_groups(project: Path, running_dev, failed_role) -> None:
    process = running_dev(("backend", "frontend"))
    os.kill(int((project / f"{failed_role}.pid").read_text()), signal.SIGUSR1)
    output, _ = process.communicate(timeout=10)
    assert process.returncode != 0
    assert "status 42" in output
    assert (project / "backend.stopped").exists()
    assert (project / "frontend.stopped").exists()


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("roles", [("backend",), ("frontend",), ("backend", "frontend")])
def test_signal_stops_every_server_group(project: Path, running_dev, signum: int, roles) -> None:
    process = running_dev(roles)
    os.killpg(process.pid, signum)
    process.communicate(timeout=10)
    for role in roles:
        assert (project / f"{role}.stopped").exists()


def test_shutdown_escalates_for_unresponsive_descendant(
    project: Path, running_dev, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEV_TEST_IGNORE_TERM", "1")
    process = running_dev(("backend",))
    os.killpg(process.pid, signal.SIGTERM)
    output, _ = process.communicate(timeout=10)
    assert "shutdown timed out; force-stopping servers" in output
    assert not (project / "backend.stopped").exists()


def test_env_file_reaches_backend_only(project: Path, running_dev) -> None:
    (project / ".env").write_text("DEV_TEST_SECRET=from-dotenv\n")
    running_dev(("backend", "frontend"))
    assert (project / "backend.secret").read_text() == "from-dotenv"
    assert (project / "frontend.secret").read_text() == ""


def test_echoed_stop_request_still_stops_gracefully(project: Path, running_dev) -> None:
    process = running_dev(("backend",))
    # Back to back, like one Ctrl+C from the terminal plus the copy `uv run` forwards.
    os.killpg(process.pid, signal.SIGINT)
    os.killpg(process.pid, signal.SIGINT)
    output, _ = process.communicate(timeout=10)
    assert "force-stopping" not in output
    assert (project / "backend.stopped").exists()


def test_second_stop_request_forces_shutdown(
    project: Path, running_dev, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEV_TEST_IGNORE_TERM", "1")
    process = running_dev(("backend",))
    os.killpg(process.pid, signal.SIGINT)
    time.sleep(1.3)  # longer than REPEAT_WINDOW_S, so this counts as a deliberate second press
    os.killpg(process.pid, signal.SIGINT)
    output, _ = process.communicate(timeout=10)
    assert "second Ctrl+C; force-stopping servers" in output
