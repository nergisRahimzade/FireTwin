"""GET /results/{scenario_id} (BE-08): the scenario's saved history, oldest first."""

from fastapi import APIRouter, HTTPException

from app.schemas import ResultsOut
from app.services import store

router = APIRouter(tags=["results"])


@router.get(
    "/results/{scenario_id}",
    response_model=ResultsOut,
    responses={404: {"description": "Unknown scenario, or history lost after a server restart"}},
)
def get_results(scenario_id: str) -> ResultsOut:
    """Read the recorded rows without re-running a calculation or changing the scenario."""
    try:
        rows = store.history(scenario_id)
    except store.ScenarioNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ResultsOut(scenario_id=scenario_id, rows=rows)
