"""Milestone 4: score every forecast against the random walk (contract.md 3.10; course module 10).

Pure: the forecast payloads (forecasting.py) in, the `evaluation` payload out. Every number here is
computed from the doubles the forecast files export (actual_log, mean_log, sd_log, the USD values),
so a reader of those files can recompute each one.

**Errors and metrics.** An error is actual minus forecast. RMSE is the square root of the mean
squared error, MAE the mean absolute error, MAPE 100 times the mean of |error| / |actual| (dollars
only; on log prices it would be a percentage of a logarithm). Each is computed in log points (the
log price) and in dollars, on the median exp(mu) (what the course reports) and on the mean
exp(mu + s^2 / 2). The random walk is scored on the same rows and every model metric is divided by
it: below 1 the model is closer than the random walk on that metric.

The course's MAPE came out NaN (module 10): it subtracted a one-column DataFrame from a Series, and
pandas aligned the Series' index against the DataFrame's column labels instead of its rows, so every
difference was NaN. `_vector` refuses anything but one-dimensional numbers of the same length.

**Diebold-Mariano with the Harvey-Leybourne-Newbold correction** (`dm_test`). Diebold and Mariano
(1995, Journal of Business & Economic Statistics 13(3), 253-263) test whether two forecasts have the
same expected loss from the loss differential d_t = L(e_model,t) - L(e_rw,t): DM = mean(d) /
sqrt(V / T), with T the number of forecasts and V the long-run variance of d, gamma_0 + 2 (gamma_1 +
... + gamma_(h-1)) for h-step forecasts (gamma_k the sample autocovariance at lag k, divisor T). Harvey,
Leybourne and Newbold (1997, "Testing the equality of prediction mean squared errors", International
Journal of Forecasting 13(2), 281-291) scale it for small samples, their modified statistic
DM* = DM * sqrt((T + 1 - 2h + h (h - 1) / T) / T), and compare DM* with a Student t on T - 1 degrees
of freedom. Here h = 1 (one-step forecasts), so
V = gamma_0 and the factor is sqrt((T - 1) / T): DM* is then exactly the one-sample t statistic of d
against 0 (tests/test_evaluation.py checks this against scipy's ttest_1samp). Two-sided; the losses
are the squared and the absolute error in log points (dollar errors scale with the price level, which
changes a lot over the oos window, so their differential is far from the constant variance the test
assumes; log errors are closer to it). Volatility clustering makes d_t heteroskedastic too; gamma_0
is still the right variance for h = 1, but the t reference is then an approximation.

The verdict (`dm_verdict`): "beats_rw" when the two-sided p-value is below ALPHA and the model's mean
loss is lower, "worse_than_rw" when it is below ALPHA and higher, "no_difference" otherwise. A model
whose one-step forecasts are the random walk's (an ARIMA(0, 1, 0) without a drift is the random walk
itself) leaves nothing to test: its loss differential is 0, or rounding noise of about 1e-15, on which
DM would compute a statistic from nothing. So when every forecast is within SAME_TOLERANCE = 1e-9 log
points of the random walk's (`max_forecast_gap`), the row says "same_as_rw" and has no statistic. The
real models' forecasts are about 1e-3 log points from it (milestone-4 walkthrough).

**Interval coverage** (`coverage`). For each interval, the share of days whose actual log price lies
inside it, beside the nominal level. For one-step forecasts, Kupiec's (1995) unconditional coverage
test (Kupiec 1995, "Techniques for verifying the accuracy of risk measurement models", Journal of
Derivatives 3(2), 73-84): if the interval is right, each day is inside with probability `level`, independently of the
others, so the count is binomial; LR = -2 ln(L(level) / L(x / n)) is chi-squared on 1 df. Verdicts:
"too_narrow" (rejected, fewer inside than the level), "too_wide" (rejected, more), "consistent". A
static path's days share one origin and one cumulated error, so they are far from independent and
the binomial reference does not hold: "not_tested", count shown.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy import stats

from arima_forecasting.forecasting import FORECASTS, KINDS, LEVELS, REFIT_EVERY, WINDOWS, artifact_name

ALPHA = 0.05
DM_HORIZON = 1
DM_LOSSES = ("squared", "absolute")
DM_VERDICTS = ("beats_rw", "no_difference", "worse_than_rw", "same_as_rw")
SAME_TOLERANCE = 1e-9  # log points: one-step forecasts this close to the random walk's on every day are its
COVERAGE_VERDICTS = ("too_narrow", "consistent", "too_wide", "not_tested")
DISTRIBUTIONS = ("normal", "t")
# The interval bounds of each distribution and level, by their field names in the forecast rows.
BOUNDS = {
    ("normal", 0.8): ("lower_80_usd", "upper_80_usd"),
    ("normal", 0.95): ("lower_95_usd", "upper_95_usd"),
    ("t", 0.8): ("t_lower_80_usd", "t_upper_80_usd"),
    ("t", 0.95): ("t_lower_95_usd", "t_upper_95_usd"),
}
MULTIPLIER_KEY = {"normal": "normal_z", "t": "t_multiplier"}

METHOD_LABELS = {
    "static": "Static multi-step (the course's)",
    "walk_forward": "Walk-forward one-step",
    "refit": f"Walk-forward one-step, refit every {REFIT_EVERY} days",
}


def _vector(values: object, name: str) -> np.ndarray:
    """A one-dimensional float array, or ValueError. A one-column DataFrame is two-dimensional and
    is refused: that is the shape that made the course's MAPE NaN."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional, got shape {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} holds a value that is not finite")
    return array


def _pair(actual: object, forecast: object) -> tuple[np.ndarray, np.ndarray]:
    a, f = _vector(actual, "actual"), _vector(forecast, "forecast")
    if len(a) != len(f) or len(a) == 0:
        raise ValueError(f"actual ({len(a)}) and forecast ({len(f)}) must be non-empty and the same length")
    return a, f


def rmse(actual: object, forecast: object) -> float:
    a, f = _pair(actual, forecast)
    return float(np.sqrt(np.mean((a - f) ** 2)))


def mae(actual: object, forecast: object) -> float:
    a, f = _pair(actual, forecast)
    return float(np.mean(np.abs(a - f)))


def mape_pct(actual: object, forecast: object) -> float:
    a, f = _pair(actual, forecast)
    if np.any(a == 0):
        raise ValueError("MAPE divides by the actual value, and one is 0")
    return float(100.0 * np.mean(np.abs(a - f) / np.abs(a)))


def loss(errors: np.ndarray, kind: str) -> np.ndarray:
    if kind == "squared":
        return errors**2
    if kind == "absolute":
        return np.abs(errors)
    raise ValueError(f"unknown loss {kind!r}")


def hln_factor(n: int, h: int = DM_HORIZON) -> float:
    """Harvey, Leybourne and Newbold's small-sample factor sqrt((n + 1 - 2h + h (h - 1) / n) / n)."""
    return math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)


def dm_verdict(p_value: float, mean_diff: float, alpha: float = ALPHA) -> str:
    if p_value < alpha and mean_diff < 0:
        return "beats_rw"
    if p_value < alpha and mean_diff > 0:
        return "worse_than_rw"
    return "no_difference"


def dm_test(e_model: object, e_rw: object, loss_kind: str, h: int = DM_HORIZON, max_forecast_gap: float | None = None) -> dict[str, Any]:
    """Diebold-Mariano of the model's errors against the random walk's, with the HLN correction,
    two-sided (module docstring). Only h = 1 is implemented: the variance is gamma_0.

    `max_forecast_gap` is the largest |model forecast - random-walk forecast| over the rows; at or
    below SAME_TOLERANCE the forecasts are the random walk's and no statistic is computed ("same_as_rw").
    With forecasts that differ, a constant loss differential (variance 0) would leave DM undefined:
    refused, as it does not happen with real data."""
    if h != 1:
        raise ValueError("only one-step forecasts (h = 1) are tested here")
    a, b = _pair(e_model, e_rw)
    d = loss(a, loss_kind) - loss(b, loss_kind)
    n = len(d)
    if n < 2:
        raise ValueError("the Diebold-Mariano test needs at least two forecasts")
    gap = float(np.max(np.abs(a - b))) if max_forecast_gap is None else float(max_forecast_gap)
    mean_diff = float(np.mean(d))
    var_diff = float(np.mean((d - mean_diff) ** 2))  # gamma_0, divisor n
    row = {"loss": loss_kind, "n": n, "max_forecast_gap": gap, "mean_diff": mean_diff, "var_diff": var_diff, "hln_factor": hln_factor(n, h), "df": n - 1}
    if gap <= SAME_TOLERANCE:
        return {**row, "statistic": None, "statistic_hln": None, "p_value": None, "verdict": "same_as_rw"}
    if not var_diff > 0:
        raise ValueError("the loss differential is constant, so its variance is 0 and DM is undefined")
    statistic = mean_diff / math.sqrt(var_diff / n)
    corrected = statistic * row["hln_factor"]
    p_value = float(2.0 * stats.t.sf(abs(corrected), n - 1))
    return {**row, "statistic": statistic, "statistic_hln": corrected, "p_value": p_value, "verdict": dm_verdict(p_value, mean_diff)}


def kupiec(n: int, inside: int, level: float) -> tuple[float, float]:
    """Kupiec's unconditional coverage LR statistic for `inside` of `n` days inside an interval of
    nominal `level`, and its chi-squared (1 df) p-value. 0 log 0 is taken as 0."""
    if not (0 <= inside <= n and n >= 1 and 0 < level < 1):
        raise ValueError(f"inside {inside} of {n} at level {level}")
    outside = n - inside
    rate = inside / n

    def term(count: int, prob: float) -> float:
        return 0.0 if count == 0 else count * math.log(prob)

    lr = -2.0 * (term(inside, level) + term(outside, 1.0 - level) - term(inside, rate) - term(outside, 1.0 - rate))
    lr = lr if lr > 0.0 else 0.0  # x / n equal to the level gives 0 up to rounding (and -0.0 is written as 0.0)
    return lr, float(stats.chi2.sf(lr, 1))


def coverage_verdict(kind: str, p_value: float | None, rate: float, level: float, alpha: float = ALPHA) -> str:
    if kind != "one_step" or p_value is None:
        return "not_tested"
    if p_value >= alpha:
        return "consistent"
    return "too_narrow" if rate < level else "too_wide"


def coverage(rows: Sequence[Mapping[str, Any]], kind: str, distribution: str, level: float, multiplier: float) -> dict[str, Any]:
    """How many actual log prices lie inside mean_log -+ multiplier * sd_log (the bounds the row's
    dollar interval was built from), and the Kupiec test for one-step forecasts."""
    inside = sum(1 for r in rows if r["mean_log"] - multiplier * r["sd_log"] <= r["actual_log"] <= r["mean_log"] + multiplier * r["sd_log"])
    n = len(rows)
    rate = inside / n
    lr = p = None
    if kind == "one_step":
        lr, p = kupiec(n, inside, level)
    return {"distribution": distribution, "level": level, "n": n, "inside": inside, "rate": rate, "lr": lr, "p_value": p, "verdict": coverage_verdict(kind, p, rate, level)}


def _metrics(actual_log: np.ndarray, actual_usd: np.ndarray, forecast_log: np.ndarray, median_usd: np.ndarray, mean_usd: np.ndarray | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "log": {"rmse": rmse(actual_log, forecast_log), "mae": mae(actual_log, forecast_log)},
        "usd_median": {"rmse": rmse(actual_usd, median_usd), "mae": mae(actual_usd, median_usd), "mape_pct": mape_pct(actual_usd, median_usd)},
    }
    if mean_usd is not None:
        out["usd_mean"] = {"rmse": rmse(actual_usd, mean_usd), "mae": mae(actual_usd, mean_usd), "mape_pct": mape_pct(actual_usd, mean_usd)}
    return out


def random_walk_forecasts(window: Mapping[str, Any], kind: str) -> tuple[np.ndarray, np.ndarray]:
    """The random walk's forecasts of a window's rows, in log points and dollars: the origin's value
    on every row (static), or the previous row's actual (one step; the origin's for the first row)."""
    rows = window["rows"]
    origin = window["origin"]
    if kind == "multi_step":
        return np.full(len(rows), origin["log_close"]), np.full(len(rows), origin["close_usd"])
    logs = [origin["log_close"], *(r["actual_log"] for r in rows[:-1])]
    usd = [origin["close_usd"], *(r["actual_usd"] for r in rows[:-1])]
    return np.array(logs, dtype=float), np.array(usd, dtype=float)


def _column(rows: Sequence[Mapping[str, Any]], key: str) -> np.ndarray:
    return np.array([r[key] for r in rows], dtype=float)


def _ratios(model: dict[str, Any], rw: dict[str, Any]) -> dict[str, Any]:
    return {
        "log": {k: model["log"][k] / rw["log"][k] for k in ("rmse", "mae")},
        "usd_median": {k: model["usd_median"][k] / rw["usd"][k] for k in ("rmse", "mae", "mape_pct")},
        "usd_mean": {k: model["usd_mean"][k] / rw["usd"][k] for k in ("rmse", "mae", "mape_pct")},
    }


def evaluation_payload(forecasts: Mapping[str, Mapping[str, Any]], fit: Mapping[str, Any]) -> dict[str, Any]:
    """The `data` part of the "evaluation" artifact (contract.md 3.10), from the forecast payloads
    keyed by artifact name and the fit payload (for the models' labels)."""
    first = forecasts[artifact_name(*FORECASTS[0])]
    windows = [{k: w[k] for k in ("id", "start", "end", "n")} | {"origin_date": w["origin"]["date"]} for w in first["windows"]]
    random_walk = []
    for kind in ("multi_step", "one_step"):
        for w in first["windows"]:
            rw_log, rw_usd = random_walk_forecasts(w, kind)
            m = _metrics(_column(w["rows"], "actual_log"), _column(w["rows"], "actual_usd"), rw_log, rw_usd, None)
            random_walk.append({"kind": kind, "window": w["id"], "n": len(w["rows"]), "log": m["log"], "usd": m["usd_median"]})
    rw_index = {(r["kind"], r["window"]): r for r in random_walk}
    metrics, dm, cover = [], [], []
    for model_id, method in FORECASTS:
        data = forecasts[artifact_name(model_id, method)]
        kind = KINDS[method]
        for w in data["windows"]:
            rows = w["rows"]
            actual_log, actual_usd = _column(rows, "actual_log"), _column(rows, "actual_usd")
            mean_log, sd_log = _column(rows, "mean_log"), _column(rows, "sd_log")
            m = _metrics(actual_log, actual_usd, mean_log, _column(rows, "median_usd"), _column(rows, "mean_usd"))
            rw = rw_index[(kind, w["id"])]
            gap = np.expm1(sd_log * sd_log / 2.0) * 100.0  # mean_usd / median_usd - 1, in percent
            metrics.append(
                {
                    "model_id": model_id,
                    "method": method,
                    "window": w["id"],
                    "n": len(rows),
                    **m,
                    "ratio_to_rw": _ratios(m, rw),
                    "back_transform": {"max_pct": float(gap.max()), "mean_pct": float(gap.mean())},
                }
            )
            if kind == "one_step":
                rw_log, _ = random_walk_forecasts(w, kind)
                gap = float(np.max(np.abs(mean_log - rw_log)))
                for loss_kind in DM_LOSSES:
                    dm.append({"model_id": model_id, "method": method, "window": w["id"], **dm_test(actual_log - mean_log, actual_log - rw_log, loss_kind, max_forecast_gap=gap)})
            for distribution in DISTRIBUTIONS:
                for index, level in enumerate(LEVELS):
                    multiplier = data["intervals"][MULTIPLIER_KEY[distribution]][index]
                    cover.append({"model_id": model_id, "method": method, "window": w["id"], **coverage(rows, kind, distribution, level, multiplier)})
    labels = {m["id"]: m["label"] for m in fit["models"]}
    return {
        "alpha": ALPHA,
        "interval_levels": list(LEVELS),
        "refit_every": REFIT_EVERY,
        "headline_usd": "median",
        "dm_settings": {"horizon": DM_HORIZON, "errors": "log", "losses": list(DM_LOSSES), "correction": "harvey_leybourne_newbold", "alternative": "two_sided", "baseline": "random_walk", "same_tolerance": SAME_TOLERANCE},
        "windows": windows,
        "models": [
            {"id": model_id, "label": labels[model_id], "methods": [method for mid, method in FORECASTS if mid == model_id], "t_df": forecasts[artifact_name(model_id, "static")]["t_df"]}
            for model_id in dict.fromkeys(mid for mid, _ in FORECASTS)
        ],
        "methods": [{"id": method, "kind": KINDS[method], "label": METHOD_LABELS[method]} for method in dict.fromkeys(method for _, method in FORECASTS)],
        "random_walk": random_walk,
        "metrics": metrics,
        "dm": dm,
        "coverage": cover,
    }


__all__ = ["WINDOWS", "evaluation_payload"]
