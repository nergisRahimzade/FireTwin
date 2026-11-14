"""OPS-04: end-to-end check of the whole demo loop against a running FireTwin API.

Walks the same path the UI does: health -> meta -> simulate -> detect -> suppress -> apply ->
results -> export, checks every response against the contract (backend/app/schemas.py) and the
links between steps, and stops at the first failure, naming the step.

Run it at every milestone (plan: hours 10, 16 and 20) against the REAL API (MOCK_MODE=0):

    make e2e                                        # http://localhost:8000
    E2E_BASE_URL=http://localhost:8001 make e2e     # another server

Exit code 0 = the whole loop works. Against a mock-mode API it fails on purpose (the plan says
"hits the real API"); pass --allow-mock to check only the wiring.

The file name doesn't start with test_, so `make test` never tries to reach a server.
tests/test_e2e_loop.py runs this same loop in-process against the mock app instead.
"""

import argparse
import os
import sys
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas import (
    DetectOut,
    HealthOut,
    MetaOut,
    ResultsOut,
    SimulateOut,
    SuppressOut,
)

DEFAULT_BASE_URL = "http://localhost:8000"
# The demo script ignites cable insulation; use it when /meta offers it.
DEMO_MATERIAL = "cable insulation"
# BE-06 sets this OpenAPI description in mock mode, which is how the loop tells mock from real.
MOCK_MARKER = "Synthetic mock API"


class E2EError(Exception):
    """One step of the loop failed. `step` names it so the report says where to look."""

    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"{step}: {message}")
        self.step = step


def _check(step: str, condition: bool, message: str) -> None:
    # Fail loudly with the step's name instead of a bare AssertionError.
    if not condition:
        raise E2EError(step, message)


def _call(client: httpx.Client, step: str, method: str, path: str, json: dict | None = None):
    try:
        response = client.request(method, path, json=json)
    except httpx.HTTPError as exc:
        raise E2EError(step, f"request failed: {exc}") from exc
    _check(step, response.status_code == 200, f"HTTP {response.status_code}: {response.text[:300]}")
    return response


def _parse(step: str, model: type[BaseModel], response: httpx.Response) -> BaseModel:
    # Validating against schemas.py catches contract drift between backend and frontend.
    try:
        return model.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise E2EError(step, f"response doesn't match {model.__name__}: {exc}") from exc


def run_loop(
    client: httpx.Client, *, allow_mock: bool = False, log: Callable[[str], None] = print
) -> dict:
    """Run every step once. Returns a short summary; raises E2EError at the first failure."""
    _parse("health", HealthOut, _call(client, "health", "GET", "/health"))
    log("ok   health")

    description = (
        _call(client, "mode", "GET", "/openapi.json").json()["info"].get("description", "")
    )
    mock = description.startswith(MOCK_MARKER)
    _check(
        "mode",
        allow_mock or not mock,
        "API is in mock mode (MOCK_MODE=1); start it with "
        "MOCK_MODE=0, or pass --allow-mock to check only the wiring",
    )
    log(f"ok   mode: {'MOCK (wiring only)' if mock else 'real'}")

    meta = _parse("meta", MetaOut, _call(client, "meta", "GET", "/meta"))
    names = [m.get("name") for m in meta.materials]
    _check("meta", bool(names), "no materials to ignite")
    material = DEMO_MATERIAL if DEMO_MATERIAL in names else names[0]
    log(f"ok   meta: {len(names)} materials, igniting {material!r}")

    scenario = {"material": material, "o2_pct": 21, "flow_speed_cm_s": 10}
    sim = _parse("simulate", SimulateOut, _call(client, "simulate", "POST", "/simulate", scenario))
    _check("simulate", bool(sim.scenario_id), "empty scenario_id")
    _check("simulate", 0.0 <= sim.burn_probability <= 1.0, "burn_probability outside 0-1")
    _check("simulate", len(sim.nearest_tests) <= 3, "more than 3 nearest tests")
    synthetic = sum(ref.is_synthetic for ref in sim.nearest_tests)
    log(
        f"ok   simulate: {sim.state}, p={sim.burn_probability:.2f}, trust={sim.trust}, "
        f"{len(sim.nearest_tests)} sources ({synthetic} synthetic)"
    )
    ref = {"scenario_id": sim.scenario_id}

    det = _parse("detect", DetectOut, _call(client, "detect", "POST", "/detect", ref))
    if det.detected:
        _check("detect", det.time_to_detect_s is not None, "detected but no time_to_detect_s")
        ids = {d.get("id") for d in det.detectors}
        _check("detect", det.detector_id in ids, f"detector {det.detector_id!r} not in detectors")
        log(f"ok   detect: {det.detector_id} after {det.time_to_detect_s:.1f} s")
    else:
        log(f"ok   detect: not detected ({det.note})")

    sup = _parse("suppress", SuppressOut, _call(client, "suppress", "POST", "/suppress", ref))
    _check("suppress", sup.scenario_id == sim.scenario_id, "scenario_id changed")
    _check("suppress", bool(sup.actions), "no actions ranked")
    scores = [a.score for a in sup.actions]
    _check("suppress", scores == sorted(scores, reverse=True), "actions not sorted by score")
    _check("suppress", sup.recommended == sup.actions[0].action, "recommended isn't the top action")
    best = sup.actions[0]
    log(f"ok   suppress: {len(sup.actions)} actions, recommended {sup.recommended}")

    body = {**ref, "action": sup.recommended}
    applied = _parse("apply", SimulateOut, _call(client, "apply", "POST", "/apply", body))
    _check("apply", applied.scenario_id == sim.scenario_id, "scenario_id changed")
    # Plan BE-02: /apply re-runs the prediction at the action's new_inputs.
    _check("apply", applied.inputs == best.new_inputs, "inputs differ from the action's new_inputs")
    log(f"ok   apply: {sup.recommended} -> {applied.state}, p={applied.burn_probability:.2f}")

    path = f"/results/{sim.scenario_id}"
    results = _parse("results", ResultsOut, _call(client, "results", "GET", path))
    _check("results", results.scenario_id == sim.scenario_id, "scenario_id changed")
    _check("results", bool(results.rows), "no history rows")
    actions = [row.get("action") for row in results.rows]
    _check("results", sup.recommended in actions, "the apply step isn't in the history")
    log(f"ok   results: {len(results.rows)} rows")

    pdf = _call(client, "export", "GET", f"/export/{sim.scenario_id}.pdf")
    content_type = pdf.headers.get("content-type", "")
    _check("export", content_type.startswith("application/pdf"), f"content-type {content_type!r}")
    _check("export", pdf.content.startswith(b"%PDF"), "body is not a PDF")
    log(f"ok   export: {len(pdf.content)} bytes")

    return {"scenario_id": sim.scenario_id, "mock": mock, "rows": len(results.rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.getenv("E2E_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--allow-mock", action="store_true", help="accept a MOCK_MODE=1 API")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds per request")
    args = parser.parse_args(argv)

    print(f"e2e: {args.base_url}")
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        try:
            summary = run_loop(client, allow_mock=args.allow_mock)
        except E2EError as exc:
            print(f"FAIL {exc}")
            if exc.step == "health":
                print("     Is the API running? Start it with `make dev` or `docker compose up`.")
            return 1
    print(f"e2e: PASS ({'mock' if summary['mock'] else 'real'} API, {summary['rows']} result rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
