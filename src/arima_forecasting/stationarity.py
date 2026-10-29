"""Unit-root tests on the training log price, and the rule that picks d (ADR-0002, section 2).

Pure: every function takes numpy values and returns plain Python values. Nothing reads a file.
Call it on the TRAINING rows only: a test statistic is an estimate, and estimates use train only.

Two tests with opposite null hypotheses run on the log price (d = 0), its first difference (d = 1)
and its second difference (d = 2):

- ADF (statsmodels `adfuller`): the null is "there is a unit root". Rejecting it is evidence that
  the series is stationary.
- KPSS (statsmodels `kpss`): the null is "the series is stationary". Rejecting it is evidence that
  it is not.

Each test is run twice. The rule uses `regression="c"` (a constant), statsmodels' default and the
course's call. A second run with `regression="ct"` (a constant and a linear trend) is reported
next to it, to show whether the verdict depends on that choice. The rule never reads it.
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.stattools import adfuller, kpss

ALPHA = 0.05

# (id, d): the transforms tested, in the order the artifact lists them.
TRANSFORMS = (("log", 0), ("diff1", 1), ("diff2", 2))

RULE_REGRESSION = "c"
TREND_REGRESSION = "ct"
ADF_AUTOLAG = "AIC"
KPSS_NLAGS = "auto"
# statsmodels interpolates the KPSS p-value inside a table that runs from 0.01 to 0.10.
KPSS_P_FLOOR = 0.01
KPSS_P_CEILING = 0.10

RULE = (
    "d is the smallest of 0, 1 and 2 at which ADF rejects a unit root and KPSS does not reject "
    "stationarity, both with regression 'c' at the 5% level (p < 0.05). If no d passes both, d is "
    "the smallest at which KPSS does not reject (2 if it rejects at every d), and tests_conflict is true."
)


def difference(values: object, d: int) -> np.ndarray:
    """The d-th difference: d = 0 is the series itself, d = 1 the daily log returns."""
    array = np.asarray(values, dtype="float64")
    if array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError("expected one-dimensional finite values")
    if d < 0:
        raise ValueError(f"d must be 0 or more, got {d}")
    return array.copy() if d == 0 else np.diff(array, n=d)


def adf_maxlag(n: int, regression: str) -> int:
    """statsmodels' default largest lag for `adfuller`: ceil(12 * (n / 100) ** (1/4)) (Schwert 1989).

    It is capped at n // 2 - (number of trend terms) - 1, as statsmodels does. The tests pass this
    value explicitly, so the artifact records the lag range that AIC searched.
    """
    trend_terms = 0 if regression == "n" else len(regression)
    return min(n // 2 - trend_terms - 1, int(math.ceil(12.0 * (n / 100.0) ** 0.25)))


def adf_test(x: np.ndarray, regression: str = RULE_REGRESSION, alpha: float = ALPHA) -> dict[str, Any]:
    """Augmented Dickey-Fuller. The lag of the augmentation is chosen by AIC over 0..maxlag."""
    maxlag = adf_maxlag(len(x), regression)
    result = adfuller(x, maxlag=maxlag, regression=regression, autolag=ADF_AUTOLAG, result_object=True)
    p_value = float(result.pvalue)
    return {
        "statistic": float(result.statistic),
        "p_value": p_value,
        "used_lag": int(result.lags),
        "maxlag": int(maxlag),
        "nobs": int(result.nobs),
        "critical_values": {key: float(result.critical_values[key]) for key in ("1%", "5%", "10%")},
        "regression": regression,
        "autolag": ADF_AUTOLAG,
        "reject_unit_root": p_value < alpha,
    }


def kpss_bound(p_value: float) -> str | None:
    """Which way the true KPSS p-value lies when statsmodels clipped it to its table's edge.

    "smaller" when the reported p is the floor 0.01 (the true p is 0.01 or less), "greater" when it
    is the ceiling 0.10 (the true p is 0.10 or more), None when it was interpolated inside the table.
    These are the two cases in which statsmodels warns (stattools/_stattools.py:3224-3235).
    """
    if p_value == KPSS_P_FLOOR:
        return "smaller"
    if p_value == KPSS_P_CEILING:
        return "greater"
    return None


def kpss_test(x: np.ndarray, regression: str = RULE_REGRESSION, alpha: float = ALPHA) -> dict[str, Any]:
    """KPSS with the Hobijn et al. (1998) automatic bandwidth (`nlags="auto"`)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = kpss(x, regression=regression, nlags=KPSS_NLAGS, result_object=True)
    p_value = float(result.pvalue)
    bound = kpss_bound(p_value)
    warned = [w for w in caught if issubclass(w.category, InterpolationWarning)]
    # Our reading of the clipped p-value must match statsmodels' own warning, word for word.
    if (bound is None) != (not warned) or (bound is not None and f"is {bound} than" not in str(warned[0].message)):
        raise RuntimeError(f"KPSS p-value {p_value} and statsmodels' warnings {[str(w.message) for w in warned]} disagree")
    for other in caught:
        if not issubclass(other.category, InterpolationWarning):
            warnings.warn(other.message, other.category, stacklevel=2)
    return {
        "statistic": float(result.statistic),
        "p_value": p_value,
        "p_value_bound": bound,
        "nlags": int(result.lags),
        "nlags_method": KPSS_NLAGS,
        "critical_values": {key: float(result.critical_values[key]) for key in ("10%", "5%", "2.5%", "1%")},
        "regression": regression,
        "reject_stationarity": p_value < alpha,
    }


def verdict(adf_rejects: bool, kpss_rejects: bool) -> str:
    """The 2 x 2 table of concept note 05.

    ADF rejects, KPSS does not: "stationary". ADF does not, KPSS does: "unit_root". Both reject:
    "conflict". Neither rejects: "inconclusive" (both tests lack the power to tell).
    """
    if adf_rejects and not kpss_rejects:
        return "stationary"
    if kpss_rejects and not adf_rejects:
        return "unit_root"
    return "conflict" if adf_rejects else "inconclusive"


def run_pair(x: np.ndarray, regression: str, alpha: float = ALPHA) -> dict[str, Any]:
    adf = adf_test(x, regression, alpha)
    kp = kpss_test(x, regression, alpha)
    return {"adf": adf, "kpss": kp, "verdict": verdict(adf["reject_unit_root"], kp["reject_stationarity"])}


def decide_d(transforms: list[dict[str, Any]]) -> tuple[int, bool]:
    """(d, tests_conflict) by RULE, reading only the regression 'c' tests of each transform."""
    ordered = sorted(transforms, key=lambda t: t["d"])
    for t in ordered:
        if t["adf"]["reject_unit_root"] and not t["kpss"]["reject_stationarity"]:
            return t["d"], False
    for t in ordered:
        if not t["kpss"]["reject_stationarity"]:
            return t["d"], True
    return ordered[-1]["d"], True


def pmdarima_ndiffs(x: np.ndarray, d_selected: int, alpha: float = ALPHA, max_d: int = 2) -> dict[str, Any]:
    """pmdarima's own choice of d with each of its three tests, as a cross-check (ADR-0002, section 2).

    pmdarima's ADF, KPSS and PP are its own implementations, not statsmodels'. pmdarima is imported
    here, not at the top of the module, so a broken install breaks this block and nothing else.
    """
    try:
        import pmdarima
        from pmdarima.arima import ndiffs

        found = {test: int(ndiffs(x, alpha=alpha, test=test, max_d=max_d)) for test in ("kpss", "adf", "pp")}
    except Exception as error:  # an import or runtime failure is reported, never raised
        return {
            "status": "unavailable",
            "reason": f"{type(error).__name__}: {error}",
            "version": None,
            "alpha": alpha,
            "max_d": max_d,
            "kpss": None,
            "adf": None,
            "pp": None,
            "agrees": None,
        }
    return {
        "status": "ok",
        "reason": None,
        "version": str(pmdarima.__version__),
        "alpha": alpha,
        "max_d": max_d,
        **found,
        "agrees": all(value == d_selected for value in found.values()),
    }


def stationarity_payload(log_close: object, alpha: float = ALPHA) -> dict[str, Any]:
    """The `data` part of the "stationarity" artifact (contract.md section 3.4).

    It holds test statistics only, never the series: the d = 0 series is the log price itself.
    """
    values = difference(log_close, 0)
    transforms = []
    for transform_id, d in TRANSFORMS:
        x = difference(values, d)
        rule = run_pair(x, RULE_REGRESSION, alpha)
        transforms.append(
            {
                "id": transform_id,
                "d": d,
                "n": int(len(x)),
                "adf": rule["adf"],
                "kpss": rule["kpss"],
                "verdict": rule["verdict"],
                "with_trend": run_pair(x, TREND_REGRESSION, alpha),
            }
        )
    d_selected, conflict = decide_d(transforms)
    return {
        "sample": "train",
        "n_train": int(len(values)),
        "alpha": alpha,
        "transforms": transforms,
        "decision": {
            "d_selected": d_selected,
            "rule": RULE,
            "tests_conflict": conflict,
            "pmdarima_ndiffs": pmdarima_ndiffs(values, d_selected, alpha),
        },
    }
