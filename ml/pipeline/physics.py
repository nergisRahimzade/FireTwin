"""Physics-shaped burn model (A1): feature maths and fitting, no file access.

Option A: logistic regression on o2, ln(u+u0), ln(u+u0)^2, pressure (or O2 partial pressure)
and one-hot fuel_type. Option B: explicit U-shaped boundary O2_crit(u) fitted per fuel_type.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.pipeline import config

log = logging.getLogger(__name__)

# Feature sets: "physics" and "physics_ppo2" are Option A, "plain" is the baseline.
VARIANTS = ("physics", "physics_ppo2", "plain")


def ln_flow(flow_cm_s: float | np.ndarray) -> float | np.ndarray:
    """ln(u + u0). Negative flow is clipped to 0, so zero flow never hits ln(0)."""
    return np.log(np.maximum(np.asarray(flow_cm_s, dtype=float), 0.0) + config.U0_CM_S)


def feature_names(variant: str) -> list[str]:
    fuels = [f"fuel_{f}" for f in config.FUEL_TYPES]
    if variant == "physics":
        return ["o2_pct", "ln_u", "ln_u_sq", "pressure_kpa", *fuels]
    if variant == "physics_ppo2":
        return ["o2_pct", "ln_u", "ln_u_sq", "ppo2_kpa", *fuels]
    if variant == "plain":
        return ["o2_pct", "pressure_kpa", "flow_cm_s", *fuels]
    raise ValueError(f"feature_names: unknown variant {variant!r}, expected one of {VARIANTS}")


def make_features(df: pd.DataFrame, variant: str) -> np.ndarray:
    """Turn rows with o2_pct, pressure_kpa, flow_cm_s, fuel_type into the model matrix."""
    try:
        o2 = df["o2_pct"].to_numpy(dtype=float)
        pressure = df["pressure_kpa"].to_numpy(dtype=float)
        flow = df["flow_cm_s"].to_numpy(dtype=float)
        lnu = ln_flow(flow)
        cols = {
            "o2_pct": o2,
            "pressure_kpa": pressure,
            "flow_cm_s": flow,
            "ln_u": lnu,
            "ln_u_sq": lnu**2,
            "ppo2_kpa": o2 / 100.0 * pressure,
        }
        for fuel in config.FUEL_TYPES:
            cols[f"fuel_{fuel}"] = (df["fuel_type"] == fuel).to_numpy(dtype=float)
        return np.column_stack([cols[name] for name in feature_names(variant)])
    except Exception:
        log.exception("make_features failed (variant=%s, columns=%s)", variant, list(df.columns))
        raise


def fit_logistic(df: pd.DataFrame, variant: str) -> Pipeline:
    """Fit standard scaling + logistic regression. df needs a 0/1 `burned` column."""
    try:
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        model.fit(make_features(df, variant), df["burned"].to_numpy(dtype=int))
        return model
    except Exception:
        log.exception("fit_logistic failed (variant=%s, n_rows=%d)", variant, len(df))
        raise


def predict_logistic(model: Pipeline, df: pd.DataFrame, variant: str) -> np.ndarray:
    return model.predict_proba(make_features(df, variant))[:, 1]


def coefficient_check(model: Pipeline, variant: str) -> dict:
    """Report whether the O2 coefficient is positive and the ln(u)^2 one negative (U shape)."""
    coefs = dict(zip(feature_names(variant), model[-1].coef_[0].tolist()))
    o2_ok = coefs["o2_pct"] > 0
    lnu_sq = coefs.get("ln_u_sq")
    return {
        "coefficients_scaled": coefs,
        "o2_coefficient_positive": o2_ok,
        "ln_u_sq_coefficient_negative": None if lnu_sq is None else lnu_sq < 0,
        "u_shape_ok": bool(o2_ok and lnu_sq is not None and lnu_sq < 0),
    }


# ---------- Option B: explicit boundary ----------


def boundary_prob(o2: np.ndarray, flow: np.ndarray, a: float, ln_u_star: float, c: float, s: float):
    """P(burn) = sigmoid((O2 - O2_crit(u)) / s), O2_crit(u) = a + c (ln(u+u0) - ln u*)^2."""
    o2_crit = a + c * (ln_flow(flow) - ln_u_star) ** 2
    z = np.clip((np.asarray(o2, dtype=float) - o2_crit) / s, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-z))


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_boundary(df: pd.DataFrame) -> dict | None:
    """Fit a, u*, c, s for ONE fuel_type by minimising log loss. None if it cannot be fitted."""
    y = df["burned"].to_numpy(dtype=float)
    if len(df) < config.MIN_ROWS_OPTION_B or y.min() == y.max():
        return None
    o2 = df["o2_pct"].to_numpy(dtype=float)
    flow = df["flow_cm_s"].to_numpy(dtype=float)

    def loss(theta: np.ndarray) -> float:
        a, ln_u_star, c, s = theta
        # small ridge on s keeps the fit finite when the classes are perfectly separable
        return _log_loss(y, boundary_prob(o2, flow, a, ln_u_star, c, s)) + 1e-3 / s

    try:
        start = np.array([float(np.median(o2)), math.log(10.0), 1.0, 1.0])
        bounds = [(0.0, 100.0), (math.log(0.5), math.log(100.0)), (0.0, 20.0), (0.05, 20.0)]
        res = minimize(loss, start, method="L-BFGS-B", bounds=bounds)
        a, ln_u_star, c, s = (float(v) for v in res.x)
        return {
            "a": a,
            "u_star_cm_s": math.exp(ln_u_star),
            "c": c,
            "s": s,
            "log_loss": _log_loss(y, boundary_prob(o2, flow, a, ln_u_star, c, s)),
            "n_rows": int(len(df)),
            "converged": bool(res.success),
        }
    except Exception:
        log.exception("fit_boundary failed (n_rows=%d)", len(df))
        raise


def predict_boundary(params: dict, df: pd.DataFrame) -> np.ndarray:
    """P(burn) per row from per-fuel Option B params; NaN where a fuel_type has no fit."""
    out = np.full(len(df), np.nan)
    for fuel, p in params.items():
        mask = (df["fuel_type"] == fuel).to_numpy()
        if p is None or not mask.any():
            continue
        out[mask] = boundary_prob(
            df.loc[mask, "o2_pct"].to_numpy(dtype=float),
            df.loc[mask, "flow_cm_s"].to_numpy(dtype=float),
            p["a"],
            math.log(p["u_star_cm_s"]),
            p["c"],
            p["s"],
        )
    return out
