"""OPS-01: every layer is importable under the configured pytest importlib mode."""

from importlib import import_module
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["data.pipeline", "ml", "app"])
def test_layer_can_be_imported(name: str) -> None:
    module = import_module(name)
    root = Path(__file__).resolve().parents[1]
    assert all(Path(path).is_relative_to(root) for path in module.__path__)
