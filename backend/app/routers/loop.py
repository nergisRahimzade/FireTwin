"""The rest of the scenario loop in real mode: /detect, /suppress, /results, /chat, /export.

Thin routes over the services: each one looks the scenario up in the store, calls one service,
and (for /detect) records a history row. An unknown scenario_id is a 404.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

from app.schemas import ChatIn, ChatOut, DetectOut, ResultsOut, ScenarioIn, ScenarioRef, SuppressOut
from app.services import detector, pdf, rag, store, suppressor

log = logging.getLogger(__name__)

router = APIRouter(tags=["simulation"])


def _not_found(exc: store.ScenarioNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _failed(what: str, exc: Exception) -> HTTPException:
    log.exception("%s failed", what)
    return HTTPException(status_code=500, detail=f"{what} failed; see server log")


@router.post("/detect", response_model=DetectOut)
def detect(body: ScenarioRef) -> DetectOut:
    """When and where the smoke alarm trips for the scenario's current inputs."""
    try:
        inputs = store.get_inputs(body.scenario_id)
        result = detector.detect(inputs)
        last = (store.history(body.scenario_id) or [{}])[-1]
        store.append(
            body.scenario_id,
            "detect",
            detection_s=result.time_to_detect_s,
            sources=last.get("sources"),  # the tests behind the current verdict
        )
        return result
    except store.ScenarioNotFound as exc:
        raise _not_found(exc) from exc
    except Exception as exc:
        raise _failed(f"/detect for scenario {body.scenario_id}", exc) from exc


@router.post("/suppress", response_model=SuppressOut)
def suppress(body: ScenarioRef) -> SuppressOut:
    """Rank the suppression actions for the scenario's current inputs."""
    try:
        return suppressor.suppress(body.scenario_id, store.get_inputs(body.scenario_id))
    except store.ScenarioNotFound as exc:
        raise _not_found(exc) from exc
    except Exception as exc:
        raise _failed(f"/suppress for scenario {body.scenario_id}", exc) from exc


@router.get("/results/{scenario_id}", response_model=ResultsOut)
def results(scenario_id: str) -> ResultsOut:
    """The scenario's history as results-table rows, oldest first."""
    try:
        return ResultsOut(scenario_id=scenario_id, rows=store.history(scenario_id))
    except store.ScenarioNotFound as exc:
        raise _not_found(exc) from exc


def _scenario_summary(scenario_id: str) -> dict:
    """What the chat needs to know about the running scenario: inputs plus the latest verdict."""
    rows = store.history(scenario_id)
    verdicts = [r for r in rows if r["state"] is not None]
    detections = [r for r in rows if r["step"] == "detect"]
    latest = verdicts[-1] if verdicts else {}
    return {
        "inputs": store.get_inputs(scenario_id).model_dump(),
        "state": latest.get("state"),
        "burn_probability": latest.get("probability"),
        "trust": latest.get("trust"),
        "last_action": latest.get("action"),
        "detection_s": detections[-1]["detection_s"] if detections else None,
        "nearest_test_ids": latest.get("sources", []),
    }


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    """Answer a question from the NASA passages, with the scenario summary when one is given."""
    try:
        summary = _scenario_summary(body.scenario_id) if body.scenario_id else None
        return rag.answer(body.message, summary)
    except store.ScenarioNotFound as exc:
        raise _not_found(exc) from exc
    except Exception as exc:
        raise _failed("/chat", exc) from exc


@router.get(
    "/export/{scenario_id}.pdf",
    response_class=Response,
    responses={
        200: {
            "description": "The scenario's results table as a PDF",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def export(scenario_id: str) -> Response:
    """PDF of the results table, built from the same rows as /results."""
    try:
        rows = store.history(scenario_id)
        current = store.get_inputs(scenario_id)
        # Recommend for the inputs the scenario STARTED with, i.e. the fire as it was ignited.
        first = ScenarioIn(**rows[0]["inputs"]) if rows else current
        recommended = suppressor.suppress(scenario_id, first)
        label = next(a.label for a in recommended.actions if a.action == recommended.recommended)
        content = pdf.build_pdf(scenario_id, current, rows, label)
    except store.ScenarioNotFound as exc:
        raise _not_found(exc) from exc
    except Exception as exc:
        raise _failed(f"/export for scenario {scenario_id}", exc) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="firetwin-{scenario_id}.pdf"'},
    )
