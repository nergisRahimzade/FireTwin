"""FastAPI app entry point (BE-05, Phase 0).

Creates the app and configures CORS. BE-06 mounts the fixed synthetic endpoints in mock mode;
real feature routers get plugged in by later tasks. Run it with `make dev`
(uvicorn app.main:app --app-dir backend).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.schemas import HealthOut


def create_app() -> FastAPI:
    """Build a fresh app. A function (not just a global) so tests can build one per setting."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Report the captured effective mode, never the Settings object or provider keys.
        mode = (
            "synthetic mock mode (MOCK_MODE=1)" if settings.mock_mode else "real mode (MOCK_MODE=0)"
        )
        print(f"FireTwin API: {mode}", flush=True)
        yield

    app = FastAPI(
        title="FireTwin API",
        lifespan=lifespan,
        version="0.1.0",
        description=(
            "Synthetic mock API for frontend development. All outcomes and citations are fixed "
            "placeholders, not NASA evidence; valid request values are intentionally ignored."
            if settings.mock_mode
            else "Fire-safety digital twin of an ISS module, backed by NASA PSI data."
        ),
    )

    # CORS: without this, the browser blocks the frontend (port 5173) from calling port 8000.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Liveness check, in both modes: Docker Compose (OPS-02) and the E2E test (OPS-04) ping this.
    @app.get("/health", response_model=HealthOut, tags=["meta"])
    def health() -> HealthOut:
        return HealthOut(status="ok")

    if settings.mock_mode:
        # Mock routes live in their own module (app/mocks), so no real router or service
        # ever contains mock code.
        from app.mocks.router import router

        app.include_router(router)
    else:
        # Real routers, imported only here: they load pandas, the model and the data files,
        # which mock mode must not need. All planned feature routes have real routers.
        from app.routers import chat, detect, export, meta, preview, results, simulate, suppress

        app.include_router(simulate.router)  # POST /simulate, POST /apply (BE-02)
        app.include_router(preview.router)  # POST /preview: verdict only, no scenario (BE-05)
        app.include_router(meta.router)  # GET /meta (BE-07)
        app.include_router(detect.router)  # POST /detect (BE-03 service)
        app.include_router(suppress.router)  # POST /suppress (BE-04 service)
        app.include_router(results.router)  # GET /results/{scenario_id} (BE-08)
        app.include_router(export.router)  # GET /export/{scenario_id}.pdf (BE-09)
        app.include_router(chat.router)  # POST /chat (BE-10)

    return app


# The app uvicorn serves.
app = create_app()
