"""One LLM client for the whole project: explainer, chat and the agents (Phase B).

Gemini (preferred) or OpenAI, chosen by which key is set, both through the OpenAI SDK: Gemini is
reached through its OpenAI-compatible endpoint, so the same messages and the same tool-calling
format work for both. Every call raises on failure; callers decide how to fall back, so the demo
never depends on the network. Check a key with `python -m ml.agents.llm`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

log = logging.getLogger(__name__)

PROVIDERS = (
    {
        "name": "gemini",
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.8-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    {
        "name": "openai",
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "base_url": None,  # the SDK's default
    },
)
TIMEOUT_S = 20.0


def provider() -> dict | None:
    """{name, api_key, model, base_url} of the first provider whose key is set, else None."""
    for p in PROVIDERS:
        key = os.getenv(p["key_env"], "").strip()
        if key:
            model = os.getenv(p["model_env"], "").strip() or p["default_model"]
            return {"name": p["name"], "api_key": key, "model": model, "base_url": p["base_url"]}
    return None


def available() -> bool:
    return provider() is not None


def complete(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """One chat completion. Returns {"content": str, "tool_calls": [{id, name, arguments}]}.

    `tools` are OpenAI-style function schemas (see ml.pipeline.tools.schemas()). Arguments come
    back already parsed from JSON. Raises RuntimeError with no key, and any SDK error as is.
    """
    from openai import OpenAI  # imported here so the offline path never needs the SDK

    p = provider()
    if p is None:
        raise RuntimeError("llm.complete: no GEMINI_API_KEY or OPENAI_API_KEY is set")
    client = OpenAI(api_key=p["api_key"], base_url=p["base_url"], timeout=TIMEOUT_S)
    kwargs: dict[str, Any] = {"model": p["model"], "messages": messages}
    if tools:
        kwargs["tools"] = tools
    try:
        message = client.chat.completions.create(**kwargs).choices[0].message
    except Exception:
        log.exception("llm.complete failed (provider=%s, model=%s)", p["name"], p["model"])
        raise
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            log.warning(
                "llm.complete: tool %s sent arguments that are not JSON", call.function.name
            )
            arguments = {}
        calls.append({"id": call.id, "name": call.function.name, "arguments": arguments})
    return {"content": (message.content or "").strip(), "tool_calls": calls}


def chat(system: str, user: str) -> str:
    """Plain question -> text, for the explainer and the chat."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return complete(messages)["content"]


def main() -> int:
    """Check the configured key with one tiny call and say clearly what is wrong if it fails."""
    p = provider()
    if p is None:
        print("No GEMINI_API_KEY or OPENAI_API_KEY in the environment (load .env first).")
        return 1
    try:
        reply = chat("Reply with the single word: ok", "ping")
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic: show any failure
        print(f"{p['name']} / {p['model']}: FAILED -> {type(exc).__name__}: {str(exc)[:300]}")
        return 1
    print(f"{p['name']} / {p['model']}: OK -> {reply!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
