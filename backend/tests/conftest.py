"""Shared backend test setup: tests never see a real LLM key from the developer's shell."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_llm_keys(monkeypatch):
    # Tests that need a key set a fake one themselves; a real one must never reach a test.
    # OPENAI_API_KEY too (BE-12): without it, a key in the developer's shell made real API calls.
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
