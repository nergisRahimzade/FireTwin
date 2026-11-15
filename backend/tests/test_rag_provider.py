"""ML-06: which LLM provider rag.py calls (Gemini preferred, OpenAI second, none = offline)."""

import sys
import types

import pytest

from app.services import rag


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_no_key_means_no_provider() -> None:
    assert rag.llm_provider() is None
    assert rag.llm_available() is False


def test_gemini_key_selects_gemini_with_its_openai_compatible_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    provider = rag.llm_provider()
    assert provider["name"] == "gemini"
    assert provider["model"] == "gemini-3.8-flash"
    assert provider["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_openai_key_alone_selects_openai(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    provider = rag.llm_provider()
    assert (provider["name"], provider["base_url"]) == ("openai", None)


def test_gemini_wins_when_both_keys_are_set(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert rag.llm_provider()["name"] == "gemini"


def test_model_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash-preview")
    assert rag.llm_provider()["model"] == "gemini-3-flash-preview"


def test_blank_key_counts_as_missing(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert rag.llm_provider() is None


def test_chat_sends_key_base_url_and_model_to_the_sdk(monkeypatch) -> None:
    calls = {}

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client"] = kwargs

            def create(**kw):
                calls["create"] = kw
                message = types.SimpleNamespace(content=" hi ")
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeClient))
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert rag._chat("system text", "user text") == "hi"
    assert calls["client"]["api_key"] == "g-key"
    assert calls["client"]["base_url"].endswith("/v1beta/openai/")
    assert calls["create"]["model"] == "gemini-3.8-flash"
    assert [m["role"] for m in calls["create"]["messages"]] == ["system", "user"]


def test_chat_without_any_key_raises_a_clear_error() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        rag._chat("s", "u")
