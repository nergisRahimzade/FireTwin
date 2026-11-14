"""FastAPI app entry point (BE-05, Phase 0).

Creates the app, lets the Vite dev server call it (CORS), and serves GET /health.
The feature routers (simulate, detect, suppress, chat, export, meta) get plugged in here
by later tasks. Run it with `make dev` (uvicorn app.main:app --app-dir backend).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.schemas import HealthOut


def create_app() -> FastAPI:
    """Build a fresh app. A function (not just a global) so tests can build one per setting."""
    settings = get_settings()
    app = FastAPI(
        title="FireTwin API",
        version="0.1.0",
        description="Fire-safety digital twin of an ISS module, backed by NASA PSI data.",
    )

    # CORS: without this, the browser blocks the frontend (port 5173) from calling port 8000.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Liveness check: Docker Compose (OPS-02) and the E2E test (OPS-04) ping this.
    @app.get("/health", response_model=HealthOut, tags=["meta"])
    def health() -> HealthOut:
        return HealthOut(status="ok")

    return app


# The app uvicorn serves.
app = create_app()
