"""BE-06 mock-only API. Request models are validated, then fixed responses are returned.

/health is not here: main.py defines it once, so it exists in mock and real mode alike.
"""

from pathlib import Path

from fastapi import APIRouter, Response

from app.mocks import responses
from app.schemas import (
    ApplyIn,
    ChatIn,
    ChatOut,
    DetectOut,
    MetaOut,
    PreviewOut,
    ResultsOut,
    ScenarioIn,
    ScenarioRef,
    SimulateOut,
    SuppressOut,
)

router = APIRouter(tags=["synthetic mocks"])


@router.get("/meta", response_model=MetaOut)
def meta() -> MetaOut:
    return responses.META


@router.post("/simulate", response_model=SimulateOut)
def simulate(inputs: ScenarioIn) -> SimulateOut:
    """Return a fixed synthetic scenario; request inputs are intentionally ignored."""
    return responses.SIMULATE


@router.post("/preview", response_model=PreviewOut)
def preview(inputs: ScenarioIn) -> PreviewOut:
    """Return a fixed synthetic verdict (is_synthetic=true); request inputs are ignored."""
    return responses.PREVIEW


@router.post("/detect", response_model=DetectOut)
def detect(scenario: ScenarioRef) -> DetectOut:
    return responses.DETECT


@router.post("/suppress", response_model=SuppressOut)
def suppress(scenario: ScenarioRef) -> SuppressOut:
    return responses.SUPPRESS


@router.post("/apply", response_model=SimulateOut)
def apply_action(request: ApplyIn) -> SimulateOut:
    """Return the fixed synthetic applied outcome, regardless of the selected action."""
    return responses.APPLY


@router.get("/results/{scenario_id}", response_model=ResultsOut)
def results(scenario_id: str) -> ResultsOut:
    return responses.RESULTS


@router.post("/chat", response_model=ChatOut)
def chat(request: ChatIn) -> ChatOut:
    return responses.CHAT


@router.get(
    "/export/{scenario_id}.pdf",
    response_class=Response,
    responses={
        200: {
            "description": "Fixed synthetic PDF fixture (not a generated NASA report)",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def export(scenario_id: str) -> Response:
    return Response(
        content=Path(__file__).with_name("export.pdf").read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="firetwin-synthetic.pdf"'},
    )
