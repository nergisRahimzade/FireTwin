"""The pipeline's functions as agent tools: one registry, JSON schemas, every call logged.

"Agents think, tools compute." An agent never sees Python objects: it asks for a tool by name with
JSON arguments and gets JSON back. Every call goes through the session's ToolLog, so each number
an agent later writes can be traced to a logged tool result (see grounding.py and critique()).
The same registry serves the deterministic pipeline, tests and any LLM agent framework.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from ml.pipeline import fire_sim, model, stages
from ml.pipeline.detector import detect
from ml.pipeline.types import CriticResult, Evidence, Plan, Scenario, ToolLog, to_plain

log = logging.getLogger(__name__)


@dataclass
class Session:
    """What one scenario's tools share: the inputs, the log, and the stage results so far."""

    scenario: Scenario
    log: ToolLog = field(default_factory=ToolLog)
    evidence: Evidence | None = None
    plans: list[Plan] = field(default_factory=list)
    critic: CriticResult | None = None
    report_paths: dict | None = None
    out_dir: Any = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[Session, dict], Any]


_CHANGES = {
    "o2_pct": {"type": "number", "description": "oxygen %, default: the scenario's"},
    "flow_speed_cm_s": {"type": "number", "description": "airflow cm/s, default: the scenario's"},
}


def _changed(session: Session, args: dict) -> Scenario:
    updates = {k: float(args[k]) for k in _CHANGES if args.get(k) is not None}
    return replace(session.scenario, **updates)


def _nearest(session: Session, args: dict) -> list:
    return model.nearest_tests(_changed(session, args), k=int(args.get("k", 3)))


def _retrieve(session: Session, args: dict) -> list:
    return stages.retrieve(str(args["query"]), k=int(args.get("k", 3)))


def _simulate(session: Session, args: dict) -> dict:
    prob, spread, trust, extrapolated, nearest = model.predict(_changed(session, args))
    return {
        "burn_probability": prob,
        "state": "burning" if prob >= 0.5 else "extinguished",
        "spread_rate_mm_s": spread,
        "trust": trust,
        "extrapolated": extrapolated,
        "nearest_test_ids": [t.test_id for t in nearest],
    }


def _detect(session: Session, args: dict) -> Any:
    return detect(_changed(session, args))


def _simulate_fire(session: Session, args: dict) -> dict:
    actions = [(float(a["time_s"]), str(a["action"])) for a in args.get("actions", [])]
    trace = fire_sim.simulate_fire(
        session.scenario, actions, duration_s=float(args.get("duration_s", 300))
    )
    return fire_sim.summarize(trace)


def _analyze(session: Session, args: dict) -> Any:
    session.evidence = stages.analyze(session.scenario, session.log)
    return session.evidence


def _plan(session: Session, args: dict) -> list:
    if session.evidence is None:
        session.evidence = stages.analyze(session.scenario, session.log)
    session.plans = stages.plan(session.scenario, session.evidence, session.log)
    return [_plan_summary(i, p) for i, p in enumerate(session.plans)]


def _plan_summary(index: int, p: Plan) -> dict:
    return {
        "rank": index + 1,
        "steps": list(p.steps),
        "extinction_probability": p.extinction_probability,
        "crew_risk": p.crew_risk,
        "detection_delay_penalty": p.detection_delay_penalty,
        "score": p.score,
        "data_support": p.data_support,
        "trust": p.trust,
        "explanation": p.explanation,
    }


def _critique(session: Session, args: dict) -> dict:
    if not session.plans:
        _plan(session, {})
    session.critic = stages.critique(session.plans, session.log)
    best = session.critic.recommended
    return {
        "approved": session.critic.approved,
        "recommended": None if best is None else list(best.steps),
        "issues": session.critic.issues,
    }


def _tool_log(session: Session, args: dict) -> list:
    last = int(args.get("last", 20))
    return [
        {"id": e["id"], "tool": e["tool"], "ok": "error" not in e}
        for e in session.log.entries[-last:]
    ]


def _report(session: Session, args: dict) -> dict:
    if session.critic is None:
        _critique(session, {})
    evidence = session.evidence or stages.analyze(session.scenario, session.log)
    rep = stages.report(session.scenario, session.critic.plans, evidence, out_dir=session.out_dir)
    session.report_paths = {"pdf": rep.pdf_path, "csv": rep.csv_path, "json": rep.json_path}
    return {**session.report_paths, "data_gaps": rep.sections["data_gaps"]}


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "nearest_tests",
            "The NASA tests closest to the scenario (optionally with changed O2/airflow).",
            {"type": "object", "properties": {**_CHANGES, "k": {"type": "integer"}}},
            _nearest,
        ),
        Tool(
            "retrieve",
            "Passages from the NASA documents that match a query.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
                "required": ["query"],
            },
            _retrieve,
        ),
        Tool(
            "analyze",
            "Evidence for the scenario: nearest tests, retrieved passages, trust, extrapolation.",
            {"type": "object", "properties": {}},
            _analyze,
        ),
        Tool(
            "simulate",
            "Burn probability, trust and nearest tests for the scenario or changed inputs.",
            {"type": "object", "properties": _CHANGES},
            _simulate,
        ),
        Tool(
            "detect",
            "When and where smoke trips a vent detector (scenario or changed inputs).",
            {"type": "object", "properties": _CHANGES},
            _detect,
        ),
        Tool(
            "simulate_fire",
            "Run the fire over time with timed actions; returns alarm and flame-out times.",
            {
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "time_s": {"type": "number"},
                                "action": {"type": "string", "enum": list(fire_sim.ACTIONS)},
                            },
                            "required": ["time_s", "action"],
                        },
                    },
                    "duration_s": {"type": "number"},
                },
            },
            _simulate_fire,
        ),
        Tool(
            "plan",
            "Score every suppression sequence (cut_power first, up to 3 steps); best first.",
            {"type": "object", "properties": {}},
            _plan,
        ),
        Tool(
            "critique",
            "Rule checks on the plans: traceable numbers, trust, crew risk, data support.",
            {"type": "object", "properties": {}},
            _critique,
        ),
        Tool(
            "get_tool_log",
            "The most recent tool calls (id, tool, ok), to check what has been computed.",
            {"type": "object", "properties": {"last": {"type": "integer"}}},
            _tool_log,
        ),
        Tool(
            "report",
            "Write the PDF/CSV/JSON report of the ranked plans; returns file paths and data gaps.",
            {"type": "object", "properties": {}},
            _report,
        ),
    )
}


def schemas(names: list[str]) -> list[dict]:
    """OpenAI-style function schemas for the named tools (what an LLM is offered)."""
    return [
        {
            "type": "function",
            "function": {
                "name": TOOLS[n].name,
                "description": TOOLS[n].description,
                "parameters": TOOLS[n].parameters,
            },
        }
        for n in names
    ]


def call(session: Session, name: str, args: dict | None = None) -> dict:
    """Run one tool through the session's log. Returns {"call_id", "result"} or {"error"}.

    Never raises for a bad name or bad arguments: an agent gets the error back as data and can
    correct itself. The failure is logged with the tool name and arguments.
    """
    args = args or {}
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"unknown tool {name!r}; available: {sorted(TOOLS)}"}
    # The tool's own entry is written first, so its id stays stable even when the tool logs
    # inner calls of its own (plan() logs one predict and one detect per sequence).
    entry = {"id": len(session.log.entries), "tool": name, "inputs": to_plain(args)}
    session.log.entries.append(entry)
    try:
        entry["output"] = to_plain(tool.run(session, args))
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"
        log.exception("tool %s failed with args=%s", name, args)
        return {"call_id": entry["id"], "error": entry["error"]}
    return {"call_id": entry["id"], "result": entry["output"]}
