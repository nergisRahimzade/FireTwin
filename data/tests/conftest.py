"""Lets the data tests import the pipeline scripts (data/pipeline/*.py) by module name."""

import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))
