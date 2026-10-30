"""Milestone 4: forecast the test and out-of-sample windows (contract.md 3.9; course module 9).

Pure apart from the filters and fits themselves: numpy values in, plain Python values out; nothing
reads a file or the clock.

**What is forecast.** The three fitted models of milestone 3 (owner's default, LEARNING_LOG "Decisions
and defaults": aic, the primary model, bic and course), each with the parameters estimated on the
training split, on two windows: **test** (the course's last 10%) and **oos** (2024-01-02 to
2026-09-30). Every forecast is of the log price; the dollar values are derived from it (below).

**Static multi-step** (the course's way, `get_forecast(steps)`): one forecast path from one origin.
For the test window the origin is the last training day. For oos it is the last test day, with the
Kalman state updated through the test window by filtering the course series with the training
parameters (no refit), so the path starts from where the series actually was.

**Walk-forward one-step**: the forecast of day t uses every observation before t and nothing after,
with the parameters fixed at the training estimates; only the Kalman state moves. Done here as one
filter pass over the whole series with fixed parameters, reading the one-step predictions of the
forecast rows (`walk_forward`). That pass equals the explicit loop that appends one observation at a
time with `append(refit=False)` and forecasts one step (`walk_forward_loop`); tests/test_forecasting.py
checks the two agree on a stretch of simulated data, and that changing a future observation changes
no earlier forecast. The single pass is the one exported because the loop re-filters the whole
history at every step, so its cost grows with the square of the series length.

**Expanding-window refit** (the robustness check, AIC model only, `refit_walk_forward`): the same
one-step forecasts, but the parameters are re-estimated every REFIT_EVERY = 21 trading days on all
the data before the block, starting from the previous block's estimates (L-BFGS, the grid's
settings). The first block uses the training estimates.

**Random walk** (the baseline): tomorrow's log price is today's. One step ahead it is the previous
observation; static, it is the origin's value across the whole window. It has no fitted variance, so
it has no interval, and its dollar forecast is the price itself. It needs no model and no file of its
own: evaluation.random_walk_forecasts builds it from each window's origin and actual rows.

**Dollars.** If the log price is normal with mean mu and variance s^2 (the model's forecast mean and
variance), the price is log-normal: its median is exp(mu) and its mean is exp(mu + s^2 / 2). The
course exponentiates mu and calls it the forecast, which is the median (PR/FAQ, mistake 4). Both are
exported, from the exported mu and s so a reader can recompute them.

**Intervals.** Normal (statsmodels' and the course's): mu -+ z s with z the normal quantile at
(1 + level) / 2. Student-t: the milestone-3 fit of a t to the model's standardised residuals gives its
degrees of freedom nu; the interval is mu -+ k s with k = t_nu quantile * sqrt((nu - 2) / nu), the t
scaled to have the model's forecast variance s^2 (a t on nu > 2 degrees of freedom has variance
nu / (nu - 2)). Matching the variance, the t puts more mass near the centre and in the far tails, so
at 80% and 95% its interval is narrower than the normal's. Dollar bounds are exp of the log bounds
(exp is increasing, so the bounds carry over). The variances are statsmodels' forecast error
variances given the parameters: they leave out the uncertainty of the estimates themselves.

**Why numpy arrays.** The course passes pandas objects with the trading-day DatetimeIndex, which has
no frequency (holidays), and statsmodels 0.15 then refuses to forecast past the sample: "No supported
index is available" (course module 9). Every model here is built on a plain numpy array, so the
forecast index is positional and the dates are attached afterwards from the price table.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from arima_forecasting.selection import MAXITER, OPTIMIZER, _model

WINDOWS = ("test", "oos")
METHODS = ("static", "walk_forward", "refit")
KINDS = {"static": "multi_step", "walk_forward": "one_step", "refit": "one_step"}
REFIT_EVERY = 21  # trading days between refits (about a month)
REFIT_MODELS = ("aic",)  # the robustness check runs on the primary model only (owner's default)
LEVELS = (0.8, 0.95)
# scipy's norm.ppf(0.9) and norm.ppf(0.975), as literals so both readers hold the same doubles.
NORMAL_Z = (1.2815515655446004, 1.959963984540054)
REFIT_COV_TYPE = "none"  # the refits' standard errors are not used, so none are computed

# One artifact per (model, method): a model's two or three paths together pass the 1 MB budget
# (contract.md, size budgets), and the page shows one at a time.
FORECASTS: tuple[tuple[str, str], ...] = (
    ("aic", "static"),
    ("aic", "walk_forward"),
    ("aic", "refit"),
    ("bic", "static"),
    ("bic", "walk_forward"),
    ("course", "static"),
    ("course", "walk_forward"),
)
FORECAST_ARTIFACTS = tuple(f"forecast_{model}_{method}" for model, method in FORECASTS)


def artifact_name(model_id: str, method: str) -> str:
    return f"forecast_{model_id}_{method}"


@dataclass(frozen=True)
class Spec:
    """A fitted model reduced to what a filter needs: its order, trend and parameter vector in
    statsmodels' order (fit.json's `params[].library_name`)."""

    order: tuple[int, int, int]
    trend: str
    params: np.ndarray

    def model(self, y: np.ndarray) -> Any:
        p, d, q = self.order
        return _model(y, d, p, q, self.trend)


def spec_from_fit(model: dict[str, Any]) -> Spec:
    """The Spec of one `fit.models[]` entry. The values are fit.json's doubles, so a forecast built
    from the committed fit.json equals one built from the in-memory fit."""
    p, d, q = (int(v) for v in model["order"])
    spec = Spec((p, d, q), str(model["trend"]), np.array([float(row["value"]) for row in model["params"]]))
    names = [row["library_name"] for row in model["params"]]
    expected = list(spec.model(np.zeros(8)).param_names)
    if names != expected:
        raise ValueError(f"model {model['id']!r}: parameters {names} are not statsmodels' {expected}")
    return spec


def t_multipliers(df: float, levels: Sequence[float] = LEVELS) -> dict[str, list[float]]:
    """The Student-t quantile at (1 + level) / 2 on `df` degrees of freedom, the scale that gives the
    t the variance 1, and their product (the multiplier of the forecast standard deviation). A t on
    df <= 2 has no finite variance, so no scale matches it: refused."""
    if not (math.isfinite(df) and df > 2.0):
        raise ValueError(f"a Student-t on {df} degrees of freedom has no finite variance; the t intervals need df > 2")
    scale = math.sqrt((df - 2.0) / df)
    quantiles = [float(stats.t.ppf(0.5 + level / 2.0, df)) for level in levels]
    return {"t_quantile": quantiles, "t_scale": scale, "t_multiplier": [q * scale for q in quantiles]}


def static_forecast(y: np.ndarray, origin: int, steps: int, spec: Spec) -> tuple[np.ndarray, np.ndarray]:
    """Mean and variance of the log price 1..steps days after y[origin - 1], with the state filtered
    through y[:origin] at fixed parameters (no refit)."""
    result = spec.model(y[:origin]).filter(spec.params)
    forecast = result.get_forecast(steps)
    return np.asarray(forecast.predicted_mean, dtype=float), np.asarray(forecast.var_pred_mean, dtype=float)


def walk_forward(y: np.ndarray, start: int, stop: int, spec: Spec) -> tuple[np.ndarray, np.ndarray]:
    """One-step forecasts of y[start:stop], each from the observations before it, at fixed parameters:
    one filter pass over y[:stop] and its one-step predictions (`dynamic=False`, the default)."""
    result = spec.model(y[:stop]).filter(spec.params)
    prediction = result.get_prediction(start=start, end=stop - 1)
    return np.asarray(prediction.predicted_mean, dtype=float), np.asarray(prediction.var_pred_mean, dtype=float)


def walk_forward_loop(y: np.ndarray, start: int, stop: int, spec: Spec) -> tuple[np.ndarray, np.ndarray]:
    """The same forecasts by the explicit loop: filter y[:start], forecast one step, append the day's
    observation with `append(refit=False)`, and repeat. The reference the single pass is tested
    against; not used in the export (its cost grows with the square of the series length)."""
    result = spec.model(y[:start]).filter(spec.params)
    means, variances = [], []
    for t in range(start, stop):
        forecast = result.get_forecast(1)
        means.append(float(forecast.predicted_mean[0]))
        variances.append(float(forecast.var_pred_mean[0]))
        result = result.append(y[t : t + 1], refit=False)
    return np.array(means), np.array(variances)


def refit_walk_forward(y: np.ndarray, start: int, stop: int, spec: Spec, every: int = REFIT_EVERY) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """One-step forecasts of y[start:stop] with the parameters re-estimated every `every` rows on all
    the data before the block (an expanding window), each refit starting from the previous block's
    estimates. The first block uses `spec.params` (the training estimates). Returns the means, the
    variances, and one record per refit (the first forecast row it serves, the observations it used,
    its estimates, log-likelihood, convergence and warnings)."""
    if every < 1:
        raise ValueError(f"refit every {every} rows: must be at least 1")
    means = np.empty(stop - start)
    variances = np.empty(stop - start)
    params = spec.params
    refits: list[dict[str, Any]] = []
    for block in range(start, stop, every):
        end = min(block + every, stop)
        if block > start:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                fitted = spec.model(y[:block]).fit(start_params=params, method="statespace", method_kwargs={"method": OPTIMIZER, "maxiter": MAXITER}, cov_type=REFIT_COV_TYPE)
            params = np.asarray(fitted.params, dtype=float)
            retvals = fitted.mle_retvals
            refits.append(
                {
                    "row": block - start,
                    "n_obs": int(block),
                    "params": [float(v) for v in params],
                    "llf": float(fitted.llf),
                    "converged": bool(retvals["converged"]),
                    "iterations": int(retvals["iterations"]),
                    "warnings": [{"category": w.category.__name__, "message": str(w.message)} for w in caught],
                }
            )
        mean, var = walk_forward(y, block, end, Spec(spec.order, spec.trend, params))
        means[block - start : end - start] = mean
        variances[block - start : end - start] = var
    return means, variances, refits


@dataclass(frozen=True)
class Window:
    """A forecast window as positions in the price table: rows start..stop - 1, forecast from the
    origin, row start - 1 (the last day before the window)."""

    id: str
    start: int
    stop: int


def windows(table: pd.DataFrame) -> tuple[Window, Window]:
    """The test and oos windows of a price table (prep.price_table: train, test, oos in that order)."""
    segment = table["segment"].to_numpy()
    n_train = int((segment == "train").sum())
    n_test = int((segment == "test").sum())
    n_oos = int((segment == "oos").sum())
    expected = ["train"] * n_train + ["test"] * n_test + ["oos"] * n_oos
    if list(segment) != expected or min(n_train, n_test, n_oos) < 1:
        raise ValueError("the price table must hold train, then test, then oos rows, none empty")
    return Window("test", n_train, n_train + n_test), Window("oos", n_train + n_test, n_train + n_test + n_oos)


def interval_block(df: float) -> dict[str, Any]:
    return {"levels": list(LEVELS), "normal_z": list(NORMAL_Z), **t_multipliers(df)}


def forecast_rows(dates: Sequence[str], actual_log: np.ndarray, actual_usd: np.ndarray, mean: np.ndarray, variance: np.ndarray, intervals: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per forecast day. Every derived number is computed from the exported mean_log and
    sd_log, so a reader recomputes it from the same two doubles."""
    if not (len(dates) == len(actual_log) == len(actual_usd) == len(mean) == len(variance)):
        raise ValueError("dates, actuals and forecasts must have one value per day")
    if not np.all(variance > 0):
        raise ValueError("a forecast variance is not positive")
    z80, z95 = intervals["normal_z"]
    k80, k95 = intervals["t_multiplier"]
    rows = []
    for day, a_log, a_usd, mu, var in zip(dates, actual_log, actual_usd, mean, variance, strict=True):
        mu, sd = float(mu), math.sqrt(float(var))
        rows.append(
            {
                "date": day,
                "actual_log": float(a_log),
                "actual_usd": float(a_usd),
                "mean_log": mu,
                "sd_log": sd,
                "median_usd": math.exp(mu),
                "mean_usd": math.exp(mu + sd * sd / 2.0),
                "lower_80_usd": math.exp(mu - z80 * sd),
                "upper_80_usd": math.exp(mu + z80 * sd),
                "lower_95_usd": math.exp(mu - z95 * sd),
                "upper_95_usd": math.exp(mu + z95 * sd),
                "t_lower_80_usd": math.exp(mu - k80 * sd),
                "t_upper_80_usd": math.exp(mu + k80 * sd),
                "t_lower_95_usd": math.exp(mu - k95 * sd),
                "t_upper_95_usd": math.exp(mu + k95 * sd),
            }
        )
    return rows


def _origin(table: pd.DataFrame, index: int) -> dict[str, Any]:
    return {"date": table.index[index].date().isoformat(), "log_close": float(table["log_close"].iloc[index]), "close_usd": float(table["close_usd"].iloc[index])}


def forecast_payload(table: pd.DataFrame, model: dict[str, Any], t_df: float, method: str) -> dict[str, Any]:
    """The `data` part of one `forecast_<model>_<method>` artifact (contract.md 3.9). `model` is a
    `fit.models[]` entry, `t_df` that model's residual t fit (`residuals_<id>.t_fit.df`)."""
    if method not in METHODS or (method == "refit" and model["id"] not in REFIT_MODELS):
        raise ValueError(f"no {method!r} forecast for model {model['id']!r}")
    spec = spec_from_fit(model)
    y = table["log_close"].to_numpy(dtype=float)
    usd = table["close_usd"].to_numpy(dtype=float)
    intervals = interval_block(t_df)
    test, oos = windows(table)
    paths: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    refits: list[dict[str, Any]] | None = None
    if method == "static":
        for w in (test, oos):
            paths[w.id] = static_forecast(y, w.start, w.stop - w.start, spec)
    elif method == "walk_forward":
        mean, var = walk_forward(y, test.start, oos.stop, spec)
        paths = {w.id: (mean[w.start - test.start : w.stop - test.start], var[w.start - test.start : w.stop - test.start]) for w in (test, oos)}
    else:
        mean, var, records = refit_walk_forward(y, test.start, oos.stop, spec)
        paths = {w.id: (mean[w.start - test.start : w.stop - test.start], var[w.start - test.start : w.stop - test.start]) for w in (test, oos)}
        names = [row["name"] for row in model["params"]]
        refits = [
            {
                "start_date": table.index[test.start + r["row"]].date().isoformat(),
                "n_obs": r["n_obs"],
                "params": [{"name": name, "value": value} for name, value in zip(names, r["params"], strict=True)],
                "llf": r["llf"],
                "converged": r["converged"],
                "iterations": r["iterations"],
                "warnings": r["warnings"],
            }
            for r in records
        ]
    blocks = []
    for w in (test, oos):
        dates = [ts.date().isoformat() for ts in table.index[w.start : w.stop]]
        mean, var = paths[w.id]
        blocks.append(
            {
                "id": w.id,
                "start": dates[0],
                "end": dates[-1],
                "n": w.stop - w.start,
                "origin": _origin(table, w.start - 1),
                "rows": forecast_rows(dates, y[w.start : w.stop], usd[w.start : w.stop], mean, var, intervals),
            }
        )
    return {
        "model_id": model["id"],
        "label": model["label"],
        "method": method,
        "kind": KINDS[method],
        "order": list(spec.order),
        "trend": spec.trend,
        "parameters": "expanding_refit" if method == "refit" else "train",
        "refit_every": REFIT_EVERY if method == "refit" else None,
        "t_df": float(t_df),
        "intervals": intervals,
        "windows": blocks,
        "refits": refits,
    }


def forecast_payloads(table: pd.DataFrame, fit: dict[str, Any], residuals: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every forecast artifact, keyed by name, in FORECAST_ARTIFACTS order. `fit` is the fit payload
    and `residuals` the `residuals_<id>` payloads (each model's t fit)."""
    models = {m["id"]: m for m in fit["models"]}
    out = {}
    for model_id, method in FORECASTS:
        t_df = residuals[f"residuals_{model_id}"]["t_fit"]["df"]
        out[artifact_name(model_id, method)] = forecast_payload(table, models[model_id], t_df, method)
    return out
