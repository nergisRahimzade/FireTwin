"""OPS-05: the demo runs from a fresh clone with no training and no network except the LLM.

Guards the prebuilt artifacts: each must be committed to Git (not just present on one laptop),
non-empty, and loadable, and a real prediction must work with no API keys (offline fallback).
"""

import subprocess
from pathlib import Path

import pytest

from app.schemas import ScenarioIn
from app.services import predictor
from ml.pipeline import model

ROOT = Path(__file__).resolve().parents[1]

# Everything real mode reads at runtime. Rebuild with `make data` / `make train`, then commit.
DEMO_ARTIFACTS = [
    "data/processed/tests.parquet",
    "ml/artifacts/model.joblib",
    "ml/artifacts/feature_ranges.json",
    "ml/artifacts/metrics.json",
    "ml/artifacts/physics_params.json",
]


@pytest.mark.parametrize("path", DEMO_ARTIFACTS)
def test_demo_artifact_is_committed(path: str) -> None:
    # `git ls-files --error-unmatch` fails if the file isn't tracked: a local-only file won't
    # exist on the demo machine's fresh clone.
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, f"{path} is not committed to Git"


@pytest.mark.parametrize("path", DEMO_ARTIFACTS)
def test_demo_artifact_is_not_empty(path: str) -> None:
    assert (ROOT / path).stat().st_size > 0, f"{path} is empty"


def test_demo_artifacts_load() -> None:
    assert len(model.load_table()) > 0
    assert model.load_model()
    assert "overall" in model.load_ranges()


def test_demo_prediction_works_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    # No LLM keys: the demo must still predict (the explanation uses the offline template).
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    material = sorted(model.load_table()["material"].dropna())[0]
    probability = predictor.predict(ScenarioIn(material=material, o2_pct=21, flow_speed_cm_s=10))[0]
    assert 0.0 <= probability <= 1.0
