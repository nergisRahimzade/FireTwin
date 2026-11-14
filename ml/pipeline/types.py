"""Typed inputs and outputs shared by every pipeline stage (and, in Phase B, by agent tools)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Scenario:
    """Same fields as ScenarioIn in the API contract."""

    material: str
    o2_pct: float
    flow_speed_cm_s: float
    pressure_kpa: float = 101.3
    flow_dir: tuple[float, float, float] = (1.0, 0.0, 0.0)
    module: str = "iss_lab"


@dataclass(frozen=True)
class TestRef:
    __test__ = False  # tell pytest this is not a test class

    test_id: str
    investigation: str
    fuel_type: str
    o2_pct: float | None
    pressure_kpa: float | None
    flow_cm_s: float | None
    outcome: str
    source_url: str
    is_synthetic: bool = False


@dataclass(frozen=True)
class Passage:
    title: str
    investigation: str
    source_url: str
    snippet: str
    score: float


@dataclass(frozen=True)
class Evidence:
    nearest: list[TestRef]
    passages: list[Passage]
    trust: str
    extrapolated: bool


@dataclass(frozen=True)
class Detection:
    detected: bool
    detector_id: str | None
    time_to_detect_s: float | None
    detectors: list[dict]
    note: str


@dataclass(frozen=True)
class Plan:
    steps: tuple[str, ...]
    label: str
    new_inputs: Scenario
    extinction_probability: float
    crew_risk: float
    detection_delay_penalty: float
    score: float
    data_support: str  # direct | indirect | none
    trust: str  # strong | medium | weak
    extrapolated: bool
    sources: list[TestRef]
    explanation: str
    predict_call_id: int | None = None  # tool_log entries the numbers came from
    detect_call_id: int | None = None


@dataclass(frozen=True)
class CriticResult:
    approved: bool
    plans: list[Plan]  # re-ranked: rejected and data_support="none" plans go last
    recommended: Plan | None
    issues: list[dict]  # {plan, rule, detail}


@dataclass(frozen=True)
class Report:
    sections: dict[str, Any]
    pdf_path: str
    csv_path: str
    json_path: str


@dataclass
class ToolLog:
    """Records every tool call (name, inputs, output) so numbers can be traced back."""

    entries: list[dict] = field(default_factory=list)

    def call(self, tool: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        entry = {"id": len(self.entries), "tool": tool, "inputs": to_plain([args, kwargs])}
        self.entries.append(entry)
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        entry["output"] = to_plain(result)
        return result

    @property
    def last_id(self) -> int:
        return len(self.entries) - 1


def to_plain(obj: Any) -> Any:
    """Dataclasses, tuples and lists -> plain JSON-ready dicts and lists."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_plain(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]
    return obj
