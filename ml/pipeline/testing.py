"""Shared pytest fixtures: logic tests run on a fixed synthetic table, not the real artifacts.

The committed data/processed/tests.parquet and ml/artifacts/ change every time the NASA data is
rebuilt or the model retrained. Tests of the LOGIC (ranking, trust, detection, endpoints) must
not change with them, so each test points the ML layer at a seed table and a model trained on
it, both written to a temporary folder. Tests that check the real committed artifacts ask for
the `real_artifacts` fixture instead. Import these fixtures from a conftest.py to use them.
"""

from __future__ import annotations

import pytest

from data.pipeline import build_table
from ml import train
from ml.pipeline import config, model

_PATH_NAMES = (
    "TESTS_PARQUET",
    "ARTIFACTS_DIR",
    "MODEL_PATH",
    "RANGES_PATH",
    "METRICS_PATH",
    "PHYSICS_PARAMS_PATH",
)
_REAL_PATHS = {name: getattr(config, name) for name in _PATH_NAMES}


def _clear_caches() -> None:
    for loader in (
        model.load_table,
        model.load_model,
        model.load_ranges,
        model.trust_thresholds,
        model.load_metrics,
    ):
        # A test may have replaced a loader with a plain function, which has no cache.
        clear = getattr(loader, "cache_clear", None)
        if clear is not None:
            clear()


def _point_at(paths: dict) -> None:
    for name, value in paths.items():
        setattr(config, name, value)
    _clear_caches()


@pytest.fixture(scope="session")
def seed_paths(tmp_path_factory) -> dict:
    """Build the synthetic seed table and train a model on it, once per test session."""
    folder = tmp_path_factory.mktemp("seed")
    table_path = folder / "tests.parquet"
    artifacts = folder / "artifacts"
    build_table.write_table(build_table.build_seed(), table_path)
    train.train(table_path, artifacts)
    return {
        "TESTS_PARQUET": table_path,
        "ARTIFACTS_DIR": artifacts,
        "MODEL_PATH": artifacts / config.MODEL_PATH.name,
        "RANGES_PATH": artifacts / config.RANGES_PATH.name,
        "METRICS_PATH": artifacts / config.METRICS_PATH.name,
        "PHYSICS_PARAMS_PATH": artifacts / config.PHYSICS_PARAMS_PATH.name,
    }


@pytest.fixture(autouse=True)
def seed_artifacts(seed_paths):
    """Every test sees the seed table and seed model unless it asks for `real_artifacts`."""
    _point_at(seed_paths)
    yield
    _point_at(_REAL_PATHS)


@pytest.fixture
def real_artifacts(seed_artifacts):
    """Switch one test back to the committed table and model."""
    _point_at(_REAL_PATHS)
    yield
    _clear_caches()
