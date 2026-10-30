"""Milestone 3: fit three models on the training split, and describe each fit (contract.md 3.7).

Pure apart from the fits themselves: numpy values in, plain Python values out; nothing reads a file
or the clock. Course module 7 ("Model Building").

The three models (owner's default, LEARNING_LOG "Decisions and defaults"; the AIC choice is the
primary model, the other two are comparisons):

- **aic**: ADR-0002's choice, the lowest-AIC ok cell of the grid. It is refitted from the grid's
  recorded estimates with the grid's own settings, so it is the grid's point, not a new search; its
  log-likelihood must equal the grid's to LLF_TOLERANCE, or the fit refuses (`GridMismatch`). That
  guard shows the recorded point is reproduced, not that it is a maximum: another optimiser started
  there can still climb a little (measured in the milestone-3 walkthrough: +1.27e-4 for the BIC
  choice, +1.8e-8 for the AIC choice).
- **bic**: the ok cell of the same d with the lowest BIC, refitted the same way.
- **course**: what the course does (ADR-0002, "What the course does"). `auto_arima` with the
  course's arguments on the **full** 2015-2023 series, test segment included (the leak), then
  `ARIMA(train, order=auto.order).fit()` with statsmodels' defaults, which has no trend at d >= 1
  (the dropped drift). `course_track` measures both: the order the same arguments pick on the
  training split alone (from aic_grid's pmdarima check), and the same order refitted with a drift.

**Inference.** statsmodels' default covariance for these fits is the outer product of gradients
(`cov_type="opg"`). For each parameter, z = estimate / standard error, and the p-value is the
probability, under the null hypothesis that the true coefficient is 0, of a z at least as far from 0
as the one observed: 2 * (1 - Phi(|z|)) for a standard normal Phi. It is not the probability that
the null is true. The 95% interval is estimate +- 1.959963984540054 * standard error. sigma2 gets no
z and no p-value (null): its null value 0 is on the boundary of the parameter space (a variance
cannot be negative), where z is not normal, so the test does not apply.

**Roots.** An ARMA model's AR and MA lag polynomials each have inverse roots (the reciprocals of
the roots, so the model is stationary and invertible when every modulus is below 1). An AR inverse
root and an MA inverse root that sit close together nearly cancel: the factor (1 - aL) on one side
and (1 - mL) on the other almost divide out, and the model behaves like a smaller one with two fewer
parameters, whose coefficients are then poorly identified (concept note 09). The rule used here
(`cancelling_pairs`): among the AR-MA pairs whose distance in the complex plane is at most
CANCEL_DISTANCE, take a one-to-one matching with as many pairs as possible, and among those the one
with the smallest total distance. The threshold is a display rule, not a test: it is stated so a
reader can apply it to the exported roots.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Any

import numpy as np
import statsmodels
from scipy.optimize import linear_sum_assignment
from scipy.stats import norm
from statsmodels.tsa.arima.model import ARIMA

from arima_forecasting.selection import MAXITER, OPTIMIZER, PMDARIMA_RUNS, _model, pmdarima_trend
from arima_forecasting.stationarity import difference

LLF_TOLERANCE = 1e-6  # the refit from the grid's estimates must reproduce the grid's llf this closely
CANCEL_DISTANCE = 0.1  # an AR and an MA inverse root this close (complex plane) are flagged as cancelling
Z95 = 1.959963984540054  # scipy's norm.ppf(0.975), as a literal so both readers hold the same double
COV_TYPE = "opg"  # statsmodels' default for these fits; recorded so the reader knows which errors these are
MODEL_IDS = ("aic", "bic", "course")
PRIMARY = "aic"

LABELS = {
    "aic": "AIC choice (ADR-0002)",
    "bic": "BIC choice",
    "course": "Course refit",
}

# The course's auto_arima arguments: the same list as aic_grid's "course" run (selection.py).
COURSE_SETTINGS: dict[str, Any] = dict(PMDARIMA_RUNS[0][1])

FIT_SETTINGS: dict[str, Any] = {
    "library": "statsmodels",
    "version": statsmodels.__version__,
    "model": "ARIMA",
    "method": "statespace",
    "optimizer": OPTIMIZER,
    "maxiter": MAXITER,
    "cov_type": COV_TYPE,
    "enforce_stationarity": True,
    "enforce_invertibility": True,
    "concentrate_scale": False,
}


class GridMismatch(ValueError):
    """The refit from the grid's recorded estimates did not reproduce the grid's log-likelihood."""


def parameter_name(library_name: str, trend: str) -> str:
    """Our name for a statsmodels parameter. In 0.15.0 `ARIMA` passes the drift of trend 't' as an
    exogenous column, so it is labelled "x1"; everything else keeps statsmodels' label."""
    if library_name == "x1" and trend == "t":
        return "drift"
    return library_name


def inverse_roots(polynomial: np.ndarray) -> list[dict[str, float]]:
    """The inverse roots of a lag polynomial 1 + c1 L + ... + cn L^n given in ascending order
    (statsmodels' polynomial_reduced_ar and _ma), sorted by modulus, largest first, then by real and
    imaginary part. They are the roots of z^n + c1 z^(n-1) + ... + cn (see
    selection.largest_inverse_root). Empty when the polynomial has no lag."""
    if len(polynomial) <= 1:
        return []
    roots = np.roots(polynomial)
    rows = [{"re": float(r.real), "im": float(r.imag), "modulus": float(abs(r))} for r in roots]
    return sorted(rows, key=lambda r: (-r["modulus"], r["re"], r["im"]))


def cancelling_pairs(ar: Sequence[dict[str, float]], ma: Sequence[dict[str, float]], distance: float = CANCEL_DISTANCE) -> list[dict[str, Any]]:
    """AR and MA inverse roots that nearly cancel: a one-to-one matching of the pairs with
    |a - m| <= distance that has as many pairs as possible, and, among those, the smallest total
    distance. Each pair gives the two indices into `ar` and `ma` and the distance; pairs are listed
    by AR index.

    Closest-first would not do: AR {0.5, 0.6} and MA {0.51, 0.41} give one pair that way (0.5 with
    0.51), where two pairs within 0.1 exist (0.5 with 0.41, 0.6 with 0.51)."""
    if not ar or not ma:
        return []
    gaps = np.array([[abs(complex(a["re"], a["im"]) - complex(m["re"], m["im"])) for m in ma] for a in ar])
    eligible = gaps <= distance
    # A cost above the threshold larger than any sum of eligible distances: every optimal assignment
    # then uses as few ineligible pairs as it can (so as many eligible ones), and the least total
    # distance among those.
    too_far = 1.0 + float(gaps[eligible].sum())
    rows, cols = linear_sum_assignment(np.where(eligible, gaps, too_far))
    return [{"ar": int(i), "ma": int(j), "distance": float(gaps[i, j])} for i, j in zip(rows, cols, strict=True) if eligible[i, j]]


def parameter_rows(result: Any, trend: str) -> list[dict[str, Any]]:
    """One row per parameter: estimate, standard error, z, two-sided p-value and 95% interval.

    Computed here from the estimate and statsmodels' standard error, so the definition is the one in
    the module docstring; a test checks the values against statsmodels' own zvalues and pvalues.
    The inference fields are null when the standard error is not a positive finite number (a
    singular covariance matrix). sigma2's z and p-value are always null (a boundary null, module
    docstring); its standard error and interval are kept."""
    rows = []
    for name, value, se in zip(result.model.param_names, result.params, result.bse, strict=True):
        value, se = float(value), float(se)
        if np.isfinite(se) and se > 0:
            z = value / se
            inference = {"std_err": se, "z": z, "p_value": float(2.0 * norm.sf(abs(z))), "ci_low": value - Z95 * se, "ci_high": value + Z95 * se}
            if name == "sigma2":
                inference.update(z=None, p_value=None)
        else:
            inference = {"std_err": None, "z": None, "p_value": None, "ci_low": None, "ci_high": None}
        rows.append({"name": parameter_name(name, trend), "library_name": name, "value": value, **inference})
    return rows


def describe(model_id: str, result: Any, order: Sequence[int], trend: str, caught: Sequence[warnings.WarningMessage], source: str, grid_llf: float | None) -> dict[str, Any]:
    """One entry of `fit.models[]` from a fitted statsmodels result."""
    retvals = result.mle_retvals
    ar = inverse_roots(result.polynomial_reduced_ar)
    ma = inverse_roots(result.polynomial_reduced_ma)
    llf = float(result.llf)
    return {
        "id": model_id,
        "label": LABELS[model_id],
        "order": [int(v) for v in order],
        "trend": trend,
        "source": source,
        "nobs": int(result.nobs),
        "nobs_effective": int(result.nobs_effective),
        "loglikelihood_burn": int(result.loglikelihood_burn),
        "params": parameter_rows(result, trend),
        "information": {
            "llf": llf,
            "aic": float(result.aic),
            "aicc": float(result.aicc),
            "bic": float(result.bic),
            "hqic": float(result.hqic),
        },
        "grid_llf": grid_llf,
        "llf_gap": None if grid_llf is None else llf - grid_llf,
        "converged": bool(retvals["converged"]),
        "iterations": int(retvals["iterations"]),
        "warnflag": int(retvals["warnflag"]),
        "warnings": [{"category": w.category.__name__, "message": str(w.message)} for w in caught],
        "inv_roots_ar": ar,
        "inv_roots_ma": ma,
        "cancelling_pairs": cancelling_pairs(ar, ma),
    }


def _grid_cell(cells: Sequence[dict[str, Any]], d: int, p: int, q: int, trend: str) -> dict[str, Any]:
    cell = next((c for c in cells if (c["d"], c["p"], c["q"], c["trend"]) == (d, p, q, trend)), None)
    if cell is None or cell["params"] is None:
        raise GridMismatch(f"the grid has no fitted cell ({p}, {d}, {q}) {trend}")
    return cell


def fit_grid_cell(y: np.ndarray, cell: dict[str, Any]) -> tuple[Any, list[warnings.WarningMessage]]:
    """Refit one grid cell with the grid's settings, starting at the grid's recorded estimates.

    The grid kept the best of many starts (selection.py); refitting from statsmodels' default start
    could stop at another local maximum. Starting at the recorded point, L-BFGS stops at once, and
    the log-likelihood must come back within LLF_TOLERANCE of the grid's (measured on AAPL: 5.0e-10
    for the AIC choice and 6.5e-8 for the BIC choice, milestone-3 walkthrough). That reproduces the
    grid's point; it does not prove the point is a maximum (Nelder-Mead from the BIC choice's point
    gains 1.27e-4, module docstring)."""
    d, p, q, trend = cell["d"], cell["p"], cell["q"], cell["trend"]
    model = _model(y, d, p, q, trend)
    start = np.array([cell["params"][name] for name in model.param_names])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = model.fit(start_params=start, method="statespace", method_kwargs={"method": OPTIMIZER, "maxiter": MAXITER}, cov_type=COV_TYPE)
    gap = float(result.llf) - cell["llf"]
    if not abs(gap) <= LLF_TOLERANCE:
        raise GridMismatch(f"refitting ({p}, {d}, {q}) {trend} from the grid's estimates gave llf {result.llf}, the grid recorded {cell['llf']} (gap {gap})")
    return result, list(caught)


def course_refit(train: np.ndarray, order: Sequence[int]) -> tuple[Any, list[warnings.WarningMessage]]:
    """The course's step (3): `ARIMA(train, order=order).fit()`, every other argument left at its
    default. statsmodels' ARIMA then has no trend when d >= 1 (statsmodels/tsa/arima/model.py:156-160)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = ARIMA(train, order=tuple(order)).fit()
    return result, list(caught)


def auto_arima_full(course: np.ndarray) -> dict[str, Any]:
    """The course's step (1): pmdarima's stepwise `auto_arima` with the course's arguments on the
    whole 2015-2023 series, test segment included. Returns the order and its estimates."""
    import pmdarima as pm

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        chosen = pm.auto_arima(course, **COURSE_SETTINGS)
    order = [int(v) for v in chosen.order]
    return {
        "order": order,
        "with_intercept": bool(chosen.with_intercept),
        "trend": pmdarima_trend(order[1], bool(chosen.with_intercept)),
        "aic": float(chosen.aic()),
        "nobs": int(chosen.arima_res_.nobs),
        "params": [{"name": str(n), "value": float(v)} for n, v in zip(chosen.arima_res_.model.param_names, chosen.params(), strict=True)],
        "warnings": [{"category": w.category.__name__, "message": str(w.message)} for w in caught],
        "pmdarima_version": str(pm.__version__),
    }


def course_track(train: np.ndarray, course: np.ndarray, aic_grid: dict[str, Any]) -> tuple[dict[str, Any], tuple[Any, list[warnings.WarningMessage], list[int]]]:
    """The course's recipe, with its leak and its dropped drift measured.

    Returns the `course_track` block and the refit (result, warnings, order) for `fit.models[]`."""
    full = auto_arima_full(course)
    order = full["order"]
    refit, caught = course_refit(train, order)
    # The same order with the drift the refit dropped, fitted with the grid's settings.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        drifted = _model(train, order[1], order[0], order[2], "t").fit(method="statespace", method_kwargs={"method": OPTIMIZER, "maxiter": MAXITER}, cov_type=COV_TYPE)
    drift = next(row for row in parameter_rows(drifted, "t") if row["name"] == "drift")
    train_run = next((r for r in aic_grid["pmdarima_check"]["runs"] if r["label"] == "course"), None)
    block = {
        "settings": dict(COURSE_SETTINGS),
        "pmdarima_version": full["pmdarima_version"],
        "n_course": int(len(course)),
        "n_train": int(len(train)),
        "test_rows_seen": int(len(course) - len(train)),
        "full_series": {k: full[k] for k in ("order", "with_intercept", "trend", "aic", "nobs", "params", "warnings")},
        "train_only": None if train_run is None else {"order": train_run["order"], "with_intercept": train_run["with_intercept"], "trend": train_run["trend"]},
        "same_order": None if train_run is None else train_run["order"] == order and train_run["with_intercept"] == full["with_intercept"],
        "refit_trend": str(refit.model.trend),
        "drift_dropped": {
            "selected_trend": full["trend"],
            "refit_trend": str(refit.model.trend),
            "aic_without_drift": float(refit.aic),
            "aic_with_drift": float(drifted.aic),
            "aic_gap": float(refit.aic) - float(drifted.aic),
            "drift": drift["value"],
            "drift_std_err": drift["std_err"],
            "drift_p_value": drift["p_value"],
        },
    }
    return block, (refit, caught, order)


def fit_models(log_close_train: object, log_close_course: object, aic_grid: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The `data` part of the "fit" artifact, and the fitted results keyed by model id (for the
    residual diagnostics, diagnostics.py). `aic_grid` is that artifact's payload: its selection
    names the AIC and BIC choices and its cells hold their estimates."""
    train = difference(log_close_train, 0)
    course = difference(log_close_course, 0)
    if len(course) <= len(train) or not np.array_equal(course[: len(train)], train):
        raise ValueError("the course series must start with the training series and be longer")
    selection = aic_grid["selection"]
    cells = aic_grid["cells"]
    p, d, q = selection["order"]
    aic_cell = _grid_cell(cells, d, p, q, selection["trend"])
    bic = selection["bic_choice"]
    bic_cell = _grid_cell(cells, d, bic["p"], bic["q"], bic["trend"])

    models = []
    results: dict[str, Any] = {}
    for model_id, cell in (("aic", aic_cell), ("bic", bic_cell)):
        result, caught = fit_grid_cell(train, cell)
        source = f"grid cell ({cell['p']}, {cell['d']}, {cell['q']}) {cell['trend']}, refitted from its recorded estimates"
        models.append(describe(model_id, result, [cell["p"], cell["d"], cell["q"]], cell["trend"], caught, source, cell["llf"]))
        results[model_id] = result
    track, (refit, caught, order) = course_track(train, course, aic_grid)
    source = f"auto_arima with the course's arguments on the full series chose {tuple(order)}; ARIMA(train, order={tuple(order)}).fit() with statsmodels' defaults"
    models.append(describe("course", refit, order, str(refit.model.trend), caught, source, None))
    results["course"] = refit
    payload = {
        "sample": "train",
        "n_train": int(len(train)),
        "primary": PRIMARY,
        "fit_settings": dict(FIT_SETTINGS),
        "z95": Z95,
        "cancel_distance": CANCEL_DISTANCE,
        "llf_tolerance": LLF_TOLERANCE,
        "models": models,
        "course_track": track,
    }
    return payload, results
