"""Pipeline stages (A2): analyze -> plan -> critique -> report, plus run_pipeline.

Each stage is a pure, typed function so it can become an agent tool in Phase B unchanged.
No LLM is used anywhere in this file.
"""

from __future__ import annotations

import csv
import itertools
import json
import logging
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from ml.pipeline import config, model
from ml.pipeline.detector import detect
from ml.pipeline.types import (
    CriticResult,
    Detection,
    Evidence,
    Passage,
    Plan,
    Report,
    Scenario,
    ToolLog,
    to_plain,
)

log = logging.getLogger(__name__)

HONESTY_LINE = "Flame is illustrative; verdicts come from NASA PSI data."
TOL = 1e-6


# ---------- analyze ----------


def retrieve(query: str, k: int = config.RETRIEVE_TOP_K, docs_dir: Path = config.DOCS_DIR):
    """Top-k passages from data/docs/<investigation>/*.txt by keyword overlap (offline).

    The first line of each file holds the source URL (DAT-07). Returns [] when no docs exist.
    """
    words = set(re.findall(r"[a-z0-9]+", query.lower()))
    passages = []
    for path in sorted(docs_dir.glob("*/*.txt")):
        try:
            header, _, body = path.read_text(encoding="utf-8").partition("\n")
        except Exception:
            log.exception("retrieve: cannot read %s (query=%r)", path, query)
            raise
        for para in (p.strip() for p in body.split("\n\n")):
            overlap = len(words & set(re.findall(r"[a-z0-9]+", para.lower())))
            if para and overlap:
                passages.append(
                    Passage(path.stem, path.parent.name, header.strip(), para[:400], float(overlap))
                )
    return sorted(passages, key=lambda p: -p.score)[:k]


def analyze(scenario: Scenario, tool_log: ToolLog | None = None) -> Evidence:
    """Nearest NASA tests (ML-04) plus top-k retrieved passages for the scenario."""
    tl = tool_log or ToolLog()
    nearest = tl.call("nearest_tests", model.nearest_tests, scenario)
    fuel = model.fuel_type_of(scenario.material) or ""
    query = f"{scenario.material} {fuel} oxygen flow flammability extinction suppression"
    passages = tl.call("retrieve", retrieve, query)
    extrapolated = model.is_extrapolated(scenario)
    trust = "weak" if extrapolated else model.trust_level(scenario)
    return Evidence(nearest=nearest, passages=passages, trust=trust, extrapolated=extrapolated)


# ---------- plan ----------


def apply_action(scenario: Scenario, action: str) -> Scenario:
    """How one suppression action changes the model inputs."""
    if action == "fans_off":
        return replace(scenario, flow_speed_cm_s=0.0)
    if action == "co2":
        return replace(scenario, o2_pct=max(scenario.o2_pct - config.CO2_O2_DROP_PCT, 0.0))
    if action in ("cut_power", "water_mist"):
        return scenario  # no input change: procedure step / no PSI data
    raise ValueError(f"apply_action: unknown action {action!r}")


def candidate_sequences() -> list[tuple[str, ...]]:
    """All action sequences up to MAX_PLAN_STEPS; cut_power is always step 1."""
    others = [a for a in config.ACTION_LABELS if a != "cut_power"]
    sequences = [("cut_power",)]
    for n in range(1, config.MAX_PLAN_STEPS):
        sequences += [("cut_power", *combo) for combo in itertools.permutations(others, n)]
    return sequences


def delay_penalty(base: Detection, after: Detection) -> float:
    """0-1: how much later smoke is detected after the plan (1 = never detected)."""
    if not base.detected:
        return 0.0  # it was already undetectable; the plan did not make it worse
    if not after.detected:
        return 1.0
    extra = max(after.time_to_detect_s - base.time_to_detect_s, 0.0)
    return min(extra / config.DETECT_TIMEOUT_S, 1.0)


def plan(scenario: Scenario, evidence: Evidence, tool_log: ToolLog | None = None) -> list[Plan]:
    """Score every action sequence with the physics model and the detector; best first.

    Score = extinction probability - crew_risk * weight - detection-delay penalty * weight.
    Plans with data_support="none" are ranked after all others.
    """
    tl = tool_log or ToolLog()
    base_detection = tl.call("detect", detect, scenario)
    plans = []
    for steps in candidate_sequences():
        try:
            new_inputs = scenario
            for action in steps:
                new_inputs = apply_action(new_inputs, action)
            prob, _, trust, extrapolated, nearest = tl.call("predict", model.predict, new_inputs)
            predict_id = tl.last_id
            after = tl.call("detect", detect, new_inputs)
            detect_id = tl.last_id

            extinction = 1.0 - prob
            safe = 1.0
            for action in steps:
                safe *= 1.0 - config.CREW_RISK[action]
            crew_risk = 1.0 - safe
            penalty = delay_penalty(base_detection, after)
            score = (
                extinction
                - crew_risk * config.CREW_RISK_WEIGHT
                - penalty * config.DETECTION_DELAY_WEIGHT
            )
            modelled = [a for a in steps if a != "cut_power"]
            if not modelled or any(a in config.NO_DATA_ACTIONS for a in modelled):
                support = "none"
            else:
                support = model.data_support(new_inputs)
            notes = []
            if "fans_off" in steps and not after.detected:
                notes.append(after.note)
            if any(a in config.NO_DATA_ACTIONS for a in steps):
                notes.append("no direct NASA data for water mist")
            if extrapolated:
                notes.append("outside tested range: no direct NASA data")
            label = " -> ".join(config.ACTION_LABELS[a] for a in steps)
            plans.append(
                Plan(
                    steps=steps,
                    label=label,
                    new_inputs=new_inputs,
                    extinction_probability=extinction,
                    crew_risk=crew_risk,
                    detection_delay_penalty=penalty,
                    score=score,
                    data_support=support,
                    trust="weak" if extrapolated else trust,
                    extrapolated=extrapolated,
                    sources=nearest,
                    explanation="; ".join(
                        ["cut power: standard procedure, removes ignition source", *notes]
                    ),
                    predict_call_id=predict_id,
                    detect_call_id=detect_id,
                )
            )
        except Exception:
            log.exception("plan: scoring failed for steps=%s scenario=%s", steps, scenario)
            raise
    return sorted(plans, key=lambda p: (p.data_support == "none", -p.score))


# ---------- critique ----------


def critique(plans: list[Plan], tool_log: ToolLog) -> CriticResult:
    """Rule checks on the plans. Rejected plans and data_support="none" plans rank last."""
    entries = {e["id"]: e for e in tool_log.entries}
    issues: list[dict] = []
    rejected: set[tuple[str, ...]] = set()
    checked: list[Plan] = []

    def flag(p: Plan, rule: str, detail: str, reject: bool) -> None:
        issues.append({"plan": p.label, "rule": rule, "detail": detail, "rejects": reject})
        if reject:
            rejected.add(p.steps)

    for p in plans:
        # Rule 1: every number must trace to a logged tool result.
        entry = entries.get(p.predict_call_id)
        if entry is None or entry["tool"] != "predict" or "output" not in entry:
            flag(p, "traceable_numbers", "no logged predict call for this plan", True)
        elif abs((1.0 - entry["output"][0]) - p.extinction_probability) > TOL:
            flag(p, "traceable_numbers", "extinction probability differs from the tool log", True)
        d_entry = entries.get(p.detect_call_id)
        if d_entry is None or d_entry["tool"] != "detect" or "output" not in d_entry:
            flag(p, "traceable_numbers", "no logged detect call for this plan", True)
        expected = (
            p.extinction_probability
            - p.crew_risk * config.CREW_RISK_WEIGHT
            - p.detection_delay_penalty * config.DETECTION_DELAY_WEIGHT
        )
        if abs(expected - p.score) > TOL:
            flag(p, "traceable_numbers", "score does not match its components", True)
        # Rule 2: extrapolated inputs -> low trust.
        if p.extrapolated and p.trust != "weak":
            flag(p, "extrapolation_trust", "extrapolated inputs: trust lowered to weak", False)
            p = replace(p, trust="weak")
        # Rule 3: crew risk under the threshold.
        if p.crew_risk > config.CREW_RISK_MAX:
            flag(p, "crew_risk", f"crew risk {p.crew_risk:.2f} > {config.CREW_RISK_MAX}", True)
        # Rule 4: cut_power must be step 1.
        if not p.steps or p.steps[0] != "cut_power":
            flag(p, "cut_power_first", "cut_power must be the first step", True)
        if p.data_support == "none":
            flag(p, "data_support", "no NASA data supports this plan: ranked last", False)
        checked.append(p)

    ranked = sorted(
        checked, key=lambda p: (p.steps in rejected, p.data_support == "none", -p.score)
    )
    ok = [p for p in ranked if p.steps not in rejected and p.data_support != "none"]
    return CriticResult(
        approved=bool(ok), plans=ranked, recommended=ok[0] if ok else None, issues=issues
    )


# ---------- report ----------


def report(
    scenario: Scenario,
    plans: list[Plan],
    evidence: Evidence,
    out_dir: Path | None = None,
    name: str = "report",
) -> Report:
    """Template-filled report (methods, scenario, results, evidence, data gaps) -> PDF/CSV/JSON."""
    out = Path(out_dir) if out_dir else Path(tempfile.gettempdir()) / "firetwin_reports"
    gaps = []
    if evidence.extrapolated:
        gaps.append("Scenario is outside the tested range: no direct NASA data.")
    if not evidence.passages:
        gaps.append("No report passages retrieved (data/docs is empty or nothing matched).")
    if any(t.is_synthetic for t in evidence.nearest):
        gaps.append("Evidence rows are SYNTHETIC placeholders, not NASA tests.")
    if any(p.data_support == "none" for p in plans):
        gaps.append("Water mist and cut power have no PSI test data (data_support = none).")
    results = [
        {
            "rank": i + 1,
            "plan": p.label,
            "extinction_probability": round(p.extinction_probability, 3),
            "crew_risk": round(p.crew_risk, 3),
            "detection_delay_penalty": round(p.detection_delay_penalty, 3),
            "score": round(p.score, 3),
            "data_support": p.data_support,
            "trust": p.trust,
            "notes": p.explanation,
        }
        for i, p in enumerate(plans)
    ]
    table = [
        {**to_plain(t), "synthetic": "SYNTHETIC" if t.is_synthetic else ""}
        for t in evidence.nearest
    ]
    sections = {
        "title": "FireTwin suppression report",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methods": (
            "Burn probability comes from a physics-shaped logistic regression on O2, "
            "ln(flow + u0), ln(flow + u0)^2, pressure and fuel type. Each plan changes the "
            "model inputs, is re-predicted, and is scored as extinction probability minus "
            f"{config.CREW_RISK_WEIGHT} x crew risk minus {config.DETECTION_DELAY_WEIGHT} x "
            "detection-delay penalty. Crew-risk values are team placeholders. " + HONESTY_LINE
        ),
        "scenario": to_plain(scenario),
        "trust": evidence.trust,
        "results": results,
        "evidence_table": table,
        "passages": to_plain(evidence.passages),
        "data_gaps": gaps,
    }
    try:
        out.mkdir(parents=True, exist_ok=True)
        json_path, csv_path, pdf_path = (out / f"{name}.{ext}" for ext in ("json", "csv", "pdf"))
        json_path.write_text(json.dumps(sections, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0]) if results else ["rank"])
            writer.writeheader()
            writer.writerows(results)
        _write_pdf(pdf_path, sections)
    except Exception:
        log.exception("report: export failed (out_dir=%s, name=%s)", out, name)
        raise
    return Report(sections, str(pdf_path), str(csv_path), str(json_path))


def _write_pdf(path: Path, s: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    body, small = styles["BodyText"], styles["BodyText"].clone("small", fontSize=7, leading=9)

    def grid(rows: list[dict], cols: list[str]) -> Table:
        data = [cols] + [[Paragraph(str(r.get(c, "")), small) for c in cols] for r in rows]
        t = Table(data, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return t

    sc = s["scenario"]
    flow = [
        Paragraph(s["title"], styles["Title"]),
        Paragraph(f"Generated {s['generated_utc']}", body),
        Paragraph("Methods", styles["Heading2"]),
        Paragraph(s["methods"], body),
        Paragraph("Scenario", styles["Heading2"]),
        Paragraph(
            f"Material {sc['material']}, O2 {sc['o2_pct']} %, pressure {sc['pressure_kpa']} kPa, "
            f"flow {sc['flow_speed_cm_s']} cm/s along {sc['flow_dir']}. Trust: {s['trust']}.",
            body,
        ),
        Paragraph("Results", styles["Heading2"]),
        grid(s["results"], list(s["results"][0]) if s["results"] else ["rank"]),
        Spacer(1, 8),
        Paragraph("Evidence table (nearest tests)", styles["Heading2"]),
        grid(
            s["evidence_table"],
            ["test_id", "investigation", "fuel_type", "o2_pct", "pressure_kpa", "flow_cm_s"]
            + ["outcome", "source_url", "synthetic"],
        ),
        Paragraph("Data gaps", styles["Heading2"]),
        *[Paragraph(f"- {g}", body) for g in (s["data_gaps"] or ["None found."])],
        Spacer(1, 8),
        Paragraph(HONESTY_LINE, body),
    ]
    SimpleDocTemplate(str(path), pagesize=landscape(A4), title=s["title"]).build(flow)


# ---------- run_pipeline ----------


@dataclass(frozen=True)
class PipelineResult:
    scenario: Scenario
    simulation: dict  # burn_probability, state, trust, extrapolated
    detection: Detection
    evidence: Evidence
    critic: CriticResult
    applied: dict | None  # result of applying the recommended plan
    results_rows: list[dict]  # step-by-step history, same idea as /results
    report: Report
    tool_log: list[dict]


def _simulate(scenario: Scenario, tl: ToolLog) -> dict:
    prob, spread, trust, extrapolated, nearest = tl.call("predict", model.predict, scenario)
    return {
        "burn_probability": prob,
        "state": "burning" if prob >= config.BURN_THRESHOLD else "extinguished",
        "spread_rate_mm_s": spread,
        "trust": trust,
        "extrapolated": extrapolated,
        "sources": [t.test_id for t in nearest],
    }


def run_pipeline(scenario: Scenario, out_dir: Path | None = None) -> PipelineResult:
    """simulate -> detect -> analyze -> plan -> critique -> apply -> results -> export."""
    tl = ToolLog()
    try:
        sim = _simulate(scenario, tl)
        detection = tl.call("detect", detect, scenario)
        evidence = analyze(scenario, tl)
        plans = plan(scenario, evidence, tl)
        critic = critique(plans, tl)
        rows = [{"step": "simulate", "inputs": to_plain(scenario), "action": None, **sim}]
        rows.append(
            {
                "step": "detect",
                "detected": detection.detected,
                "detection_s": detection.time_to_detect_s,
                "note": detection.note,
            }
        )
        applied = None
        if critic.recommended is not None:
            best = critic.recommended
            applied = _simulate(best.new_inputs, tl)
            rows.append(
                {"step": "apply", "inputs": to_plain(best.new_inputs), "action": best.label}
                | applied
            )
        rep = report(scenario, critic.plans, evidence, out_dir=out_dir)
        tl.entries.append(
            {"id": len(tl.entries), "tool": "report", "inputs": [], "output": rep.pdf_path}
        )
        return PipelineResult(
            scenario, sim, detection, evidence, critic, applied, rows, rep, tl.entries
        )
    except Exception:
        log.exception("run_pipeline failed for scenario=%s", scenario)
        raise
