# OPS handoff: Windows startup and tests (package 2)

Original pre-integration handoff; see the Codex integration review at the end for current status.

For the integrator (Codex) and the next OPS owner. Package 2 of Ryan's fixes plan: native Windows
behaviour of `make dev` (`scripts/dev.py`) and the container entrypoint
(`docker/backend_entrypoint.py`), plus Windows CI coverage. Not pushed; no PR opened.

## 1. Base, branch, worktree

- Base: `origin/main` at `8355532dbf05538228bbad66aca6d2e7cca662d0` (PR #26 merged).
- Branch: `feature/OPS-windows-startup` (local only, no upstream set).
- Worktree: `/tmp/firetwin-claude-windows`.
- Commits, one task each:
  - `e055cd0` OPS-01: make dev stops before starting anything on native Windows
  - `2457acf` OPS-02: container entrypoint refuses native Windows; test exec and signals separately
  - `83553be` OPS-03: Windows CI job for the startup checks
  - this file, in a separate docs commit on top.

## 2. Root cause: reported vs verified

Platform used for verification: native Windows (WSL2 host, `win32`), CPython **3.12.10** from the
Python launcher (`py -3.12`). No Python 3.11 is installed on that Windows side, so 3.11 itself was
not exercised natively; the behaviour below is in CPython's Windows `os.exec*` and `os`/`signal`
modules and is the same on 3.11 to my knowledge, but that is not verified.

**Reported** (New fixes): `test_container_startup.py` fails on Windows "because the entrypoint uses
`os.execvp`".

**Verified**, by running main's (`8355532`) test file natively with pytest 9.2.0 in a throwaway
venv (`python -m pytest -p no:warnings tests/test_dev.py tests/test_container_startup.py`):

```
FAILED tests/test_container_startup.py::test_entrypoint_passes_chosen_mode_to_command
>       assert "child-mode=1" in result.stdout
E       assert 'child-mode=1' in 'startup: synthetic mock mode\n'
        ... returncode=0, stderr='  File "<string>", line 1\n    import\n  ^\nSyntaxError: invalid syntax\n'
tests\test_container_startup.py:91: AssertionError
1 failed, 18 passed, 15 skipped
```

`os.execvp` **is** available on Windows and does start the command. The real cause:

1. Windows `exec*` starts a *new* process and ends the caller; it is not a process replacement.
   The C runtime joins the arguments **without quoting**, so the child received
   `-c import os; print(...)` split into separate words, and ran only `import` (SyntaxError).
   Replacing the space with a tab splits the same way (probed).
2. The caller's exit status is not the server's: a child that exits 7 came back as **0** (probed).
   So on Windows a failing server would look like a successful start.

`-p no:warnings` was needed only because the project's warning filter imports
`starlette.exceptions`, which the minimal venv didn't have; CI does the full locked install.

**Launcher, verified natively** (`python scripts/dev.py` from main, in a temp project with a
sleeping stand-in backend reached through a venv `python.exe` copied as `uv.exe`, npm absent):

```
dev: starting backend (:8000)
dev: starting frontend (:5173)
dev: could not start server: [WinError 2] The system cannot find the file specified
  File "...\scripts\dev.py", line 41, in _signal_group
    os.killpg(process.pid, signum)
AttributeError: module 'os' has no attribute 'killpg'. Did you mean: 'kill'?
stand-in backend pid 14688 still running after dev.py exited: True
```

So native Windows produced exactly the partial stack the plan warns about: the backend kept
running after the launcher crashed (cleaned up with `taskkill`). Also probed on that Windows:
`os.killpg`, `os.setsid`, `signal.SIGKILL` and `signal.SIGUSR1` are all absent; `make` is not on
PATH; `npm` is not installed there, so **npm.cmd resolution was not exercised** (a list-form
`Popen(["npm", ...])` only finds `.exe` files, so it would fail even with Node installed).

Not verified: Git Bash/MSYS2/Cygwin Pythons (they may report `os.name == "posix"`), and macOS.

## 3. Changed files

- `scripts/dev.py`: on a non-POSIX `os.name` it prints the supported routes (Docker Desktop,
  WSL) and exits 2 before starting any server. The POSIX path is unchanged.
- `tests/test_dev.py`: the file-wide POSIX skip became a per-test `posix_only` marker on the nine
  real-process tests, so they run as before on Linux. New: an every-OS test of the Windows message
  (no `Popen` allowed), and a Windows-only test that runs the real launcher and checks nothing starts.
- `docker/backend_entrypoint.py`: `main()` takes optional `argv`/`os_name` for tests; on a
  non-POSIX OS it exits with a pointer to Docker Desktop instead of calling `os.execvp`. The
  Linux path still execs, so Docker signals reach uvicorn directly.
- `tests/test_container_startup.py`: mode-selection and invalid-mode tests still run everywhere.
  New every-OS tests stub `os.execvp` to check the exact command and mode handed over, and the
  Windows refusal. The real exec test is POSIX-only, plus a new one: same pid after exec, SIGTERM
  handled by the server itself, its exit status returned. A Windows-only test runs the real script.
- `.github/workflows/ci.yml`: new job `Windows (startup checks)` on `windows-latest`: locked
  `uv sync`, then `uv run pytest tests/test_dev.py tests/test_container_startup.py` (no make).
- `tests/test_ci_workflow.py`: guards the two required check names and the Windows job command.

## 4. Validation

Linux (WSL2 Ubuntu, worktree `.venv` from `uv.lock`, Python 3.11):

- `make lint`: `All checks passed!` / `99 files already formatted`
- `make test`: `594 passed, 5 skipped in 21.04s` (the 5 = main's 3 + the 2 Windows-only tests)
- `uv run pytest tests/test_dev.py -q`: `16 passed, 1 skipped`
- `uv run pytest tests/test_container_startup.py -q`: `22 passed, 1 skipped`

Native Windows (Python 3.12.10, pytest 9.2.0, throwaway venv, `-p no:warnings`), this branch:

- `23 passed, 17 skipped`, exit 0. The 17 skips are the POSIX-only process/exec tests.

Linux Docker (signals still reach uvicorn): built `docker/backend.Dockerfile` under a test tag, ran
`docker run -d --init -e MOCK_MODE=1` (no published ports, like Compose's `init: true`):

- process tree: `docker-init` -> `/opt/venv/bin/python /opt/venv/bin/uvicorn ...` (no Python
  entrypoint process left: exec replaced it);
- `docker stop -t 10`: 0.49 s, uvicorn logged `Shutting down` ... `Finished server process`,
  exit code 143 (SIGTERM). Test container and image removed afterwards.

**Not verified:** the new Windows CI job has never run (nothing pushed). Its locked `uv sync` on
`windows-latest` (wheel availability for every locked package on Windows) is the main risk;
the first PR run settles it. Native `make dev` support was not built (out of scope by policy).

## 5. Ready-to-append entries for shared docs

**`docs/OPS_NOTES.md`**, new section at the end:

```markdown
## OPS-01 / OPS-02 / OPS-03: Windows support boundary (2026-11-15, Ryan)

**Chosen (the plan doesn't mention Windows)**
- Supported on Windows: Docker Desktop with Linux containers (`docker compose up --build`), or
  WSL (`make setup && make dev` in an Ubuntu shell, repo cloned inside WSL). Native Windows
  `make dev` is **not** supported: the launcher needs POSIX process groups and signals.
- `scripts/dev.py` on native Windows prints both routes and exits 2 before starting anything.
  Before this, it could start the backend, crash in `os.killpg` and leave the backend running.
- `docker/backend_entrypoint.py` is for the Linux container only. On native Windows `os.execvp`
  starts a new process, drops argument quoting and loses the exit status (reproduced), so the
  entrypoint refuses there instead. In Linux Docker it still execs; `docker stop` reaches uvicorn.
- Tests: real process/exec/signal tests are POSIX-only; mode selection, invalid modes, command
  dispatch (stubbed exec) and the Windows refusals run on every OS.
- CI: extra job `Windows (startup checks)` runs those two test files on `windows-latest` with
  pytest directly (the Makefile needs a POSIX shell). Required check names are unchanged; whether
  to make the new job required is a repo-owner decision.
- Supersedes the OPS-01 note "`tests/test_dev.py` is skipped on non-POSIX systems".
```

**`docs/CHANGELOG.md`**, under `## 2026-11-15`:

```markdown
- **OPS-01**: `make dev` stops before starting anything on native Windows and names the supported
  routes (Docker Desktop, WSL); `tests/test_dev.py` tests that boundary on every OS.
- **OPS-02**: the container entrypoint refuses native Windows (exec there loses argument quoting and
  exit status); exec dispatch is tested on every OS, real exec/SIGTERM/exit status on POSIX.
- **OPS-03**: new CI job `Windows (startup checks)`; required check names unchanged and tested.
```

## 6. Outside my file boundary / integration prerequisites

- No changes needed outside the assigned files.
- Integration: append the two entries above, and mark the old OPS-01 skip note as superseded.
- Repo owner: decide whether `Windows (startup checks)` becomes a required check (it isn't yet).
- Package 3 overlap: the launcher message says `docker compose up --build`, which matches
  `docker/README.md` after #27 (it documents `MOCK_MODE=0` and the PowerShell form separately).
  No wording change needed. This branch still merges cleanly with main `fd5ec94`.
- If native Windows `make dev` is wanted later, it needs its own process-control design (job
  objects, `npm.cmd` resolution, Ctrl+Break handling) and testing on Windows; not started here.

## 7. Review notes on #26 and #27 for the next docs build (Codex)

Reviewed after both merged (main `fd5ec94`). No code defects found; #27's real-mode Compose run
was re-verified independently (separate project, temporary ports: both services healthy, both
mode lines logged, only `docs`/`processed` under `/app/data`, raw stand-in invisible, mount
read-only, `make e2e` PASS). Small items for `feature/OPS-01-docs-reconciliation`:

1. `docs/OPS_NOTES.md`, section "OPS-02: runtime mounts and mode visibility": the bullet ending
   "Startup mode visibility is described under BE-05 below." points the wrong way; the BE-05
   section is directly *above* it. Say "above".
2. `docs/CHANGELOG.md`, `## 2026-11-15`: a blank line separates the new OPS-02/BE-05 bullets
   from the OPS-01 bullet, splitting one list into two. Remove the blank line.
3. `backend/app/main.py` lifespan uses `print` for the mode line. It matches the entrypoint's
   `print`, so optional, but the team style prefers `logging` (level from `LOG_LEVEL`). If
   changed, keep `backend/tests/test_startup_mode.py` asserting the line still appears and no
   key is printed.
4. Record for teammates (OPS_NOTES, under the #26 cleanup note): updating an older checkout
   (e.g. one at `b01b110`) to current main deletes the raw upload folders and root plan PDFs
   from that working tree. Plan copies under `docs/plan/` are untouched (ignored); raw files
   stay recoverable from history (`b01b110`), but copy them outside the repo first if needed.
5. Process: #26 and #27 were merged with no review recorded on GitHub. Next PRs should get a
   recorded review before merge, per "don't merge into main until the team says so".
6. Environment: `/tmp` on this machine is a 7.7 GB tmpfs (92 % full) and is wiped on WSL
   restart. Worktrees there lose uncommitted work; commit early or use a disk-backed path.


## Codex integration review

Original Claude branch remains untouched. Integration uses a separate branch based on
main `3ce0587`, retaining the task-separated implementation commits. Shared-doc entries
are integrated in OPS_NOTES and CHANGELOG; small doc review corrections were pushed to
PR #29. Optional conversion of startup print to logging was not necessary for behavior.
The real exec regression now uses a bounded readiness wait instead of blocking readline.
Native Windows evidence above is Claude's Python 3.12 report; Codex verification is Linux
Python 3.11, with the new Windows Python 3.11 CI job providing the remaining platform check.

Codex checks: `make lint` passed (104 files); `make test`: 604 passed, 5 skipped in
24.69s. The two extra skips are native-Windows checks on this Linux host.
