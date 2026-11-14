"""OPS-01 dev launcher: supervise both servers and clean up their process groups (POSIX).

`make dev` runs this. It starts whichever servers exist (backend, frontend), stops all of them when
one exits, and on Ctrl+C stops them gracefully, waiting up to GRACE_PERIOD_S before force-killing.
Press Ctrl+C a second time (after REPEAT_WINDOW_S) to force-stop at once.
"""

import os
import signal
import subprocess
import time
from pathlib import Path
from types import FrameType

# How long servers get to shut down cleanly before they are force-killed.
GRACE_PERIOD_S = 5.0
# One Ctrl+C reaches us twice: the terminal signals the whole process group, and `uv run` also
# forwards it. A repeat inside this window is that echo, not the user pressing Ctrl+C again.
REPEAT_WINDOW_S = 1.0


class _StopRequests:
    """Signal handler that remembers the first stop request and spots a deliberate second one."""

    def __init__(self) -> None:
        self.first_signal = 0  # 0 = nobody asked us to stop yet
        self.first_at = 0.0
        self.forced = False  # True = the user pressed Ctrl+C again: skip the grace period

    def __call__(self, signum: int, frame: FrameType | None) -> None:
        now = time.monotonic()
        if not self.first_signal:
            self.first_signal, self.first_at = signum, now
        elif now - self.first_at >= REPEAT_WINDOW_S:
            self.forced = True


def _signal_group(process: subprocess.Popen, signum: int) -> None:
    # The leader may have failed while its reloader/server descendants are still alive.
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _group_exists(process: subprocess.Popen) -> bool:
    process.poll()  # Reap a finished leader before checking its process group.
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    return True


def _stop_servers(processes: list[subprocess.Popen], requests: _StopRequests) -> None:
    for process in processes:
        _signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + GRACE_PERIOD_S
    while any(_group_exists(process) for process in processes):
        if requests.forced or time.monotonic() >= deadline:
            reason = "second Ctrl+C" if requests.forced else "shutdown timed out"
            print(f"dev: {reason}; force-stopping servers", flush=True)
            for process in processes:
                _signal_group(process, signal.SIGKILL)
            break
        time.sleep(0.05)
    for process in processes:
        process.wait()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    servers: list[tuple[str, list[str], Path]] = []
    if (root / "backend/app/main.py").is_file():
        # Only the backend loads this file; the frontend does not receive keys from it.
        env_args = ["--env-file", str(root / ".env")] if (root / ".env").is_file() else []
        servers.append(
            (
                "backend (:8000)",
                [
                    "uv",
                    "run",
                    *env_args,
                    "uvicorn",
                    "app.main:app",
                    "--app-dir",
                    "backend",
                    "--reload",
                    "--reload-dir",
                    "backend",
                    "--port",
                    "8000",
                ],
                root,
            )
        )
    else:
        print("dev: skipping backend (no backend/app/main.py yet, BE-05)", flush=True)
    if (root / "frontend/package.json").is_file():
        servers.append(("frontend (:5173)", ["npm", "run", "dev"], root / "frontend"))
    else:
        print("dev: skipping frontend (no frontend/package.json yet, FE-01)", flush=True)
    if not servers:
        return 0

    requests = _StopRequests()
    previous = {
        signum: signal.signal(signum, requests) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    processes: list[subprocess.Popen] = []
    try:
        for name, command, cwd in servers:
            if requests.first_signal:
                break
            print(f"dev: starting {name}", flush=True)
            # start_new_session: each server gets its own process group, so one killpg reaches
            # the server and everything it started (uvicorn's reloader, Vite's esbuild, ...).
            processes.append(subprocess.Popen(command, cwd=cwd, start_new_session=True))
        while not requests.first_signal:
            for (name, _, _), process in zip(servers, processes):
                status = process.poll()
                if status is not None:
                    print(f"dev: {name} exited (status {status}); stopping servers", flush=True)
                    # A negative status means "killed by signal N"; shells report that as 128 + N.
                    return status if status >= 0 else 128 - status
            time.sleep(0.05)
        print("dev: stopping servers (press Ctrl+C again to force)", flush=True)
        return 128 + requests.first_signal
    except OSError as error:
        print(f"dev: could not start server: {error}", flush=True)
        return 1
    finally:
        _stop_servers(processes, requests)
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
