"""Shared test setup for ml/tests: puts the repo root on sys.path so `import ml...` works."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
