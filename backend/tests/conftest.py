"""Shared backend test setup: tests never see a real LLM key from the developer's shell."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_llm_keys(monkeypatch):
    # Tests that need a key set a fake one themselves; a real one must never reach a test.
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)


from ml.pipeline.testing import real_artifacts, seed_artifacts, seed_paths  # noqa: E402, F401
