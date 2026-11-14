"""BE-09: download a PDF built from the same saved rows as /results."""

from fastapi import APIRouter, HTTPException, Response

from app.services import pdf, store

router = APIRouter(tags=["export"])


@router.get(
    "/export/{scenario_id}.pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"description": "Unknown scenario, or history lost after a server restart"},
    },
)
def export(scenario_id: str) -> Response:
    """Generate in memory; no report files, HTTP calls, or changes to the scenario."""
    try:
        content = pdf.export_scenario(scenario_id)
    except store.ScenarioNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="firetwin-results.pdf"'},
    )
