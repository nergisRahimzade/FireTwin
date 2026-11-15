"""Train the burn model (ML-01 / A1, ML-03) and write ml/artifacts/.

Fits the physics-shaped logistic regression (Option A), the explicit boundary (Option B) and a
plain logistic baseline, compares them with leave-one-investigation-out, and saves
model.joblib, feature_ranges.json, physics_params.json and metrics.json.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.pipeline import config, model, physics  # noqa: E402

log = logging.getLogger("train")

RANGE_FEATURES = ["o2_pct", "pressure_kpa", "flow_cm_s"]


def load_training_rows(path: Path = config.TESTS_PARQUET) -> pd.DataFrame:
    """Rows with a known outcome and complete inputs, plus a 0/1 `burned` column."""
    try:
        table = pd.read_parquet(path)
    except Exception:
        log.exception("load_training_rows: cannot read %s (run `make data` first)", path)
        raise
    rows = model.usable_rows(table[table["outcome"].isin(["burned", "extinguished"])])
    rows = rows.assign(burned=(rows["outcome"] == "burned").astype(int))
    if len(rows) < 10 or rows["burned"].nunique() < 2:
        raise ValueError(f"load_training_rows: need >=10 rows with both outcomes, got {len(rows)}")
    return rows.reset_index(drop=True)


def _score(y: np.ndarray, p: np.ndarray) -> dict:
    ok = ~np.isnan(p)
    if not ok.any():
        return {"accuracy": None, "log_loss": None, "n_rows": 0}
    y, p = y[ok], np.clip(p[ok], 1e-9, 1 - 1e-9)
    base = float(np.clip(y.mean(), 1e-9, 1 - 1e-9))
    base_loss = float(-(base * np.log(base) + (1 - base) * np.log(1 - base)))
    auc = None
    if y.min() != y.max():
        from sklearn.metrics import roc_auc_score

        auc = float(roc_auc_score(y, p))
    return {
        "roc_auc": auc,
        "base_rate_log_loss": base_loss,
        "accuracy": float(np.mean((p >= 0.5) == (y == 1))),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "n_rows": int(ok.sum()),
    }


def fit_boundary_all(rows: pd.DataFrame) -> dict:
    return {
        fuel: physics.fit_boundary(rows[rows["fuel_type"] == fuel]) for fuel in config.FUEL_TYPES
    }


def leave_one_investigation_out(rows: pd.DataFrame) -> dict:
    """Hold out each investigation in turn; return pooled out-of-fold scores per model."""
    y = rows["burned"].to_numpy(dtype=float)
    preds = {
        name: np.full(len(rows), np.nan) for name in (*physics.VARIANTS, "boundary", "per_fuel")
    }
    folds = []
    for inv in sorted(rows["investigation"].unique()):
        test_mask = (rows["investigation"] == inv).to_numpy()
        train, test = rows[~test_mask], rows[test_mask]
        if train["burned"].nunique() < 2:
            log.warning("LOIO: skipping %s (training fold has one outcome only)", inv)
            continue
        for variant in physics.VARIANTS:
            model = physics.fit_logistic(train, variant)
            preds[variant][test_mask] = physics.predict_logistic(model, test, variant)
        preds["boundary"][test_mask] = physics.predict_boundary(fit_boundary_all(train), test)
        # No pooled fallback here: a fuel type with no training rows in the fold is NOT scored.
        preds["per_fuel"][test_mask] = physics.predict_per_fuel(physics.fit_per_fuel(train), test)
        folds.append({"held_out": inv, "n_test": int(test_mask.sum())})
    return {"folds": folds, **{name: _score(y, p) for name, p in preds.items()}}


def stratified_cv(rows: pd.DataFrame, n_splits: int = 5, seed: int = 0) -> dict:
    """Per fuel type: out-of-fold accuracy of its own model, next to the always-guess-majority rate.

    Optimistic by construction: tests from one investigation repeat the same conditions, so
    neighbouring folds share near-identical rows. Read it with the leave-one-investigation-out
    numbers, which are the stricter test, and with the majority rate, which is the bar to beat.
    """
    from sklearn.model_selection import StratifiedKFold

    out = {}
    for fuel in physics.FUEL_FEATURES:
        sub = rows[rows["fuel_type"] == fuel].reset_index(drop=True)
        if len(sub) < config.MIN_ROWS_PER_FUEL or sub["burned"].value_counts().min() < n_splits:
            continue
        pred = np.full(len(sub), np.nan)
        folds = StratifiedKFold(n_splits, shuffle=True, random_state=seed).split(sub, sub["burned"])
        for train_idx, test_idx in folds:
            models = physics.fit_per_fuel(sub.iloc[train_idx])
            pred[test_idx] = physics.predict_per_fuel(models, sub.iloc[test_idx])
        share = float(sub["burned"].mean())
        scored = _score(sub["burned"].to_numpy(dtype=float), pred)
        auc, loss, base = scored["roc_auc"], scored["log_loss"], scored["base_rate_log_loss"]
        scored["majority_class_accuracy"] = max(share, 1 - share)
        scored["beats_base_rate"] = bool(
            auc is not None
            and auc >= config.SKILL_MIN_AUC
            and loss <= base * (1 - config.SKILL_MIN_LOGLOSS_GAIN)
        )
        out[fuel] = scored
    return out


def feature_ranges(rows: pd.DataFrame) -> dict:
    def span(df: pd.DataFrame) -> dict:
        return {f: {"min": float(df[f].min()), "max": float(df[f].max())} for f in RANGE_FEATURES}

    return {
        "overall": span(rows),
        "by_fuel_type": {fuel: span(g) for fuel, g in rows.groupby("fuel_type")},
    }


def train(table_path: Path = config.TESTS_PARQUET, out_dir: Path = config.ARTIFACTS_DIR) -> dict:
    """Run the whole training job and return the metrics dict that was written."""
    rows = load_training_rows(table_path)
    loio = leave_one_investigation_out(rows)

    # Option A: pick pressure vs O2 partial pressure by out-of-fold log loss.
    candidates = [v for v in ("physics", "physics_ppo2") if loio[v]["log_loss"] is not None]
    variant = min(candidates, key=lambda v: loio[v]["log_loss"]) if candidates else "physics"
    model = physics.fit_logistic(rows, variant)
    check = physics.coefficient_check(model, variant)
    if not check["u_shape_ok"]:
        log.warning("COEFFICIENT CHECK FAILED (expected O2 > 0 and ln(u)^2 < 0): %s", check)

    per_fuel = physics.fit_per_fuel(rows)
    boundary = fit_boundary_all(rows)
    spread_model = physics.fit_spread(rows, variant)
    n_spread = int(rows["spread_rate_mm_s"].notna().sum())
    metrics = {
        "n_rows": int(len(rows)),
        "n_synthetic_rows": int(rows["is_synthetic"].sum()),
        "n_rows_with_assumed_pressure": int((~rows["pressure_recorded"]).sum()),
        "assumed_pressure_kpa": config.NOMINAL_PRESSURE_KPA,
        "rows_per_investigation": {
            inv: {"burned": int(g["burned"].sum()), "extinguished": int((1 - g["burned"]).sum())}
            for inv, g in rows.groupby("investigation")
        },
        "trained_on_synthetic_data": bool(rows["is_synthetic"].any()),
        "evaluation": "leave-one-investigation-out",
        "chosen_variant": variant,
        "accuracy": loio[variant]["accuracy"],
        "physics_model": loio[variant],
        "physics_model_other_variant": {v: loio[v] for v in candidates if v != variant},
        "boundary_model_option_b": loio["boundary"],
        "baseline_plain_logistic": loio["plain"],
        "folds": loio["folds"],
        "coefficient_check": check,
        "serving_model": "per-fuel logistic regressions (pooled model only for unknown fuel types)",
        "per_fuel_model": loio["per_fuel"],
        "per_fuel_stratified_cv": stratified_cv(rows),
        "fuel_models_with_skill": sorted(
            f for f, s in stratified_cv(rows).items() if s["beats_base_rate"]
        ),
        "per_fuel_coefficient_check": {
            fuel: physics.per_fuel_coefficient_check(entry) for fuel, entry in per_fuel.items()
        },
        "per_fuel_rows": {fuel: entry["n_rows"] for fuel, entry in per_fuel.items()},
        "spread_model": {"fitted": spread_model is not None, "n_rows": n_spread},
    }
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle = {
            "model": model,
            "variant": variant,
            "per_fuel": per_fuel,
            "spread_model": spread_model,
        }
        joblib.dump(bundle, out_dir / config.MODEL_PATH.name)
        for name, payload in (
            (config.RANGES_PATH.name, feature_ranges(rows)),
            (
                config.PHYSICS_PARAMS_PATH.name,
                {"u0_cm_s": config.U0_CM_S, "by_fuel_type": boundary},
            ),
            (config.METRICS_PATH.name, metrics),
        ):
            (out_dir / name).write_text(json.dumps(payload, indent=2) + "\n")
    except Exception:
        log.exception("train: could not write artifacts to %s", out_dir)
        raise
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    result = train()
    print(json.dumps({k: result[k] for k in result if k != "folds"}, indent=2))
