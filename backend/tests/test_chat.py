"""BE-10: real chat delegation, scenario snapshots, offline RAG and mock isolation."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ChatOut, ScenarioIn
from app.services import rag, store

INPUTS = ScenarioIn(material="Synthetic chat fixture", o2_pct=21, flow_speed_cm_s=10)
ANSWER = ChatOut(
    answer="Synthetic chat test response.",
    citations=[
        {
            "title": "Synthetic fixture",
            "investigation": "Synthetic FLEX",
            "source_url": "https://example.com/synthetic-chat",
            "snippet": "Synthetic source text.",
            "is_synthetic": True,
        }
    ],
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    store.clear()
    with TestClient(create_app()) as client:
        yield client
    store.clear()


@pytest.fixture
def docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "Synthetic-FLEX"
    folder.mkdir()
    (folder / "abstract.txt").write_text(
        "https://example.com/synthetic-chat\n"
        "Synthetic fixture: FLEX studied suppression with carbon dioxide.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rag, "DOCS_DIR", tmp_path)


@pytest.mark.parametrize("extra", [{}, {"scenario_id": None}])
def test_general_chat_passes_no_scenario(client: TestClient, monkeypatch, extra) -> None:
    seen = []

    def answer(message, scenario):
        seen.append((message, scenario))
        return ANSWER

    monkeypatch.setattr(rag, "answer", answer)
    message = "  Why did fans off work? \u03bb  "
    response = client.post("/chat", json={"message": message, **extra})
    assert response.status_code == 200
    assert seen == [(message, None)]
    assert response.json() == ANSWER.model_dump(mode="json")


def test_chat_passes_current_inputs_and_ordered_history(client: TestClient, monkeypatch) -> None:
    scenario_id = store.create(INPUTS)
    store.append(scenario_id, "simulate", probability=0.8, sources=["synthetic-chat-001"])
    changed = INPUTS.model_copy(update={"flow_speed_cm_s": 0})
    store.append(scenario_id, "apply", inputs=changed, probability=0.2, action="fans_off")
    store.set_inputs(scenario_id, changed)
    seen = []

    def answer(message, scenario):
        seen.append(scenario)
        return ANSWER

    monkeypatch.setattr(rag, "answer", answer)
    response = client.post("/chat", json={"message": "Why?", "scenario_id": scenario_id})
    assert response.status_code == 200
    assert seen == [
        {
            "scenario_id": scenario_id,
            "inputs": changed.model_dump(mode="json"),
            "history": store.history(scenario_id),
        }
    ]
    assert [row["inputs"]["flow_speed_cm_s"] for row in seen[0]["history"]] == [10, 0]


def test_chat_accepts_existing_scenario_without_history(client: TestClient, monkeypatch) -> None:
    scenario_id = store.create(INPUTS)

    def answer(message, scenario):
        assert scenario["scenario_id"] == scenario_id
        assert scenario["history"] == []
        return ANSWER

    monkeypatch.setattr(rag, "answer", answer)
    assert (
        client.post("/chat", json={"message": "Why?", "scenario_id": scenario_id}).status_code
        == 200
    )


@pytest.mark.parametrize("scenario_id", ["unknown", ""])
def test_unknown_scenario_is_404_before_calling_rag(
    client: TestClient, monkeypatch, scenario_id
) -> None:
    def answer(*args):
        pytest.fail("RAG must not receive an unknown scenario")

    monkeypatch.setattr(rag, "answer", answer)
    response = client.post("/chat", json={"message": "Why?", "scenario_id": scenario_id})
    assert response.status_code == 404
    assert "server restart" in response.json()["detail"]


def test_chat_context_is_isolated_from_the_store(client: TestClient, monkeypatch) -> None:
    scenario_id = store.create(INPUTS)
    store.append(scenario_id, "simulate", sources=["synthetic-chat-001"])
    before = store.get(scenario_id)
    before["inputs"] = before["inputs"].model_copy(deep=True)

    def answer(message, scenario):
        scenario["inputs"]["o2_pct"] = 99
        scenario["history"][0]["sources"].append("synthetic-mutation")
        scenario["history"].clear()
        return ANSWER

    monkeypatch.setattr(rag, "answer", answer)
    response = client.post("/chat", json={"message": "Why?", "scenario_id": scenario_id})
    assert response.status_code == 200
    assert store.get(scenario_id) == before


def test_chat_context_does_not_include_another_scenario(client: TestClient, monkeypatch) -> None:
    first = store.create(INPUTS)
    second = store.create(INPUTS.model_copy(update={"material": "Other synthetic scenario"}))
    store.append(second, "simulate", sources=["other-synthetic-source"])

    def answer(message, scenario):
        assert scenario["scenario_id"] == first
        assert scenario["history"] == []
        assert second not in json.dumps(scenario)
        assert "other-synthetic-source" not in json.dumps(scenario)
        return ANSWER

    monkeypatch.setattr(rag, "answer", answer)
    assert client.post("/chat", json={"message": "Why?", "scenario_id": first}).status_code == 200


@pytest.mark.parametrize(
    "body", [{}, {"message": None}, {"message": 123}, {"message": "Why?", "scenario_id": 123}]
)
def test_chat_uses_existing_request_validation(client: TestClient, monkeypatch, body) -> None:
    def answer(*args):
        pytest.fail("Invalid requests must not reach RAG")

    monkeypatch.setattr(rag, "answer", answer)
    assert client.post("/chat", json=body).status_code == 422


def test_empty_question_uses_rag_no_evidence_response(client: TestClient) -> None:
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 200
    assert response.json() == {"answer": rag.NOTHING_RELEVANT, "citations": []}


def test_offline_chat_returns_the_retrieved_source(client: TestClient, docs, monkeypatch) -> None:
    def no_network(*args):
        pytest.fail("The no-key path must not call the LLM")

    monkeypatch.setattr(rag, "_chat", no_network)
    response = client.post("/chat", json={"message": "carbon dioxide suppression?"})
    assert response.status_code == 200
    result = ChatOut.model_validate(response.json())
    assert "Synthetic fixture" in result.answer
    assert result.citations[0]["source_url"] == "https://example.com/synthetic-chat"


def test_irrelevant_question_returns_no_citations(client: TestClient, docs) -> None:
    response = client.post("/chat", json={"message": "pizza toppings?"})
    assert response.status_code == 200
    assert response.json() == {"answer": rag.NOTHING_RELEVANT, "citations": []}


def test_real_rag_serializes_scenario_into_llm_context(
    client: TestClient, docs, monkeypatch
) -> None:
    scenario_id = store.create(INPUTS)
    store.append(scenario_id, "simulate", state="burning", probability=0.8)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key-not-real")
    payloads = []

    def fake_chat(system, user):
        payloads.append(json.loads(user))
        return "Synthetic fixture: FLEX studied suppression [1]."

    monkeypatch.setattr(rag, "_chat", fake_chat)
    response = client.post("/chat", json={"message": "suppression?", "scenario_id": scenario_id})
    assert response.status_code == 200
    assert payloads[0]["scenario"] == {
        "scenario_id": scenario_id,
        "inputs": INPUTS.model_dump(mode="json"),
        "history": json.loads(json.dumps(store.history(scenario_id))),
    }
    assert payloads[0]["passages"][0]["source_url"] == "https://example.com/synthetic-chat"


def test_llm_failure_keeps_the_service_offline_fallback(
    client: TestClient, docs, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key-not-real")

    def failed_llm(*args):
        raise RuntimeError("synthetic connection failure")

    monkeypatch.setattr(rag, "_chat", failed_llm)
    response = client.post("/chat", json={"message": "suppression?"})
    assert response.status_code == 200
    assert "Synthetic fixture" in response.json()["answer"]
    assert response.json()["citations"]


def test_unexpected_service_failure_returns_generic_500(client: TestClient, monkeypatch) -> None:
    def broken_service(*args):
        raise RuntimeError("synthetic internal diagnostic, must not reach client")

    monkeypatch.setattr(rag, "answer", broken_service)
    response = client.post("/chat", json={"message": "suppression?"})
    assert response.status_code == 500
    assert response.json() == {"detail": "chat failed; see server log"}


def test_chat_openapi_uses_shared_contract(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/chat"]["post"]
    body = operation["requestBody"]["content"]["application/json"]["schema"]
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/ChatIn"}
    assert response == {"$ref": "#/components/schemas/ChatOut"}
    assert {"404", "422", "500"} <= operation["responses"].keys()


def test_mock_chat_does_not_call_real_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    def answer(*args):
        pytest.fail("Mock mode must keep the fixed chat response")

    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setattr(rag, "answer", answer)
    with TestClient(create_app()) as client:
        response = client.post("/chat", json={"message": "Why?", "scenario_id": "unknown"})
    assert response.status_code == 200
    assert "synthetic" in response.json()["answer"].lower()
