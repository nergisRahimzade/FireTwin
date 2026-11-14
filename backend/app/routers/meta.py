"""GET /meta (BE-07): the options the UI needs to build its controls.

Thin router: the logic lives in app/services/meta.py.
"""

from fastapi import APIRouter, HTTPException

from app.schemas import MetaOut
from app.services import meta as meta_service

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaOut)
def get_meta() -> MetaOut:
    """Materials (with n_tests), tested ranges per feature, and investigations."""
    try:
        return meta_service.build_meta()
    except meta_service.MetaUnavailableError as exc:
        # 503 = the API is running but its data isn't built yet; the message says what to run.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
