"""Descriptive statistics of the training split: a summary, two KDEs and a decomposition.

Pure: every function takes pandas or numpy values and returns plain Python values (floats, lists,
dicts, and None for a missing value). Nothing here reads a file.

Every function is meant to be called on the TRAINING rows only (ADR-0002, section 1). Looking at
the test period while describing the data is a mild form of leakage: what you notice can shape the
model you choose.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde, norm
from statsmodels.tsa.seasonal import seasonal_decompose

KDE_POINTS = 200
KDE_BANDWIDTH_METHOD = "scott"
# The grid runs this many bandwidths past the smallest and largest value. A Gaussian kernel three
# standard deviations from its centre is at 1.1% of its peak, so the curve has nearly reached zero.
KDE_GRID_PAD_BANDWIDTHS = 3.0

DECOMPOSITION_PERIOD = 252  # trading days in a year, approximately; the course's value


def _floats(values: object) -> np.ndarray:
    array = np.asarray(values, dtype="float64")
    if array.ndim != 1:
        raise ValueError(f"expected one-dimensional values, got shape {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError("values contain NaN or infinity")
    return array


def _number(value: float) -> float:
    """A plain float, refusing NaN and infinity, which the contract never writes."""
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"non-finite result {out}")
    return out


def log_returns(log_close: pd.Series) -> pd.Series:
    """Daily log returns, r_t = ln P_t - ln P_{t-1}: the first difference of the log close.

    The first day has no previous day, so n prices give n - 1 returns.
    """
    return log_close.diff().iloc[1:]


def summary(table: pd.DataFrame) -> dict[str, Any]:
    """n, first and last date, the close in dollars, and the four moments of the log return.

    The estimators are pandas' defaults, named here because each has rivals:
    - std: the sample standard deviation, divided by n - 1 (ddof=1).
    - skew: the adjusted Fisher-Pearson coefficient G1 (bias-corrected; scipy's skew(bias=False)).
    - excess_kurtosis: the bias-corrected excess kurtosis G2 (scipy's kurtosis(bias=False)); a
      normal distribution has 0.
    """
    close = table["close_usd"]
    returns = log_returns(table["log_close"])
    return {
        "n": int(len(table)),
        "start": table.index[0].date().isoformat(),
        "end": table.index[-1].date().isoformat(),
        "close_usd": {
            "min": _number(close.min()),
            "max": _number(close.max()),
            "mean": _number(close.mean()),
            "median": _number(close.median()),
        },
        "log_return": {
            "n": int(len(returns)),
            "mean": _number(returns.mean()),
            "std": _number(returns.std(ddof=1)),
            "skew": _number(returns.skew()),
            "excess_kurtosis": _number(returns.kurt()),
        },
    }


def tail_share(values: object, k: float = 3.0) -> dict[str, float]:
    """The share of values more than k sample standard deviations from the mean, and what a
    normal distribution would give: 2 * (1 - Phi(k)), which is 0.27% for k = 3.

    A much larger observed share is what "fat tails" means in practice.
    """
    data = _floats(values)
    mean, sd = data.mean(), data.std(ddof=1)
    return {
        "k": float(k),
        "observed": _number(np.mean(np.abs(data - mean) > k * sd)),
        "normal": _number(2.0 * norm.sf(k)),
    }


def kde(values: object, variable: str, points: int = KDE_POINTS) -> dict[str, Any]:
    """A Gaussian kernel density estimate on an even grid, with a normal curve for comparison.

    A KDE puts a small normal bump (the kernel) on every observation and adds them up. The
    bandwidth h is the standard deviation of each bump. Scott's rule sets h = n^(-1/5) * s, where
    s is the sample standard deviation (ddof=1). This is scipy's default and the one pandas'
    `plot(kind='kde')` uses, which is what the course calls.

    `normal_density` is the normal distribution with the sample's mean and standard deviation. Where
    the KDE sits above it in the tails, the data has fat tails.
    """
    data = _floats(values)
    if len(data) < 2:
        raise ValueError("a KDE needs at least two values")
    estimator = gaussian_kde(data, bw_method=KDE_BANDWIDTH_METHOD)
    # The kernel's covariance is factor^2 times the sample variance, so its square root is h.
    bandwidth = math.sqrt(float(estimator.covariance[0, 0]))
    pad = KDE_GRID_PAD_BANDWIDTHS * bandwidth
    grid = np.linspace(data.min() - pad, data.max() + pad, points)
    density = estimator(grid)
    mean, sd = float(data.mean()), float(data.std(ddof=1))
    normal = norm.pdf(grid, loc=mean, scale=sd)
    return {
        "variable": variable,
        "n": int(len(data)),
        "bandwidth_method": KDE_BANDWIDTH_METHOD,
        "bandwidth_factor": _number(estimator.factor),
        "bandwidth": _number(bandwidth),
        "points": [
            {"x": _number(x), "density": _number(d), "normal_density": _number(nd)}
            for x, d, nd in zip(grid, density, normal, strict=True)
        ],
    }


def decompose(log_close: pd.Series, period: int = DECOMPOSITION_PERIOD, model: str = "additive"):
    """statsmodels' classical decomposition of the log close: trend, seasonal and residual.

    The trend is a centred moving average over `period` days. It needs period // 2 days on each
    side, so the first and last period // 2 trend and residual values are NaN (statsmodels' default
    extrapolate_trend=0 leaves them missing). The seasonal part is the average detrended value at
    each position in the year, repeated. The values are passed as a plain array with an explicit
    period, because a trading-day date index has no frequency for statsmodels to read.
    """
    values = _floats(log_close.to_numpy())
    if len(values) < 2 * period:
        raise ValueError(f"a period of {period} needs at least {2 * period} values, got {len(values)}")
    return seasonal_decompose(values, model=model, period=period)


def _nullable(value: float) -> float | None:
    return None if math.isnan(value) else _number(value)


def decomposition(log_close: pd.Series, period: int = DECOMPOSITION_PERIOD) -> dict[str, Any]:
    """The additive decomposition of the log close as contract rows, with null where undefined."""
    result = decompose(log_close, period=period, model="additive")
    rows = [
        {
            "date": ts.date().isoformat(),
            "observed_log": _number(obs),
            "trend_log": _nullable(trend),
            "seasonal_log": _number(seas),
            "resid_log": _nullable(resid),
        }
        for ts, obs, trend, seas, resid in zip(
            log_close.index, result.observed, result.trend, result.seasonal, result.resid, strict=True
        )
    ]
    return {"model": "additive", "period": period, "rows": rows}


def course_comparison(table: pd.DataFrame, period: int = DECOMPOSITION_PERIOD) -> dict[str, float]:
    """How the course's "multiplicative on logs" differs from our additive-on-logs decomposition.

    The course calls seasonal_decompose(log_close, model='multiplicative'). That reads the log as a
    PRODUCT: ln P = T * S * R. Our model reads it as a SUM: ln P = T + S + R, which is the same as
    P = e^T * e^S * e^R, a product in dollars. Returned, all on the training rows:

    - trend_max_abs_diff: the two trends are the same moving average, so this is 0.
    - additive_seasonal_range: max minus min of S in our version, in log points.
    - multiplicative_seasonal_min / _max: the course's seasonal factors, which hover around 1.
    - seasonal_gap_max_abs: the largest |T * (S_mult - 1) - S_add|, in log points: how far the
      course's seasonal effect, put on our scale, moves from ours.
    - dollar_trend_max_rel_gap: the largest |exp(T_log) / T_usd - 1|, where T_usd is the trend of a
      multiplicative decomposition of the dollar close. exp of a moving average of logs is a
      weighted geometric mean of prices, T_usd the arithmetic one, so "additive on logs equals
      multiplicative on dollars" holds for the model, not exactly for the estimate. The gap is
      roughly half the weighted variance of ln P inside one window, which a strong drift alone
      produces.
    - dollar_seasonal_max_rel_gap: the largest |exp(S_add) / S_usd - 1|, the same comparison for
      the seasonal parts.
    """
    log_close = table["log_close"]
    additive = decompose(log_close, period, "additive")
    course = decompose(log_close, period, "multiplicative")
    dollars = decompose(table["close_usd"], period, "multiplicative")
    keep = ~np.isnan(additive.trend)
    trend = additive.trend[keep]
    return {
        "trend_max_abs_diff": _number(np.max(np.abs(trend - course.trend[keep]))),
        "additive_seasonal_range": _number(additive.seasonal.max() - additive.seasonal.min()),
        "multiplicative_seasonal_min": _number(course.seasonal.min()),
        "multiplicative_seasonal_max": _number(course.seasonal.max()),
        "seasonal_gap_max_abs": _number(
            np.max(np.abs(trend * (course.seasonal[keep] - 1.0) - additive.seasonal[keep]))
        ),
        "dollar_trend_max_rel_gap": _number(np.max(np.abs(np.exp(trend) / dollars.trend[keep] - 1.0))),
        "dollar_seasonal_max_rel_gap": _number(np.max(np.abs(np.exp(additive.seasonal) / dollars.seasonal - 1.0))),
    }
