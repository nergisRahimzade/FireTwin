"""BE-10: answer a chat question with an optional snapshot of the running scenario."""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas import ChatIn, ChatOut
from app.services import rag, store

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatOut,
    responses={
        404: {"description": "Unknown scenario, or history lost after a server restart"},
        500: {"description": "Chat service failed"},
    },
)
def chat(body: ChatIn) -> ChatOut:
    """Delegate retrieval and answering to RAG, without changing inputs or recording a step."""
    scenario = None
    if body.scenario_id is not None:
        try:
            saved = store.get(body.scenario_id)
        except store.ScenarioNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        scenario = {
            "scenario_id": body.scenario_id,
            "inputs": saved["inputs"].model_dump(mode="json"),
            "history": saved["history"],
        }
    try:
        return rag.answer(body.message, scenario)
    except Exception as error:
        log.exception("Chat service failed")
        raise HTTPException(status_code=500, detail="chat failed; see server log") from error
