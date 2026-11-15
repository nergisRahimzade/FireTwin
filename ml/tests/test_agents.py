"""Multi-agent orchestrator with a scripted fake LLM: no network, fully deterministic."""

import pytest

from ml.agents import llm, team
from ml.pipeline.types import Scenario

BASE = Scenario(material="cable insulation", o2_pct=21.0, flow_speed_cm_s=10.0)


def _script(replies):
    """A fake llm.complete that returns the given replies in order."""
    it = iter(replies)

    def fake(messages, tools=None):
        return next(it)

    return fake


def _tool(name, args=None, cid="c1"):
    return {"content": "", "tool_calls": [{"id": cid, "name": name, "arguments": args or {}}]}


def _text(text):
    return {"content": text, "tool_calls": []}


def test_without_a_key_the_pipeline_answers(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    run = team.run_agents(BASE, out_dir=tmp_path)
    assert run.mode == "fallback" and run.approved
    assert run.recommended[0] == "cut_power"
    assert run.report["pdf"].endswith(".pdf")


def test_full_agent_loop_uses_tools_and_the_critique_tool_decides(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(
        llm,
        "complete",
        _script(
            [
                _tool("analyze"),
                _text("The nearest tests are close to the scenario."),
                _tool("plan"),
                _text("Fans off removes the airflow that feeds the flame."),
                _tool("critique"),
                _text("APPROVE"),
                _tool("report"),
                _text("The recommended plan starts with cutting power."),
            ]
        ),
    )
    run = team.run_agents(BASE, out_dir=tmp_path)
    assert run.mode == "agents" and run.approved
    assert run.recommended[0] == "cut_power"
    agents = [s["agent"] for s in run.agent_trace]
    assert agents[0] == "Experiment Analyst" and agents[-1] == "Report Writer"
    assert [s["tool"] for s in run.agent_trace if s["action"] == "tool"] == [
        "analyze",
        "plan",
        "critique",
        "report",
    ]


def test_an_ungrounded_summary_is_withheld(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(
        llm,
        "complete",
        _script(
            [
                _text("ok"),
                _tool("plan"),
                _text("ok"),
                _tool("critique"),
                _text("APPROVE"),
                _tool("report"),
                _text("Extinction is guaranteed at 99.9 % within 3.7 seconds."),
            ]
        ),
    )
    run = team.run_agents(BASE, out_dir=tmp_path)
    assert run.summary.startswith("Summary withheld")
    assert any(s["action"] == "summary rejected" for s in run.agent_trace)


def test_an_agent_cannot_use_another_agents_tools(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(llm, "available", lambda: True)
    replies = [_tool("report"), _text("done")] + [_text("ok")] * 10
    monkeypatch.setattr(llm, "complete", _script(replies))
    run = team.run_agents(BASE, out_dir=tmp_path)
    first = run.agent_trace[0]
    assert first["agent"] == "Experiment Analyst" and "may not use report" in first["error"]


def test_an_llm_failure_falls_back_to_the_pipeline(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(llm, "available", lambda: True)

    def boom(messages, tools=None):
        raise ConnectionError("network down")

    monkeypatch.setattr(llm, "complete", boom)
    run = team.run_agents(BASE, out_dir=tmp_path)
    assert run.mode == "fallback" and run.recommended is not None
    assert "agents failed" in run.agent_trace[-1]["reasoning"]


@pytest.mark.parametrize("agent", [team.ANALYST, team.STRATEGIST, team.CRITIC, team.WRITER])
def test_each_agent_only_lists_registered_tools(agent) -> None:
    from ml.pipeline import tools

    assert set(agent.tools) <= set(tools.TOOLS)
