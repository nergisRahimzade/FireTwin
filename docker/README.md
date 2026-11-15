# OPS-02: run FireTwin with Docker Compose

Docker Desktop must be running its Linux engine (enable WSL integration when using WSL).
Host Python, uv, Node and npm are not required for this route: dependencies are installed inside
the images from `uv.lock` and `frontend/package-lock.json`. The first build needs network access
to download base images and dependencies; mock mode does not need external services at runtime.

From the repository root:

```sh
docker compose up --build
```

Open the frontend at `http://localhost:5173` and API docs at `http://localhost:8000/docs`.
On a fresh clone, plain `docker compose up` also builds the missing images. Use `--build` after
source or lockfile changes because source is copied into images rather than bind-mounted.

For detached startup that waits for both health checks:

```sh
docker compose up --build --wait
docker compose logs -f
```

Ctrl+C stops an attached `up`. For detached containers, run `docker compose down`.

## Startup mode and files

No `.env` is required. Compose passes only the settings explicitly listed in the YAML; an
optional root `.env` supplies those settings, but is never copied into an image. Only the backend
receives `OPENAI_API_KEY`, `GEMINI_API_KEY` and optional `OPENAI_MODEL`/`GEMINI_MODEL` settings;
the frontend receives only the public `VITE_API_URL`. Keys are optional: real mode works offline
through the existing fallback. Gemini takes precedence when both keys are set; blank model
settings retain the RAG service defaults.

- Unset/blank `MOCK_MODE`: the container chooses synthetic mocks when any required file below
  is absent or empty. With all files present, it chooses real mode.
- `MOCK_MODE=1`: always use the BE-06 synthetic fixtures, even when artifacts exist.
- `MOCK_MODE=0`: require all files; fail clearly if anything is missing instead of quietly
  serving synthetic data. Other flag values fail startup.

The required files are `data/processed/tests.parquet`, `ml/artifacts/model.joblib` and
`ml/artifacts/feature_ranges.json`, matching the predictor's table/model/range readers.
The startup check does not unpickle or validate their scientific contents; the real services
remain responsible for loading valid artifacts. Current main includes the real simulation,
detection, suppression, results, PDF and chat routes, with prebuilt demo artifacts. A fresh
clone without `.env` therefore starts in real mode; missing required files select mocks.

Copying `.env.example` to `.env` explicitly sets `MOCK_MODE=1`; remove that setting or leave its
value blank to use Docker's automatic selection. The native `make dev` flag behavior is unchanged:
its backend defaults to mock mode and accepts only `0`/`1`, so keep blank values Docker-specific.

Both `data/` and `ml/artifacts/` are read-only bind mounts. Their tracked placeholder directories
must exist; Compose will not silently create missing host paths. Training and downloads happen
outside these containers. Runtime source and dependencies live in the images; private plan PDFs,
local env files, host environments, caches, data and artifacts are excluded from the build context.

## Ports and frontend connection

Both processes listen on `0.0.0.0` inside their containers, but published host ports bind to
`127.0.0.1`. The frontend waits for backend health before starting. Python and Node service
processes run as non-root users, with an init process for signal forwarding/reaping.

To avoid another local dev stack without changing files:

```sh
BACKEND_PORT=18000 FRONTEND_PORT=15173 docker compose up --build --wait
```

This also adjusts the default browser API URL to `http://localhost:18000` and backend CORS origins
to port `15173`. Do not use `http://backend:8000` as the browser API URL: that name belongs to the
container network, not the user's browser. `VITE_API_URL` and `CORS_ORIGINS` can override these
defaults for a different browser host. Pass the same port/settings overrides on later Compose
commands when recreating the stack.

## Checks and boundaries

`make test` includes startup selection, explicit overrides, bad flags and command execution;
these unit tests need neither Docker nor ML packages. Container checks additionally cover image
builds, both health checks, the Vite-served API URL, browser CORS, the synthetic API responses and
PDF download, real-mode end-to-end operation, automatic missing-file fallback, provider settings,
non-root execution, and read-only mounts.

This task provides the development stack. It does not train a model, implement real feature
routes, fix frontend dependency versions, add CI, or publish a production deployment. The locked
frontend dependencies currently emit existing npm advisory warnings during image installation.

The implementation follows [Docker's health-based startup ordering](https://docs.docker.com/compose/how-tos/startup-order/)
and [uv's Docker integration](https://docs.astral.sh/uv/guides/integration/docker/).
