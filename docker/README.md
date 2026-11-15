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

Only `data/processed/`, `data/docs/` and `ml/artifacts/` are read-only bind mounts.
Raw uploads, clean intermediate CSVs and pipeline scripts are not mounted into the backend.
The processed table/metadata and cited text corpus remain available to the API. Their tracked directories
must exist; Compose will not silently create missing host paths. Training and downloads happen
outside these containers. Runtime source and dependencies live in the images, and so do the
tracked `data/processed/`, `data/docs/` and `ml/artifacts/` files, so the backend image also runs
real mode on its own (for a hosted deploy without bind mounts). Private plan PDFs, local env files,
host environments, caches and raw downloaded data are excluded from the build context.

## Choosing and checking the mode

The backend prints `FireTwin API: synthetic mock mode (MOCK_MODE=1)` or
`FireTwin API: real mode (MOCK_MODE=0)` at startup, both natively and in Docker.
In Docker, `docker compose logs backend` also includes the entrypoint's selection message.
These messages identify routing mode; real mode does not certify model accuracy or data quality.

For real mode on POSIX/WSL:

```sh
MOCK_MODE=0 docker compose up --build
# Native POSIX development, with uv/npm installed:
MOCK_MODE=0 make dev
```

For Docker Desktop's Linux engine from PowerShell:

```powershell
$env:MOCK_MODE = '0'
docker compose up --build
# To return to automatic selection for later Docker commands:
Remove-Item Env:MOCK_MODE
```

Use `1` to explicitly select synthetic mocks. An exported shell setting takes precedence
over a root `.env`; an unset shell setting allows `.env` to supply the value. Blank mode
is automatic only in Docker: native startup still accepts only `0` or `1` and defaults to `1`.
The native launcher loads `.env` only for the backend, while tests never load it.
Only the named Compose settings are forwarded; the frontend never receives provider keys.

If required artifact **files** are missing or empty, automatic mode selects mocks and
explicit real mode fails with the missing filenames. Missing mount **directories** fail
before the entrypoint: restore the tracked directories rather than letting Docker create
empty paths as root. Downloads and training remain host-side tasks.

The default stack mounts no vector database or embedding cache and uses keyword fallback.
The optional local-vector bundle setup below adds a prepared index and model cache.

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
the mode-selection tests need neither Docker nor ML packages. Compose configuration checks
use the Docker Compose CLI without requiring a running engine, and skip explicitly when
the CLI is unavailable. Container checks additionally cover image
builds, both health checks, the Vite-served API URL, browser CORS, the synthetic API responses and
PDF download, real-mode end-to-end operation, automatic missing-file fallback, provider settings,
non-root execution, and read-only mounts.

This task provides the development stack. It does not train a model, implement real feature
routes, fix frontend dependency versions, add CI, or publish a production deployment. The locked
frontend dependencies currently emit existing npm advisory warnings during image installation.

The implementation follows [Docker's health-based startup ordering](https://docs.docker.com/compose/how-tos/startup-order/)
and [uv's Docker integration](https://docs.astral.sh/uv/guides/integration/docker/).


## Optional offline vector retrieval

Prepare the bundle once, before an offline demo (Python 3.11 and locked dependencies
from `uv sync --locked --dev` are needed for this host-side command):

```sh
uv run python docker/rag_bundle.py prepare --output .local/rag-bundle
uv run python docker/rag_bundle.py verify --output .local/rag-bundle
docker compose -f docker-compose.yml -f docker-compose.rag.yml up --build
```

The prepare step explicitly uses local MiniLM even if an OpenAI key exists. First
provisioning downloads the public model weights (about 80 MB compressed); an offline
runtime does not download them. To reuse a previously extracted MiniLM cache:

```sh
uv run python docker/rag_bundle.py prepare --output .local/rag-bundle-v2 \
  --cache-source .local/rag-bundle/model
RAG_BUNDLE_DIR=./.local/rag-bundle-v2 docker compose \
  -f docker-compose.yml -f docker-compose.rag.yml up --build --force-recreate
```

PowerShell sets a custom source with `$env:RAG_BUNDLE_DIR='./.local/rag-bundle-v2'`
before the Compose command. No env setting is required for the default source path.

A bundle contains `store/`, the extracted `model/onnx/` cache, and a SHA-256 file
manifest. It is local/generated and ignored by Git. Existing output directories are
refused; rebuild a changed corpus into a new directory. The index builder runs in a
separate process so database handles close before the manifest is written. Bundles
contain the cited text metadata too: distribute only corpora the team may share.

The override mounts the bundle read-only at `/app/rag_bundle`. Startup verifies its
inventory/hashes and copies the index into the non-root user's writable `/app/chroma_db`.
The model remains read-only in the bundle. Startup logs a verified-vector-bundle line;
API queries never initialize/download missing local model files. An empty mounted
bundle directory selects keyword fallback; a missing host directory is a Compose error.
Corrupt bundles fail startup with a verification error. A different bundle with an
existing runtime copy requires recreating the container. Default Compose still works
without any bundle or override. The container copy is disposable on recreation.

**Never open the sealed bundle's index directly with Chroma, even for a query.** It can
write index files. Use the startup copy or copy `store/` into a separate writable
location for native use. Native queries can select an extracted model cache with
`FIRETWIN_EMBEDDING_CACHE=/path/to/bundle/model`.

Standalone ingest now uses local embeddings by default:
`uv run python ml/ingest_rag.py --embedding minilm --cache-dir /path/to/model-cache`.
OpenAI embeddings require explicit `--embedding openai` plus a key and query-time
network; they do not meet the local-vector offline policy. A key appearing later
never changes an index's recorded provider.

Indexes publish isolated generations with an atomic `CURRENT.json` pointer. Builders
never change an existing generation, though Chroma queries can write bookkeeping files.
Failed rebuilds leave the previous generation active. Search checks the
completion marker, chunk count, model/provider and corpus fingerprint; expected
unavailability returns keyword fallback with a warning once per path/reason. Old,
failed and in-use generation directories are retained; clean them up only offline
with readers/writers stopped. Publication is coherent, not a promise of power-loss
recovery or cross-machine distributed transactions. Legacy indexes need rebuilding.
Default-source indexes track current corpus files. Custom-source indexes validate
saved content; callers can supply expected `chunks=` to check external custom changes.

Verification should call `ml.ingest_rag.search` directly (or disable keyword fallback)
with a prepared copy and outbound networking blocked. A passing keyword-only result
does not establish that vector search worked. The normal pytest suite uses synthetic
embeddings; the prepared real-model rehearsal is a separate recorded runtime check.
