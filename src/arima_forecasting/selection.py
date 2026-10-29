"""The AIC grid: every (d, p, q, trend) fit on the training split, the choice, and pmdarima's check.

ADR-0002, sections 3 to 7. Pure apart from the fits themselves: numpy values in, plain Python
values out, and nothing reads a file or the clock.

- d is NOT chosen here. It comes from the unit-root tests (stationarity.py) and is passed in.
- Every cell is fitted with the same statsmodels settings (FIT_SETTINGS), so every cell of one d
  scores the same observations and AIC can rank them. AIC is compared only within one d.
- Nothing is dropped. A fit that raises is `failed`; one whose optimiser did not converge is
  `not_converged`; one with an inverse AR or MA root of modulus above 0.99 is `near_unit_root`
  (close to non-stationary or non-invertible). Only `ok` cells can be chosen.
- pmdarima is imported inside `pmdarima_check`, so a broken pmdarima breaks that block only.

**Several starts per cell.** An ARMA likelihood with near-cancelling roots has many local maxima,
and one optimiser run from statsmodels' default start often stops at a poor one (the milestone-2
review found 86 pairs of d = 1 cells in which a model scored below a model it nests). So each cell
is fitted from: statsmodels' default start; each fitted nested model one step smaller (one fewer AR
or MA lag, or no drift), its estimates padded with zeros, which starts the optimiser exactly at that
model's likelihood; and RANDOM_STARTS seeded random starts for cells with both AR and MA lags. The
run with the highest log-likelihood is kept (see `choose`; if it did not converge, it is restarted
once from its own estimates, `polish_start`), and the cell records which start won.
So no cell can score below a model it nests, and both readers check that. Everything is seeded; the
runs of one size go to a pool of worker processes, which changes no result.

The export tool sets OPENBLAS_NUM_THREADS=1 before numpy loads: the fits are tiny, and OpenBLAS's
default thread pool makes them several times slower; the results are bit-identical either way.
"""

from __future__ import annotations

import os
import re
import warnings
import zlib
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, wait
from typing import Any

import numpy as np
import statsmodels
from statsmodels.tsa.arima.model import ARIMA

from arima_forecasting.stationarity import difference

# The grid of ADR-0002 section 5: p, q in 0..5; d = 0 with a constant, d = 1 without and with a
# drift, d = 2 without a trend. 36 + 72 + 36 = 144 cells. Read at call time, so a test can shrink it.
GRID_ORDERS: tuple[int, ...] = tuple(range(6))
GRID_SPECS: tuple[tuple[int, tuple[str, ...]], ...] = ((0, ("c",)), (1, ("n", "t")), (2, ("n",)))

MAXITER = 200
OPTIMIZER = "lbfgs"
NEAR_UNIT_ROOT = 0.99  # pmdarima's threshold (_auto_solvers.py:42); applied to AR and MA separately
NEAR_TIE = 2.0
# Seeded random starts per cell with p >= 1 and q >= 1. Measured on the training split: the chosen
# cell is the same with 2, 6, 12 and 24, but the cells within 2 AIC of it are not; 24 found two near
# ties (ARIMA(4, 1, 3) and (5, 1, 3) with a drift) that 12 missed. See the milestone-2 walkthrough.
RANDOM_STARTS = 24
START_SEED = 20261029
# A converged run beats a higher run that did not converge when it is at most this much lower in
# log-likelihood. statsmodels minimises -llf / nobs, and L-BFGS-B stops when a step lowers that by
# less than factr * eps = 1e7 * 2.2e-16 of its size (scipy's defaults): about 1.1e-5 of llf on the
# training split (llf / nobs about 2.55, nobs 2036). Converged runs at one optimum differ by that
# much; 1e-4 is ten times it. Measured: (0, 1, 0) with a drift, from its default start, converges
# 7.8e-6 below a padded start that stops without converging.
KEEP_TOLERANCE = 1e-4
# A cell may score at most this much below a model it nests. Each step of the grid (`parents`) can
# lose at most KEEP_TOLERANCE, and the longest chain of steps within one d is 5 + 5 + 1 = 11, so
# 11 * 1e-4 = 1.1e-3 bounds it; 2e-3 of llf is 0.004 of AIC, far below the near-tie threshold of 2.
NESTING_TOLERANCE = 2e-3
WORKERS = 16  # processes for the grid (capped at the CPU count); the result does not depend on it
# Perturbed copies of each padded start: the new AR or MA coefficients get seeded values of this size
# (in the optimiser's unconstrained space), once positive and once negative, because a zero-padded
# start can sit exactly at the smaller model's optimum, which L-BFGS cannot leave (round-2 review).
PERTURB_SIZE = (0.05, 0.3)
# The polish stage (round-2 review): the cells within POLISH_WINDOW AIC of the best ok cell of each d,
# and every cell whose llf ties a model it nests (within TIE), are refitted from every such cell's
# estimates, truncated or padded: Nelder-Mead (POLISH_NM_MAXITER iterations), then L-BFGS.
POLISH_WINDOW = 4.0
TIE = 1e-6
POLISH_NM_MAXITER = 2000
POLISH_ROUNDS = 2
REPAIR_ROUNDS = 6

STATUSES = ("ok", "not_converged", "near_unit_root", "failed")
TREND_TERMS = {"n": 0, "c": 1, "t": 1}

FIT_SETTINGS: dict[str, Any] = {
    "library": "statsmodels",
    "version": statsmodels.__version__,
    "model": "ARIMA",
    "method": "statespace",
    "optimizer": OPTIMIZER,
    "maxiter": MAXITER,
    "enforce_stationarity": True,
    "enforce_invertibility": True,
    "concentrate_scale": False,
    # statsmodels' ARIMA never passes this to SARIMAX, whose default is False (ADR-0002, section 3).
    "simple_differencing": False,
    "near_unit_root_threshold": NEAR_UNIT_ROOT,
    "starts": "default, every fitted nested model one step smaller padded with zeros and two perturbed copies of it, and seeded random starts (p, q >= 1); the highest log-likelihood is kept, and restarted once from its estimates if it did not converge (', polished'); then a polish stage (Nelder-Mead, then L-BFGS, from the estimates of every cell within polish_window AIC of the best ok cell of its d or tied with a model it nests) and a repair of any nesting break",
    "perturb_size": list(PERTURB_SIZE),
    "polish_window": POLISH_WINDOW,
    "polish_nm_maxiter": POLISH_NM_MAXITER,
    "polish_rounds": POLISH_ROUNDS,
    "keep_tolerance": KEEP_TOLERANCE,
    "random_starts": RANDOM_STARTS,
    "start_seed": START_SEED,
    "nesting_tolerance": NESTING_TOLERANCE,
}

RULE = (
    "lowest AIC among status=ok cells with d = d_selected (from the unit-root tests); "
    "ties: fewer parameters, then smaller p + q, then smaller p"
)

# scipy's L-BFGS-B `warnflag`: 0 converged, 1 hit a limit, 2 stopped for another reason.
_WARNFLAGS = {1: "too many iterations or function calls", 2: "stopped for another reason, usually a failed line search"}

Key = tuple[int, int, int, str]  # (d, p, q, trend)


class ModelSearchError(ValueError):
    """The grid cannot produce a choice (for example, no cell of the chosen d is eligible)."""


def k_params(p: int, q: int, trend: str) -> int:
    """Estimated parameters: p AR, q MA, the trend term if any, and the innovation variance sigma2."""
    return p + q + TREND_TERMS[trend] + 1


def nests(small: Key, big: Key) -> bool:
    """True when the model `small` is a special case of `big`: the same d, no more AR or MA lags, and
    the same trend or none. Setting big's extra coefficients to zero gives small exactly."""
    (ds, ps, qs, ts), (db, pb, qb, tb) = small, big
    return small != big and ds == db and ps <= pb and qs <= qb and (ts == tb or ts == "n")


def parents(key: Key, trends: Sequence[str], orders: Sequence[int]) -> list[Key]:
    """The nested models one step smaller in the grid: the next smaller p, the next smaller q, or no
    trend. Following these steps from a cell reaches every model of the grid it nests."""
    d, p, q, trend = key
    orders = list(orders)
    out = []
    if orders.index(p) > 0:
        out.append((d, orders[orders.index(p) - 1], q, trend))
    if orders.index(q) > 0:
        out.append((d, p, orders[orders.index(q) - 1], trend))
    if trend != "n" and "n" in trends:
        out.append((d, p, q, "n"))
    return out


def largest_inverse_root(polynomial: np.ndarray) -> float | None:
    """The largest modulus among the inverse roots of a lag polynomial 1 + c1 L + ... + cn L^n, given
    in ascending order (statsmodels' polynomial_reduced_ar and _ma). The inverse roots are the roots
    of z^n + c1 z^(n-1) + ... + cn, which np.roots reads from the same coefficients. A zero top
    coefficient, as in a padded start that never moved, is an inverse root at 0, not a division by
    zero (statsmodels' arroots and maroots divide by it). None when the polynomial has no lag."""
    if len(polynomial) <= 1:
        return None
    return float(np.max(np.abs(np.roots(polynomial))))


def _model(y: np.ndarray, d: int, p: int, q: int, trend: str) -> ARIMA:
    return ARIMA(y, order=(p, d, q), trend=trend, enforce_stationarity=True, enforce_invertibility=True, concentrate_scale=False)


def padded_start(model: ARIMA, estimates: dict[str, float]) -> np.ndarray:
    """A start for `model` from a nested model's estimates (by parameter name), with zeros for the
    coefficients the nested model lacks. It is exactly the nested model, so the optimiser starts at
    its likelihood, and L-BFGS never ends lower than it starts."""
    return np.array([estimates.get(name, 0.0) for name in model.param_names])


def perturbed_starts(model: ARIMA, estimates: dict[str, float], key: Key, label: str) -> list[tuple[str, np.ndarray]]:
    """Two copies of a padded start in which the AR and MA coefficients the smaller model lacks are
    nonzero: seeded sizes in PERTURB_SIZE, set in the optimiser's unconstrained space (so the start
    stays stationary and invertible), once positive ("+") and once negative ("-"). None when the step
    adds no AR or MA coefficient (the trend step)."""
    new = [i for i, name in enumerate(model.param_names) if name.startswith(("ar.", "ma.")) and name not in estimates]
    if not new:
        return []
    d, p, q, trend = key
    rng = np.random.default_rng([START_SEED, d, p, q, ord(trend), zlib.crc32(label.encode())])
    size = rng.uniform(*PERTURB_SIZE, len(new))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            base = model.untransform_params(padded_start(model, estimates))
            out = []
            for sign, mark in ((1.0, "+"), (-1.0, "-")):
                u = base.copy()
                u[new] = sign * size
                out.append((mark, model.transform_params(u)))
    except Exception:  # pragma: no cover - a start statsmodels cannot map; the padded start remains
        return []
    return out


def random_starts(model: ARIMA, key: Key, count: int | None = None) -> list[np.ndarray]:
    """`count` (RANDOM_STARTS when None, read at call time) seeded random starts: the AR and MA
    coefficients drawn as N(0, 1) in the optimiser's unconstrained space and mapped back, so every
    start is stationary and invertible. The seed is derived from the cell, so a cell's starts do not
    depend on the order cells are fitted in; the k-th start is the same whatever the count."""
    count = RANDOM_STARTS if count is None else count
    d, p, q, trend = key
    rng = np.random.default_rng([START_SEED, d, p, q, ord(trend)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # statsmodels' own start may warn; the default run records it
        base = model.untransform_params(model.start_params)
    lags = [i for i, name in enumerate(model.param_names) if name.startswith(("ar.", "ma."))]
    out = []
    for _ in range(count):
        u = base.copy()
        u[lags] = rng.standard_normal(len(lags))
        out.append(model.transform_params(u))
    return out


def run_start(y: np.ndarray, key: Key, label: str, start: np.ndarray | None) -> dict[str, Any]:
    """One optimiser run of one cell from one start, summarised as plain values (picklable, so it can
    run in a worker process). A run that raises, or that ends at a non-finite value, is returned as a
    failure with its error text, so a bad start can never become the cell's result."""
    d, p, q, trend = key
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model = _model(y, d, p, q, trend)
            result = model.fit(start_params=start, method="statespace", method_kwargs={"method": OPTIMIZER, "maxiter": MAXITER})
            retvals = result.mle_retvals
            summary: dict[str, Any] = {
                "failure": None,
                "llf": float(result.llf),
                "aic": float(result.aic),
                "aicc": float(result.aicc),
                "bic": float(result.bic),
                "nobs_effective": int(result.nobs_effective),
                "converged": bool(retvals["converged"]),
                "iterations": int(retvals["iterations"]),
                "warnflag": int(retvals["warnflag"]),
                "max_inv_root_ar": largest_inverse_root(result.polynomial_reduced_ar),
                "max_inv_root_ma": largest_inverse_root(result.polynomial_reduced_ma),
                "params": dict(zip(model.param_names, map(float, result.params))),
            }
            values = [summary[k] for k in ("llf", "aic", "aicc", "bic", "max_inv_root_ar", "max_inv_root_ma") if summary[k] is not None]
            if not all(np.isfinite(values + list(summary["params"].values()))):
                raise FloatingPointError("the fit ended at a non-finite value")
        except Exception as error:  # recorded, never raised (ADR-0002, section 5)
            summary = {"failure": f"{type(error).__name__}: {error}"}
    return {"label": label, "warnings": [{"category": w.category.__name__, "message": str(w.message)} for w in caught], **summary}


def choose(runs: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The run a cell keeps: the highest log-likelihood, except that a converged run wins over a
    higher one that did not converge when the difference is at most KEEP_TOLERANCE. Ties keep the
    earlier start (the default start first).

    Keeping the highest likelihood is what makes the grid consistent: a cell started from its nested
    models can never end below them. A padded start can stop where it began, at the nested model's
    optimum, without converging (L-BFGS's line search finds no better point; seen on (4, 1, 5) with
    and without a drift). The cell then keeps that point and says it did not converge, rather than
    keep a converged but worse optimum."""
    done = [r for r in runs if r["failure"] is None]
    if not done:
        return None
    best = done[0]
    for r in done[1:]:
        if r["llf"] > best["llf"]:
            best = r
    converged = [r for r in done if r["converged"]]
    if not best["converged"] and converged:
        top = converged[0]
        for r in converged[1:]:
            if r["llf"] > top["llf"]:
                top = r
        if best["llf"] - top["llf"] <= KEEP_TOLERANCE:
            best = top
    return best


POLISHED = ", polished"


def polish_start(runs: Sequence[dict[str, Any]]) -> tuple[str, np.ndarray] | None:
    """When the run `choose` keeps did not converge, one more start: its own estimates, labelled
    "<its start>, polished". L-BFGS starts afresh there (a new curvature estimate) and usually
    converges at or above that point; measured on (0, 1, 1) with a drift, a padded start stopped
    unconverged 1.7e-4 above the converged default run, and its polish converged above both. A
    padded start that stopped exactly at the nested optimum stops there again, and the cell stays
    not converged. None when no polish is needed."""
    kept = choose(runs)
    if kept is None or kept["converged"] or kept["label"].endswith(POLISHED):
        return None
    return kept["label"] + POLISHED, np.array(list(kept["params"].values()))


def _cell_from(key: Key, runs: Sequence[dict[str, Any]], building: list[dict[str, str]] | None = None) -> dict[str, Any]:
    d, p, q, trend = key
    cell: dict[str, Any] = {"d": d, "p": p, "q": q, "trend": trend, "k_params": k_params(p, q, trend)}
    kept = choose(runs)
    if kept is None:
        first = runs[0] if runs else {"failure": "no start", "warnings": []}
        return {
            **cell,
            "warnings": (building or []) + first["warnings"],
            "status": "failed",
            "reason": "the fit raised an error",
            "aic": None,
            "aicc": None,
            "bic": None,
            "llf": None,
            "nobs_effective": None,
            "converged": None,
            "iterations": None,
            "warnflag": None,
            "max_inv_root_ar": None,
            "max_inv_root_ma": None,
            "start": None,
            "starts_tried": len(runs),
            "error": first["failure"],
            "params": None,
        }
    if len(kept["params"]) != cell["k_params"]:  # pragma: no cover - a guard against a hidden parameter
        raise RuntimeError(f"ARIMA{(p, d, q)} trend {trend!r} has {len(kept['params'])} parameters, expected {cell['k_params']}")
    ar, ma = kept["max_inv_root_ar"], kept["max_inv_root_ma"]
    near = [f"{name} {value:.6f}" for name, value in (("AR", ar), ("MA", ma)) if value is not None and value > NEAR_UNIT_ROOT]
    if not kept["converged"]:
        status, flag = "not_converged", kept["warnflag"]
        reason = f"L-BFGS did not converge after {kept['iterations']} iterations (warnflag {flag}: {_WARNFLAGS.get(flag, 'unknown')}) from the best start, {kept['label']}"
    elif near:
        status, reason = "near_unit_root", f"largest inverse root modulus above {NEAR_UNIT_ROOT}: {', '.join(near)}"
    else:
        status, reason = "ok", None
    return {
        **cell,
        "warnings": (building or []) + kept["warnings"],
        "status": status,
        "reason": reason,
        "aic": kept["aic"],
        "aicc": kept["aicc"],
        "bic": kept["bic"],
        "llf": kept["llf"],
        "nobs_effective": kept["nobs_effective"],
        "converged": kept["converged"],
        "iterations": kept["iterations"],
        "warnflag": kept["warnflag"],
        "max_inv_root_ar": ar,
        "max_inv_root_ma": ma,
        "start": kept["label"],
        "starts_tried": len(runs),
        "error": None,
        "params": kept["params"],
    }


def _nested_label(key: Key) -> str:
    d, p, q, trend = key
    return f"nested ({p}, {d}, {q}) {trend}"


_NESTED = re.compile(r"nested \(([0-9]+), ([0-9]+), ([0-9]+)\) ([nct])")


def _starts(
    y: np.ndarray, key: Key, nested: Sequence[tuple[str, dict[str, float]]]
) -> tuple[list[tuple[str, np.ndarray | None]] | None, str | None, list[dict[str, str]]]:
    """The starts of one cell: (starts, None, warnings), or (None, error, warnings) when statsmodels
    refuses the specification itself (a constant with d >= 1)."""
    d, p, q, trend = key
    with warnings.catch_warnings(record=True) as built:
        warnings.simplefilter("always")
        try:
            model = _model(y, d, p, q, trend)
            refused = None
        except Exception as error:  # recorded, never raised
            model, refused = None, f"{type(error).__name__}: {error}"
    caught = [{"category": w.category.__name__, "message": str(w.message)} for w in built]
    if model is None:
        return None, refused, caught
    starts: list[tuple[str, np.ndarray | None]] = [("default", None)]
    for label, estimates in nested:
        starts.append((label, padded_start(model, estimates)))
        starts += [(f"{label}, perturbed {mark}", start) for mark, start in perturbed_starts(model, estimates, key, label)]
    if p > 0 and q > 0:
        starts += [(f"random {i + 1}", start) for i, start in enumerate(random_starts(model, key))]
    return starts, None, caught


def fit_cell(y: np.ndarray, d: int, p: int, q: int, trend: str, nested: Sequence[tuple[str, dict[str, float]]] = ()) -> dict[str, Any]:
    """Fit one ARIMA(p, d, q) with `trend` from every start, in this process, and describe the run
    it keeps. `nested` holds (label, estimates by parameter name) of fitted nested models, used as
    padded starts; fit_grid supplies them, and a cell fitted alone has none."""
    key: Key = (d, p, q, trend)
    starts, refused, building = _starts(y, key, nested)
    if starts is None:
        return _cell_from(key, [{"label": "default", "failure": refused, "warnings": []}], building)
    runs = [run_start(y, key, label, start) for label, start in starts]
    if (polish := polish_start(runs)) is not None:
        runs.append(run_start(y, key, *polish))
    return _cell_from(key, runs, building)


def cell_order(cell: dict[str, Any]) -> tuple[int, str, int, int]:
    """The artifact's sort order: d, then trend, then p, then q."""
    return (cell["d"], cell["trend"], cell["p"], cell["q"])


def nesting_violations(cells: Sequence[dict[str, Any]], tolerance: float = NESTING_TOLERANCE) -> list[tuple[Key, Key, float]]:
    """(small, big, shortfall) for every pair of fitted cells in which `big` nests `small` but scores
    a lower log-likelihood by more than `tolerance`. A maximum likelihood cannot do that."""
    done = [c for c in cells if c["llf"] is not None]
    out = []
    for big in done:
        for small in done:
            kb, ks = (big["d"], big["p"], big["q"], big["trend"]), (small["d"], small["p"], small["q"], small["trend"])
            if nests(ks, kb) and big["llf"] < small["llf"] - tolerance:
                out.append((ks, kb, small["llf"] - big["llf"]))
    return out


def fit_grid(
    y: np.ndarray, orders: Sequence[int], specs: Sequence[tuple[int, Sequence[str]]], workers: int | None = None
) -> list[dict[str, Any]]:
    """Fit every cell, each after the models one step smaller (`parents`), so that it can start from
    their estimates.

    A cell's runs start as soon as its parents are done, and go to `workers` processes (WORKERS when
    None, capped at the number of CPUs; 1 runs everything in this process). A cell's starts depend
    only on its parents' results and every run is deterministic, so neither the number of workers
    nor the order in which runs finish changes any result.
    """
    workers = min(WORKERS if workers is None else workers, os.cpu_count() or 1)
    orders = tuple(orders)
    trends_of = {d: tuple(trends) for d, trends in specs}
    keys = [(d, p, q, t) for d, trends in specs for t in trends for p in orders for q in orders]
    waiting = {k: set(parents(k, trends_of[k[0]], orders)) for k in keys}
    children: dict[Key, list[Key]] = {k: [] for k in keys}
    for k in keys:
        for parent in sorted(waiting[k]):
            children[parent].append(k)
    cells: dict[Key, dict[str, Any]] = {}
    estimates: dict[Key, dict[str, float]] = {}
    building: dict[Key, list[dict[str, str]]] = {}
    runs: dict[Key, list[dict[str, Any] | None]] = {}
    futures: dict[Future, tuple[Key, int]] = {}
    polished: set[Key] = set()
    kept_runs: dict[Key, dict[str, Any]] = {}
    built: dict[Key, list[dict[str, str]]] = {}
    executor: Any = _pool(workers) if workers > 1 else _Inline()

    def start(key: Key) -> None:
        nested = [(_nested_label(pk), estimates[pk]) for pk in parents(key, trends_of[key[0]], orders) if pk in estimates]
        starts, refused, building[key] = _starts(y, key, nested)
        if starts is None:
            finish(key, [{"label": "default", "failure": refused, "warnings": []}])
            return
        runs[key] = [None] * len(starts)
        for i, (label, first) in enumerate(starts):
            futures[executor.submit(run_start, y, key, label, first)] = (key, i)

    def finish(key: Key, done: list[dict[str, Any]]) -> None:
        built[key] = building.pop(key)
        cells[key] = _cell_from(key, done, built[key])
        kept = choose(done)
        if kept is not None:
            estimates[key] = kept["params"]
            kept_runs[key] = kept
        for child in children[key]:
            waiting[child].discard(key)
            if not waiting[child]:
                start(child)

    try:
        for key in keys:
            if not waiting[key]:
                start(key)
        drain(y, futures, runs, polished, executor, finish)
        polish_stage(y, cells, kept_runs, built, executor)
    finally:
        executor.shutdown()
    if len(cells) != len(keys):  # pragma: no cover - every cell has a path from a cell with no parents
        raise RuntimeError(f"fitted {len(cells)} of {len(keys)} cells")
    return sorted(cells.values(), key=cell_order)


def drain(y: np.ndarray, futures: dict, runs: dict, polished: set, executor: Any, finish: Callable[[Key, list[dict[str, Any]]], None]) -> None:
    """Collect the grid stage's runs as they finish; a cell is finished when all its runs (and its
    polish restart, if any) are back."""
    while futures:
            finished, _ = wait(list(futures), return_when=FIRST_COMPLETED)
            for future in finished:
                key, i = futures.pop(future)
                runs[key][i] = future.result()
                if any(run is None for run in runs[key]):
                    continue
                polish = None if key in polished else polish_start(runs[key])  # type: ignore[arg-type]
                if polish is not None:
                    polished.add(key)
                    runs[key].append(None)
                    futures[executor.submit(run_start, y, key, *polish)] = (key, len(runs[key]) - 1)
                else:
                    finish(key, runs.pop(key))  # type: ignore[arg-type]


def transplant(model: ARIMA, estimates: dict[str, float]) -> np.ndarray:
    """Another cell's estimates as a start for `model`, matched by parameter name: padded with zeros
    where `model` has more lags, truncated where it has fewer."""
    return padded_start(model, estimates)


def polish_run(y: np.ndarray, key: Key, label: str, start: np.ndarray) -> dict[str, Any]:
    """Nelder-Mead from `start` (POLISH_NM_MAXITER iterations), then L-BFGS from where it stopped;
    the L-BFGS run is returned under `label`. Nelder-Mead does not follow the gradient, so it can leave
    a point where L-BFGS's line search stalls."""
    d, p, q, trend = key
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            moved = _model(y, d, p, q, trend).fit(start_params=start, method="statespace", method_kwargs={"method": "nm", "maxiter": POLISH_NM_MAXITER}).params
        if not np.all(np.isfinite(moved)):
            raise FloatingPointError("Nelder-Mead ended at a non-finite value")
    except Exception as error:  # recorded, never raised
        return {"label": label, "warnings": [], "failure": f"{type(error).__name__}: {error}"}
    return run_start(y, key, label, np.asarray(moved))


def _polished_label(source: Key) -> str:
    d, p, q, trend = source
    return f"polished from ({p}, {d}, {q}) {trend}"


_POLISHED_FROM = re.compile(r"polished from \(([0-9]+), ([0-9]+), ([0-9]+)\) ([nct])")


def polish_targets(cells: dict[Key, dict[str, Any]]) -> list[Key]:
    """The cells the polish stage refits: every ok cell within POLISH_WINDOW AIC of the best ok cell of
    its d, and every fitted cell whose llf ties (within TIE) a model it nests: a stalled padded start."""
    targets: set[Key] = set()
    for d in sorted({k[0] for k in cells}):
        ok = [k for k, c in cells.items() if k[0] == d and c["status"] == "ok"]
        if ok:
            best = min(cells[k]["aic"] for k in ok)
            targets |= {k for k in ok if cells[k]["aic"] - best <= POLISH_WINDOW}
    fitted = [k for k, c in cells.items() if c["llf"] is not None]
    for big in fitted:
        if any(nests(small, big) and abs(cells[big]["llf"] - cells[small]["llf"]) <= TIE for small in fitted):
            targets.add(big)
    return sorted(targets)


def polish_stage(y: np.ndarray, cells: dict[Key, dict[str, Any]], kept: dict[Key, dict[str, Any]], built: dict[Key, list[dict[str, str]]], executor: Any) -> None:
    """Refit the cells that matter from each other's estimates, then repair any nesting break.

    Each round takes a snapshot of the targets' estimates, runs `polish_run` from every target of the
    same d into every target, and keeps a run only if `choose` prefers it to the cell's current run.
    The repair then refits any cell left below a model it nests from that model's estimates (padded,
    perturbed and polished), until none is. Everything is seeded or deterministic."""

    def improve(tasks: list[tuple[Key, str, np.ndarray, Callable[..., dict[str, Any]]]]) -> bool:
        futures = {executor.submit(fn, y, key, label, first): key for key, label, first, fn in tasks}
        results: dict[Key, list[dict[str, Any]]] = {}
        for future, key in futures.items():
            results.setdefault(key, []).append(future.result())
        changed = False
        for key in sorted(results):
            done = [kept[key]] + results[key]
            best = choose(done)
            tried = cells[key]["starts_tried"] + len(results[key])
            if best is not kept[key]:
                kept[key], changed = best, True
                cells[key] = _cell_from(key, [best], built.get(key))
            cells[key]["starts_tried"] = tried
        return changed

    models = {k: _model(y, *k) for k in cells if cells[k]["llf"] is not None}
    for _ in range(POLISH_ROUNDS):
        targets = [k for k in polish_targets(cells) if k in kept]
        snapshot = {k: dict(kept[k]["params"]) for k in targets}
        tasks = [(k, _polished_label(src), transplant(models[k], snapshot[src]), polish_run) for k in targets for src in targets if src[0] == k[0]]
        if not improve(tasks):
            break
    for _ in range(REPAIR_ROUNDS):
        worst: dict[Key, Key] = {}
        for small, big, _gap in nesting_violations(list(cells.values()), tolerance=KEEP_TOLERANCE):
            if big in kept and small in kept and (big not in worst or cells[small]["llf"] > cells[worst[big]]["llf"]):
                worst[big] = small
        if not worst:
            break
        tasks = []
        for big, small in sorted(worst.items()):
            label, estimates = _polished_label(small), dict(kept[small]["params"])
            tasks.append((big, label, transplant(models[big], estimates), run_start))
            tasks.append((big, label, transplant(models[big], estimates), polish_run))
            tasks += [(big, label, start, run_start) for _, start in perturbed_starts(models[big], estimates, big, label)]
        improve(tasks)


class _Inline:
    """An executor that runs each task when it is submitted, in this process (workers = 1)."""

    def submit(self, fn: Callable[..., Any], *args: Any) -> Future:
        future: Future = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as error:  # pragma: no cover - run_start records errors itself
            future.set_exception(error)
        return future

    def shutdown(self) -> None:
        pass


def _pool(workers: int) -> Any:
    """A pool of fresh ('spawn') processes, which inherit OPENBLAS_NUM_THREADS from this one."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    return ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))


def replayable(cells: Sequence[dict[str, Any]], key: Key) -> bool:
    """True when `refit_cell` can replay a cell's kept run exactly: its start, and the start of every
    nested model its start came from, was made in the grid stage. A cell or ancestor won in the polish
    stage ("polished from ...") changed after its estimates were used, so it cannot be replayed."""
    by_key = {(c["d"], c["p"], c["q"], c["trend"]): c for c in cells}
    while True:
        label = by_key[key]["start"] or "default"
        if _POLISHED_FROM.fullmatch(label):
            return False
        match = _NESTED.fullmatch(label.removesuffix(POLISHED).partition(", perturbed ")[0])
        if match is None:
            return True
        sp, sd, sq, st = match.groups()
        key = (int(sd), int(sp), int(sq), st)


def refit_cell(
    y: np.ndarray, cells: Sequence[dict[str, Any]], key: Key, _memo: dict[Key, Any] | None = None
) -> tuple[dict[str, Any], dict[str, float] | None]:
    """Reproduce one committed cell from its recorded winning start alone, refitting the nested
    models its start came from (recursively). Used by the tests to check a committed cell without
    refitting the whole grid; every field must come back identical.

    A cell that is not `replayable` (it, or a model its start came from, was won in the polish
    stage) cannot be replayed from its label. For such a cell this returns the cell with its
    log-likelihood recomputed at its recorded parameters (`params`), which must match."""
    memo = {} if _memo is None else _memo
    if key in memo:
        return memo[key]
    cell = next(c for c in cells if (c["d"], c["p"], c["q"], c["trend"]) == key)
    label = cell["start"] or "default"
    d, p, q, trend = key
    if cell["params"] is not None and not replayable(cells, key):
        model = _model(y, d, p, q, trend)
        params = dict(cell["params"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            llf = float(model.loglike(np.array([params[name] for name in model.param_names])))
        memo[key] = ({**cell, "llf": llf}, params)
        return memo[key]
    starts, refused, building = _starts(y, key, [])
    if starts is None:
        out: tuple[dict[str, Any], dict[str, float] | None] = (
            _cell_from(key, [{"label": "default", "failure": refused, "warnings": []}], building),
            None,
        )
    else:
        model = _model(y, d, p, q, trend)
        base = label.removesuffix(POLISHED)
        if base == "default":
            start = None
        elif base.startswith("random "):
            start = random_starts(model, key, int(base.split()[1]))[-1]
        else:
            nested, _, mark = base.partition(", perturbed ")
            match = _NESTED.fullmatch(nested)
            if match is None:
                raise ValueError(f"unknown start {label!r}")
            sp, sd, sq, st = match.groups()
            _, parent = refit_cell(y, cells, (int(sd), int(sp), int(sq), st), memo)
            start = padded_start(model, parent or {})
            if mark:
                start = dict(perturbed_starts(model, parent or {}, key, nested))[mark]
        run = run_start(y, key, base, start)
        if base != label and run["failure"] is None:
            run = run_start(y, key, label, np.array(list(run["params"].values())))
        described = _cell_from(key, [run], building)
        described["starts_tried"] = cell["starts_tried"]
        out = (described, None if run["failure"] else run["params"])
    memo[key] = out
    return out


def _rank(cell: dict[str, Any]) -> tuple[float, int, int, int, str]:
    # Lowest AIC; ties: fewer parameters, smaller p + q, smaller p, then the trend code.
    return (cell["aic"], cell["k_params"], cell["p"] + cell["q"], cell["p"], cell["trend"])


def best_eligible(cells: Sequence[dict[str, Any]], d: int) -> dict[str, Any] | None:
    eligible = [c for c in cells if c["d"] == d and c["status"] == "ok"]
    return min(eligible, key=_rank) if eligible else None


def add_delta_aic(cells: list[dict[str, Any]]) -> None:
    """delta_aic = aic minus the lowest eligible AIC of the SAME d. Never across d (ADR-0002, section 3)."""
    for d in sorted({c["d"] for c in cells}):
        best = best_eligible(cells, d)
        for c in cells:
            if c["d"] == d:
                c["delta_aic"] = None if c["aic"] is None or best is None else c["aic"] - best["aic"]


def select(cells: Sequence[dict[str, Any]], d_selected: int, specs: Sequence[tuple[int, Sequence[str]]]) -> dict[str, Any]:
    """The choice, by RULE, plus the near-ties, BIC's choice and the best cell of each d (display only)."""
    best = best_eligible(cells, d_selected)
    if best is None:
        raise ModelSearchError(f"no cell with d = {d_selected} has status ok, so no order can be chosen")
    within = sorted(
        (c for c in cells if c["d"] == d_selected and c["status"] == "ok" and c["aic"] - best["aic"] <= NEAR_TIE),
        key=_rank,
    )
    eligible = [c for c in cells if c["d"] == d_selected and c["status"] == "ok"]
    bic = min(eligible, key=lambda c: (c["bic"], c["k_params"], c["p"] + c["q"], c["p"], c["trend"]))
    best_per_d = []
    for d, _ in specs:
        top = best_eligible(cells, d)
        best_per_d.append({"d": d, "cell": None if top is None else {"p": top["p"], "q": top["q"], "trend": top["trend"], "aic": top["aic"]}})
    return {
        "d_selected": d_selected,
        "order": [best["p"], d_selected, best["q"]],
        "trend": best["trend"],
        "aic": best["aic"],
        "bic": best["bic"],
        "k_params": best["k_params"],
        "rule": RULE,
        "within_2_aic": [{"p": c["p"], "q": c["q"], "trend": c["trend"], "aic": c["aic"], "delta_aic": c["delta_aic"]} for c in within],
        "bic_choice": {"p": bic["p"], "q": bic["q"], "trend": bic["trend"], "aic": bic["aic"], "bic": bic["bic"]},
        "best_per_d": best_per_d,
        "status_counts": [
            {"d": d, **{status: sum(1 for c in cells if c["d"] == d and c["status"] == status) for status in STATUSES}}
            for d, _ in specs
        ],
    }


# auto_arima on the training split, twice (ADR-0002, section 7). "course" passes the course's
# arguments, except trace=True, which only prints; "defaults" passes pmdarima's defaults plus
# seasonal=False. Every argument passed is echoed into the artifact.
PMDARIMA_RUNS: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "course",
        {
            "start_p": 1,
            "start_q": 1,
            "test": "adf",
            "max_p": 5,
            "max_q": 5,
            "m": 1,
            "d": None,
            "seasonal": False,
            "start_P": 0,
            "D": 0,
            "trace": False,
            "error_action": "ignore",
            "suppress_warnings": True,
            "stepwise": True,
        },
    ),
    ("defaults", {"seasonal": False}),
)


def pmdarima_trend(d: int, with_intercept: bool) -> str | None:
    """Our trend code for pmdarima's model: its intercept is a mean at d = 0 and a drift at d = 1.

    pmdarima's intercept and statsmodels' drift are different numbers for the same model (ADR-0002,
    section 4), but they are the same model. At d = 2 an intercept is a quadratic trend in the log
    price, which the grid does not fit, so there is no matching cell.
    """
    if not with_intercept:
        return "n"
    return {0: "c", 1: "t"}.get(d)


def _agreement(order: list[int], trend: str | None, aic: float, cells: Sequence[dict[str, Any]], selection: dict[str, Any]) -> dict[str, Any]:
    p, d, q = order
    same = next((c for c in cells if (c["d"], c["p"], c["q"], c["trend"]) == (d, p, q, trend)), None)
    return {
        "d": d == selection["d_selected"],
        "order": order == selection["order"],
        "trend": trend == selection["trend"],
        "same_order_status": None if same is None else same["status"],
        "aic_gap_same_order": None if same is None or same["aic"] is None else aic - same["aic"],
    }


def pmdarima_check(y: np.ndarray, cells: Sequence[dict[str, Any]], selection: dict[str, Any]) -> dict[str, Any]:
    """What pmdarima's stepwise auto_arima picks on the same training data, and how it compares."""
    try:
        import pmdarima as pm
    except Exception as error:
        return {"status": "unavailable", "reason": f"{type(error).__name__}: {error}", "version": None, "runs": []}
    runs = []
    try:
        for label, settings in PMDARIMA_RUNS:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                # return_valid_fits=True returns every fit the search kept, best first
                # (pmdarima/arima/auto.py:702 and _return_wrapper).
                fits = pm.auto_arima(y, return_valid_fits=True, **settings)
            chosen = fits[0]
            order = [int(v) for v in chosen.order]
            with_intercept = bool(chosen.with_intercept)
            aic = float(chosen.aic())
            trend = pmdarima_trend(order[1], with_intercept)
            retvals = chosen.arima_res_.mle_retvals
            runs.append(
                {
                    "label": label,
                    "settings": {**settings, "return_valid_fits": True},
                    "order": order,
                    "with_intercept": with_intercept,
                    "trend": trend,
                    "aic": aic,
                    "converged": bool(retvals["converged"]),
                    "iterations": int(retvals["iterations"]),
                    "visited": [
                        {"order": [int(v) for v in f.order], "with_intercept": bool(f.with_intercept), "aic": float(f.aic())}
                        for f in fits
                    ],
                    "warnings": [{"category": w.category.__name__, "message": str(w.message)} for w in caught],
                    "agreement": _agreement(order, trend, aic, cells, selection),
                }
            )
    except Exception as error:  # a runtime failure inside pmdarima is reported, never raised
        return {"status": "unavailable", "reason": f"{type(error).__name__}: {error}", "version": str(pm.__version__), "runs": []}
    return {"status": "ok", "reason": None, "version": str(pm.__version__), "runs": runs}


def aic_grid_payload(
    log_close: object,
    d_selected: int,
    *,
    orders: Sequence[int] | None = None,
    specs: Sequence[tuple[int, Sequence[str]]] | None = None,
    cross_check: Callable[[np.ndarray, Sequence[dict[str, Any]], dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The `data` part of the "aic_grid" artifact (contract.md section 3.6).

    `orders`, `specs` and `cross_check` default to the module's GRID_ORDERS, GRID_SPECS and
    pmdarima_check, read when the function runs.
    """
    y = difference(log_close, 0)
    orders = GRID_ORDERS if orders is None else tuple(orders)
    specs = GRID_SPECS if specs is None else tuple((d, tuple(trends)) for d, trends in specs)
    cross_check = pmdarima_check if cross_check is None else cross_check
    if d_selected not in [d for d, _ in specs]:
        raise ModelSearchError(f"d = {d_selected} is not in the grid's specs {[d for d, _ in specs]}")
    cells = fit_grid(y, orders, specs)
    add_delta_aic(cells)
    selection = select(cells, d_selected, specs)
    return {
        "sample": "train",
        "n_train": int(len(y)),
        "criterion": "aic",
        "grid": {"p": list(orders), "q": list(orders), "specs": [{"d": d, "trends": list(trends)} for d, trends in specs]},
        "fit_settings": dict(FIT_SETTINGS),
        "cells": cells,
        "selection": selection,
        "pmdarima_check": cross_check(y, cells, selection),
    }
