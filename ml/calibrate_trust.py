"""Measure the trust distances from the data (ML-04 thresholds) and save trust_calibration.json.

Question answered: how close must a NASA test be before its outcome predicts ours? For every
test with a known outcome, look at the other known tests of the same fuel type (leave-one-out),
using the same normalised distance as nearest_tests(). Then:
- medium distance = the largest candidate d where the single nearest neighbour within d gets the
  outcome right at least MEDIUM_ACCURACY of the time;
- strong distance = the largest candidate d where a majority vote of >= TRUST_STRONG_COUNT
  neighbours within d is right at least STRONG_ACCURACY of the time.
Each needs at least MIN_SUPPORT tests to count, and both targets are raised to the majority rate
(always guessing the more common outcome): a neighbour that is no better than that guess carries
no information. If no candidate qualifies, the config default stays and the file says so.
Run after `make train`: `python ml/calibrate_trust.py`.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.pipeline import config, model  # noqa: E402

log = logging.getLogger("calibrate_trust")

CANDIDATES = (0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)
MEDIUM_ACCURACY = 0.75
STRONG_ACCURACY = 0.90
MIN_SUPPORT = 20


def _distances(rows) -> np.ndarray:
    """Pairwise normalised distances, scaled exactly as in model.nearest_with_distance."""
    table = model.usable_rows(model.load_table())
    scaled = []
    for feature in model.DIST_FEATURES:
        span = float(table[feature].max() - table[feature].min()) or 1.0
        scaled.append(rows[feature].to_numpy(dtype=float) / span)
    points = np.column_stack(scaled)
    return np.sqrt(((points[:, None, :] - points[None, :, :]) ** 2).sum(axis=2))


def calibrate() -> dict:
    rows = model.usable_rows(model.load_table(), known_only=True).reset_index(drop=True)
    burned = (rows["outcome"] == "burned").to_numpy()
    fuel = rows["fuel_type"].to_numpy()
    dist = _distances(rows)
    np.fill_diagonal(dist, np.inf)  # leave-one-out: a test never supports itself
    dist[fuel[:, None] != fuel[None, :]] = np.inf  # same fuel type only, as trust_level() does

    table = []
    for d in CANDIDATES:
        nn_hits, nn_n, vote_hits, vote_n = 0, 0, 0, 0
        for i in range(len(rows)):
            near = np.where(dist[i] <= d)[0]
            if len(near):
                nearest = near[np.argmin(dist[i][near])]
                nn_n += 1
                nn_hits += burned[nearest] == burned[i]
            if len(near) >= config.TRUST_STRONG_COUNT:
                vote_n += 1
                vote_hits += (burned[near].mean() >= 0.5) == burned[i]
        table.append(
            {
                "distance": d,
                "nearest_neighbour_accuracy": round(nn_hits / nn_n, 3) if nn_n else None,
                "nearest_neighbour_support": nn_n,
                "majority_vote_accuracy": round(vote_hits / vote_n, 3) if vote_n else None,
                "majority_vote_support": vote_n,
            }
        )

    # The bar a neighbour must clear: guessing each test's own fuel type's more common outcome.
    hits = 0
    for f in set(fuel):
        mine = burned[fuel == f]
        hits += max(mine.sum(), len(mine) - mine.sum())
    majority = hits / len(rows)
    medium_target = max(MEDIUM_ACCURACY, majority)
    strong_target = max(STRONG_ACCURACY, majority)

    def largest(acc_key: str, n_key: str, target: float) -> float | None:
        ok = [
            r["distance"] for r in table if r[n_key] >= MIN_SUPPORT and (r[acc_key] or 0) >= target
        ]
        return max(ok) if ok else None

    medium = largest("nearest_neighbour_accuracy", "nearest_neighbour_support", medium_target)
    strong = largest("majority_vote_accuracy", "majority_vote_support", strong_target)
    medium_d = medium if medium is not None else config.TRUST_MEDIUM_DIST
    strong_d = strong if strong is not None else config.TRUST_STRONG_DIST
    return {
        "strong_distance": min(strong_d, medium_d),  # strong can never be looser than medium
        "medium_distance": medium_d,
        "calibrated": {"strong": strong is not None, "medium": medium is not None},
        "majority_rate": round(majority, 3),
        "finding": (
            "neighbours beat the majority guess at the chosen distances"
            if medium is not None
            else "no distance makes a neighbour's outcome beat the majority guess: the config "
            "defaults are kept, and trust mainly reflects whether the fuel model has skill"
        ),
        "rule": f"medium: nearest neighbour right >= {MEDIUM_ACCURACY:.0%}; strong: vote of "
        f">= {config.TRUST_STRONG_COUNT} right >= {STRONG_ACCURACY:.0%}; >= {MIN_SUPPORT} tests",
        "n_known_tests": int(len(rows)),
        "by_distance": table,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    try:
        result = calibrate()
        config.TRUST_CALIBRATION_PATH.write_text(json.dumps(result, indent=2) + "\n")
    except Exception:
        log.exception("calibrate_trust failed")
        raise
    log.info("strong <= %s, medium <= %s", result["strong_distance"], result["medium_distance"])
    for r in result["by_distance"]:
        log.info("%s", r)


if __name__ == "__main__":
    main()
