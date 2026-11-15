"""Multi-agent orchestrator (Phase B): Analyst -> Strategist -> Critic (-> retry) -> Report Writer.

Plain Python, no framework. Each agent is an LLM with a role and a fixed set of tools from
ml/pipeline/tools.py; it may only reason and choose tools ("agents think, tools compute"). The
approval decision is the critique TOOL's result, never the LLM's opinion, and the writer's summary
is rejected if it states anything not in the tool results (grounding.py). With no API key, or on
any failure, the deterministic pipeline's answer is returned instead: the demo never crashes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from ml.agents import llm
from ml.pipeline import grounding, tools
from ml.pipeline.types import Scenario

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_RETRIES = 2


@dataclass(frozen=True)
class Agent:
    name: str
    role: str
    tools: tuple[str, ...]


ANALYST = Agent(
    "Experiment Analyst",
    "Explain how the nearest NASA tests and passages relate to the scenario, from tool results.",
    ("analyze", "nearest_tests", "retrieve"),
)
STRATEGIST = Agent(
    "Suppression Strategist",
    "Propose suppression plans and explain their trade-offs (extinction, crew risk, detection). "
    "Call plan; test variants with simulate, detect or simulate_fire. Never invent numbers.",
    ("plan", "simulate", "detect", "simulate_fire"),
)
CRITIC = Agent(
    "Safety & Evidence Critic",
    "Call critique and get_tool_log, then state APPROVE or REJECT with the reasons the tool gave.",
    ("critique", "get_tool_log"),
)
WRITER = Agent(
    "Report Writer",
    "Call report, then write a short summary and discussion using only numbers from tool results.",
    ("report",),
)


@dataclass
class AgentRun:
    mode: str  # "agents" or "fallback"
    recommended: list[str] | None
    approved: bool
    summary: str
    report: dict | None
    agent_trace: list[dict] = field(default_factory=list)
    tool_log: list[dict] = field(default_factory=list)


def run_agent(agent: Agent, session: tools.Session, task: str, trace: list[dict]) -> str:
    """Let one agent call its tools until it answers in text. Every step goes into `trace`."""
    messages = [
        {"role": "system", "content": f"You are the {agent.name} of FireTwin. {agent.role}"},
        {"role": "user", "content": task},
    ]
    specs = tools.schemas(list(agent.tools))
    for _ in range(MAX_TOOL_ROUNDS):
        reply = llm.complete(messages, tools=specs)
        if not reply["tool_calls"]:
            trace.append({"agent": agent.name, "action": "answer", "reasoning": reply["content"]})
            return reply["content"]
        messages.append(
            {
                "role": "assistant",
                "content": reply["content"] or None,
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                    }
                    for c in reply["tool_calls"]
                ],
            }
        )
        for c in reply["tool_calls"]:
            # An agent may only use its own tools.
            out = (
                tools.call(session, c["name"], c["arguments"])
                if c["name"] in agent.tools
                else {"error": f"{agent.name} may not use {c['name']}"}
            )
            trace.append(
                {
                    "agent": agent.name,
                    "action": "tool",
                    "tool": c["name"],
                    "arguments": c["arguments"],
                    "call_id": out.get("call_id"),
                    "error": out.get("error"),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": c["id"],
                    "content": json.dumps(out, default=str)[:6000],
                }
            )
    raise RuntimeError(f"{agent.name} did not finish within {MAX_TOOL_ROUNDS} tool rounds")


def _fallback(scenario: Scenario, reason: str, out_dir=None) -> AgentRun:
    """The deterministic pipeline through the same tools, with no LLM."""
    session = tools.Session(scenario, out_dir=out_dir)
    for name in ("analyze", "plan", "critique", "report"):
        tools.call(session, name)
    best = session.critic.recommended if session.critic else None
    steps = list(best.steps) if best else None
    return AgentRun(
        mode="fallback",
        recommended=steps,
        approved=bool(session.critic and session.critic.approved),
        summary=f"Deterministic pipeline result ({reason}). Recommended: "
        f"{' -> '.join(steps) if steps else 'none'}.",
        report=session.report_paths,
        agent_trace=[{"agent": "orchestrator", "action": "fallback", "reasoning": reason}],
        tool_log=session.log.entries,
    )


def run_agents(scenario: Scenario, out_dir=None) -> AgentRun:
    """Analyst -> Strategist -> Critic (Strategist again if rejected, max 2) -> Report Writer."""
    if not llm.available():
        return _fallback(scenario, "no LLM key set", out_dir)
    session, trace = tools.Session(scenario, out_dir=out_dir), []
    try:
        brief = json.dumps({"scenario": scenario.__dict__})
        findings = run_agent(ANALYST, session, f"Scenario: {brief}", trace)
        feedback = ""
        for _attempt in range(MAX_RETRIES + 1):
            run_agent(STRATEGIST, session, f"{brief}\nAnalyst: {findings}\n{feedback}", trace)
            run_agent(CRITIC, session, "Review the strategist's plans.", trace)
            if session.critic is None:
                tools.call(session, "critique")  # the decision always comes from the tool
            if session.critic.approved:
                break
            feedback = f"The critic rejected the plans: {session.critic.issues}"
        summary = run_agent(WRITER, session, "Write the report summary.", trace)
        problems = grounding.check(summary, session.log.entries)
        if problems:
            trace.append(
                {"agent": "orchestrator", "action": "summary rejected", "reasoning": problems}
            )
            summary = "Summary withheld: it stated facts not found in the tool results."
        if session.report_paths is None:
            tools.call(session, "report")
        best = session.critic.recommended
        return AgentRun(
            mode="agents",
            recommended=list(best.steps) if best else None,
            approved=session.critic.approved,
            summary=summary,
            report=session.report_paths,
            agent_trace=trace,
            tool_log=session.log.entries,
        )
    except Exception as exc:
        log.exception("run_agents failed for scenario=%s; using the pipeline", scenario)
        result = _fallback(scenario, f"agents failed: {type(exc).__name__}", out_dir)
        result.agent_trace = trace + result.agent_trace
        return result
