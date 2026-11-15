"""Tests for the OPS-04 e2e loop, run in-process against the BE-06 mock app (no network)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.e2e_loop import E2EError, main, run_loop


def _quiet(_: str) -> None:
    # The loop prints one line per step; tests don't need them.
    pass


@pytest.fixture
def mock_api(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MOCK_MODE", "1")
    return TestClient(create_app())


def _broken(api: TestClient, path_prefix: str, response: httpx.Response) -> httpx.Client:
    """A client whose requests reach the mock app, except one path that returns `response`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith(path_prefix):
            return response
        real = api.request(
            request.method,
            request.url.path,
            content=request.content,
            headers={"content-type": "application/json"},
        )
        return httpx.Response(real.status_code, headers=real.headers, content=real.content)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://e2e")


def test_loop_passes_against_the_mock_app(mock_api: TestClient) -> None:
    summary = run_loop(mock_api, allow_mock=True, log=_quiet)
    assert summary["mock"] is True
    assert summary["rows"] == 3


def test_loop_refuses_a_mock_api_by_default(mock_api: TestClient) -> None:
    # The plan says the e2e test "hits the real API".
    with pytest.raises(E2EError) as error:
        run_loop(mock_api, log=_quiet)
    assert error.value.step == "mode"


def test_missing_endpoint_names_its_step(mock_api: TestClient) -> None:
    client = _broken(mock_api, "/detect", httpx.Response(404, json={"detail": "Not Found"}))
    with pytest.raises(E2EError) as error:
        run_loop(client, allow_mock=True, log=_quiet)
    assert error.value.step == "detect"


def test_non_pdf_export_fails(mock_api: TestClient) -> None:
    html = httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")
    with pytest.raises(E2EError) as error:
        run_loop(_broken(mock_api, "/export", html), allow_mock=True, log=_quiet)
    assert error.value.step == "export"


def test_contract_mismatch_fails(mock_api: TestClient) -> None:
    # A /simulate answer missing required fields must fail the contract check, not pass silently.
    bad = httpx.Response(200, json={"scenario_id": "s1", "state": "burning"})
    with pytest.raises(E2EError, match="SimulateOut") as error:
        run_loop(_broken(mock_api, "/simulate", bad), allow_mock=True, log=_quiet)
    assert error.value.step == "simulate"


def test_unreachable_api_exits_1_with_a_hint(capsys: pytest.CaptureFixture[str]) -> None:
    # Port 9 on localhost: nothing listens there, so the connection is refused at once.
    assert main(["--base-url", "http://127.0.0.1:9", "--timeout", "2"]) == 1
    output = capsys.readouterr().out
    assert "FAIL health" in output
    assert "make dev" in output


def _edited(api: TestClient, path: str, edit) -> httpx.Client:
    """A client that reaches the mock app, but lets `edit` change the JSON returned for `path`."""

    def handler(request: httpx.Request) -> httpx.Response:
        real = api.request(
            request.method,
            request.url.path,
            content=request.content,
            headers={"content-type": "application/json"},
        )
        if not request.url.path.startswith(path):
            return httpx.Response(real.status_code, headers=real.headers, content=real.content)
        return httpx.Response(real.status_code, json=edit(real.json()))

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://e2e")


def test_a_scenario_that_does_not_burn_fails(mock_api: TestClient) -> None:
    # Ranking suppression for a fire that is already out is meaningless.
    client = _edited(mock_api, "/simulate", lambda body: {**body, "state": "extinguished"})
    with pytest.raises(E2EError, match="doesn't burn") as error:
        run_loop(client, allow_mock=True, log=_quiet)
    assert error.value.step == "simulate"


def test_a_no_data_action_above_a_backed_one_fails(mock_api: TestClient) -> None:
    # Contract order: data-backed actions first. Mark only the LAST action as backed.
    def edit(body: dict) -> dict:
        body["actions"][-1]["data_support"] = "direct"
        return body

    with pytest.raises(E2EError, match="no-data action ranks above") as error:
        run_loop(_edited(mock_api, "/suppress", edit), allow_mock=True, log=_quiet)
    assert error.value.step == "suppress"


def test_a_real_api_must_offer_the_scenario_material(mock_api: TestClient) -> None:
    # Only mock mode may fall back to another material; here the "real" API lacks the default one.
    client = _edited(
        mock_api,
        "/openapi.json",
        lambda body: {**body, "info": {**body["info"], "description": ""}},
    )
    with pytest.raises(E2EError, match="isn't offered") as error:
        run_loop(client, log=_quiet)
    assert error.value.step == "meta"
