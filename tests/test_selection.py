"""The AIC grid, the choice and pmdarima's cross-check (src/arima_forecasting/selection.py).

Fits run on simulated log prices with a fixed seed; no market data is used. The ranking, the
deltas and the near-ties are tested on hand-built cells whose expected answers are written out.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest
import statsmodels
from statsmodels.tsa.arima.model import ARIMA

from arima_forecasting import selection as sel
from arima_forecasting.payloads import validate_aic_grid


def walk(n: int = 600, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.log(30.0) + np.cumsum(0.0008 + 0.017 * rng.standard_normal(n))


# --- the grid and one cell ---------------------------------------------------------------------

def test_the_grid_is_the_one_adr_0002_specifies():
    assert sel.GRID_ORDERS == (0, 1, 2, 3, 4, 5)
    assert sel.GRID_SPECS == ((0, ("c",)), (1, ("n", "t")), (2, ("n",)))
    cells = sum(len(trends) for _, trends in sel.GRID_SPECS) * len(sel.GRID_ORDERS) ** 2
    assert cells == 144  # 36 + 72 + 36
    assert (sel.MAXITER, sel.NEAR_UNIT_ROOT, sel.NEAR_TIE) == (200, 0.99, 2.0)


@pytest.mark.parametrize("p, q, trend, k", [(0, 0, "n", 1), (0, 0, "t", 2), (3, 5, "t", 10), (2, 2, "n", 5), (1, 0, "c", 3)])
def test_k_params_counts_ar_ma_the_trend_and_sigma2(p, q, trend, k):
    assert sel.k_params(p, q, trend) == k


def test_an_ok_cell_records_what_statsmodels_reports():
    cell = sel.fit_cell(walk(), 1, 0, 1, "t")
    assert cell["status"] == "ok" and cell["reason"] is None and cell["error"] is None
    assert cell["converged"] is True and cell["warnflag"] == 0
    assert cell["k_params"] == 3 and cell["nobs_effective"] == 599  # d = 1 burns one observation
    assert cell["aic"] == pytest.approx(-2 * cell["llf"] + 2 * 3, rel=1e-12)
    assert cell["bic"] == pytest.approx(-2 * cell["llf"] + 3 * np.log(599), rel=1e-12)
    assert cell["max_inv_root_ar"] is None and 0 <= cell["max_inv_root_ma"] < 0.99
    assert cell["warnings"] == []


def test_a_constant_with_d_1_is_a_failed_cell_with_statsmodels_message():
    # statsmodels' ARIMA puts trends in the levels, so a constant cannot survive differencing.
    cell = sel.fit_cell(walk(), 1, 1, 1, "c")
    assert cell["status"] == "failed" and cell["reason"] == "the fit raised an error"
    assert cell["error"].startswith("ValueError: In models with integration")
    for name in ("aic", "aicc", "bic", "llf", "nobs_effective", "converged", "iterations", "warnflag", "max_inv_root_ar", "max_inv_root_ma"):
        assert cell[name] is None, name
    assert cell["k_params"] == 4


def test_an_ar_root_at_one_on_the_level_of_a_random_walk_is_flagged_near_unit_root():
    cell = sel.fit_cell(walk(), 0, 1, 0, "c")
    assert cell["converged"] is True
    assert cell["max_inv_root_ar"] > 0.99 and cell["status"] == "near_unit_root"
    assert cell["reason"].startswith("largest inverse root modulus above 0.99: AR 0.99")


def test_an_ma_root_at_one_from_over_differencing_is_flagged_too():
    # pmdarima's root test lets the MA roots overwrite the AR result (_auto_solvers.py:37-40); the
    # grid checks both. Differencing white noise gives an MA(1) with theta = -1, a root on the circle.
    noise = np.random.default_rng(4).standard_normal(2000)
    cell = sel.fit_cell(noise, 1, 0, 1, "n")
    assert cell["converged"] is True and cell["max_inv_root_ar"] is None
    assert cell["max_inv_root_ma"] > 0.99 and cell["status"] == "near_unit_root"
    assert "MA 0.99" in cell["reason"]


def test_a_fit_stopped_by_maxiter_is_not_converged_and_keeps_its_warning(monkeypatch):
    monkeypatch.setattr(sel, "MAXITER", 1)
    cell = sel.fit_cell(walk(), 1, 2, 2, "n")
    assert cell["status"] == "not_converged" and cell["converged"] is False
    assert "warnflag 1" in cell["reason"] and cell["iterations"] == 1
    assert "ConvergenceWarning" in [w["category"] for w in cell["warnings"]]


def test_not_converged_takes_precedence_over_near_unit_root(monkeypatch):
    # A threshold of 0 makes every root "near", and one iteration stops the optimiser: both
    # conditions hold, and the cell must say "not converged".
    monkeypatch.setattr(sel, "MAXITER", 1)
    monkeypatch.setattr(sel, "NEAR_UNIT_ROOT", 0.0)
    cell = sel.fit_cell(walk(), 0, 1, 0, "c")
    assert cell["converged"] is False and cell["max_inv_root_ar"] > 0.0
    assert cell["status"] == "not_converged" and cell["reason"].startswith("L-BFGS did not converge")


def test_the_fit_settings_in_the_artifact_are_the_settings_statsmodels_used(monkeypatch):
    seen = {}

    class Spy(ARIMA):
        def fit(self, *args, **kwargs):
            seen["model"], seen["result"] = self, super().fit(*args, **kwargs)
            return seen["result"]

    monkeypatch.setattr(sel, "ARIMA", Spy)
    sel.fit_cell(walk(), 1, 1, 1, "t")
    model, result = seen["model"], seen["result"]
    settings = sel.FIT_SETTINGS
    assert result.mle_settings["optimizer"] == settings["optimizer"] == "lbfgs"
    assert result.mle_settings["maxiter"] == settings["maxiter"] == 200
    assert model.enforce_stationarity is settings["enforce_stationarity"] is True
    assert model.enforce_invertibility is settings["enforce_invertibility"] is True
    assert model.concentrate_scale is settings["concentrate_scale"] is False
    assert model.simple_differencing is settings["simple_differencing"] is False
    assert settings["version"] == statsmodels.__version__ == "0.15.0"


# --- several starts per cell, and the nesting rule ----------------------------------------------
# An ARMA likelihood with near-cancelling roots has many local maxima. The milestone-2 review found
# 86 pairs of d = 1 cells of the committed grid in which a model scored below a model it nests. These
# tests use a simulated walk (seed 2) on which one default start per cell does the same.


def run(label, llf=None, converged=True, failure=None):
    return {"label": label, "llf": llf, "converged": converged, "failure": failure, "warnings": []}


def test_choose_keeps_the_highest_likelihood_even_from_a_run_that_did_not_converge():
    runs = [run("default", 10.0), run("nested (0, 1, 0) n", 10.5, converged=False)]
    assert sel.choose(runs)["label"] == "nested (0, 1, 0) n"


def test_choose_prefers_a_converged_run_only_within_the_keep_tolerance():
    near = [run("default", 10.0 - sel.KEEP_TOLERANCE / 2), run("nested (0, 1, 0) n", 10.0, converged=False)]
    assert sel.choose(near)["label"] == "default"
    far = [run("default", 10.0 - 2 * sel.KEEP_TOLERANCE), run("nested (0, 1, 0) n", 10.0, converged=False)]
    assert sel.choose(far)["label"] == "nested (0, 1, 0) n"


def test_choose_skips_failed_runs_and_breaks_a_tie_towards_the_earlier_start():
    runs = [run("default", failure="LinAlgError: made up"), run("random 1", 5.0), run("random 2", 5.0)]
    assert sel.choose(runs)["label"] == "random 1"
    assert sel.choose([run("default", failure="LinAlgError: made up")]) is None


def test_a_best_run_that_did_not_converge_is_polished_once_from_its_own_estimates(monkeypatch):
    monkeypatch.setattr(sel, "MAXITER", 1)  # every run stops after one iteration, so the best one is polished
    monkeypatch.setattr(sel, "RANDOM_STARTS", 2)
    y, key = walk(), (1, 1, 1, "t")
    cell = sel.fit_cell(y, *key)
    assert cell["start"] == "default, polished" and cell["starts_tried"] == 4  # default, 2 random, the polish
    unpolished = [sel.run_start(y, key, label, start) for label, start in sel._starts(y, key, [])[0]]
    assert sel.choose(unpolished)["label"] == "default"
    assert cell["llf"] > max(r["llf"] for r in unpolished) + 1e-3
    refit, _ = sel.refit_cell(y, [cell], key)
    assert refit == cell


def test_polish_start_is_only_for_a_best_run_that_did_not_converge():
    params = {"ma.L1": 0.1, "sigma2": 1.0}
    assert sel.polish_start([{**run("default", 5.0), "params": params}]) is None
    label, start = sel.polish_start([{**run("default", 5.0, converged=False), "params": params}])
    assert label == "default, polished" and list(start) == [0.1, 1.0]
    assert sel.polish_start([{**run("default, polished", 5.0, converged=False), "params": params}]) is None  # never twice


def test_a_run_that_ends_at_nan_parameters_is_a_failure_not_the_result():
    # Found by a mutant that padded with 0.1: from this start statsmodels returns NaN parameters
    # without raising, and numpy cannot take the roots of a NaN polynomial. The run must become a
    # failure, never a crash and never the cell's result.
    y, key = walk(400, 2), (1, 2, 1, "t")
    start = np.array([0.0002835863198841778, 0.9218391425873708, 0.1, -0.9603828342962812, 0.0002918197212842129])
    bad = sel.run_start(y, key, "nested (1, 1, 1) t", start)
    assert bad["failure"] is not None and "llf" not in bad
    good = sel.run_start(y, key, "default", None)
    assert sel.choose([bad, good])["label"] == "default"


def test_nests_means_the_same_d_no_more_lags_and_the_same_trend_or_none():
    assert sel.nests((1, 0, 1, "n"), (1, 1, 1, "t"))
    assert sel.nests((1, 1, 1, "n"), (1, 1, 1, "t"))
    assert not sel.nests((1, 0, 1, "t"), (1, 1, 1, "n"))  # a drift is not a special case of none
    assert not sel.nests((1, 1, 1, "t"), (1, 1, 1, "t"))  # not itself
    assert not sel.nests((0, 0, 0, "c"), (1, 1, 1, "c"))  # another d scores other observations
    assert not sel.nests((1, 2, 0, "n"), (1, 1, 1, "n"))


def test_parents_are_one_step_smaller_and_lead_to_every_model_a_cell_nests():
    orders, trends = (0, 1, 2, 3), ("n", "t")
    assert sel.parents((1, 2, 3, "t"), trends, orders) == [(1, 1, 3, "t"), (1, 2, 2, "t"), (1, 2, 3, "n")]
    assert sel.parents((0, 0, 0, "c"), ("c",), orders) == []
    assert sel.parents((1, 2, 0, "t"), trends, (0, 2)) == [(1, 0, 0, "t"), (1, 2, 0, "n")]  # the next smaller order of the grid
    keys = [(1, p, q, t) for t in trends for p in orders for q in orders]
    for key in keys:
        reached, todo = set(), [key]
        while todo:
            for parent in sel.parents(todo.pop(), trends, orders):
                if parent not in reached:
                    reached.add(parent)
                    todo.append(parent)
        assert reached == {k for k in keys if sel.nests(k, key)}, key


def test_a_padded_start_is_exactly_the_nested_model():
    y = walk(400, 2)
    small = sel.run_start(y, (1, 1, 2, "n"), "default", None)
    model = sel._model(y, 1, 2, 2, "n")
    start = dict(zip(model.param_names, sel.padded_start(model, small["params"])))
    assert start == {"ar.L1": small["params"]["ar.L1"], "ar.L2": 0.0, "ma.L1": small["params"]["ma.L1"], "ma.L2": small["params"]["ma.L2"], "sigma2": small["params"]["sigma2"]}
    assert model.loglike(np.array(list(start.values()))) == pytest.approx(small["llf"], abs=1e-9)


def test_a_cell_started_from_a_nested_model_never_ends_below_it(monkeypatch):
    monkeypatch.setattr(sel, "RANDOM_STARTS", 0)  # the nested start alone must be enough
    y = walk(400, 2)
    small = sel.run_start(y, (1, 1, 2, "n"), "default", None)
    alone = sel.fit_cell(y, 1, 2, 2, "n")
    assert alone["llf"] < small["llf"] - 1  # from its default start, ARIMA(2, 1, 2) stops 1.67 below ARIMA(1, 1, 2)
    cell = sel.fit_cell(y, 1, 2, 2, "n", nested=[("nested (1, 1, 2) n", small["params"])])
    assert cell["llf"] >= small["llf"] - sel.KEEP_TOLERANCE
    assert cell["start"].startswith("nested (1, 1, 2) n") and cell["starts_tried"] == 4  # default, padded, padded +/-


def test_with_one_default_start_per_cell_the_same_grid_has_local_optima(monkeypatch):
    # The control: what the several starts are for.
    monkeypatch.setattr(sel, "RANDOM_STARTS", 0)
    y = walk(400, 2)
    cells = [sel.fit_cell(y, 1, p, q, t) for t in ("n", "t") for p in (0, 1, 2) for q in (0, 1, 2)]
    worst = max(gap for _, _, gap in sel.nesting_violations(cells))
    assert worst > 1.5


@pytest.fixture(scope="module")
def seed2_grid():
    """The d = 1 grid with p, q in 0..2 on the seed-2 walk, fitted once for the tests below."""
    y = walk(400, 2)
    return y, sel.fit_grid(y, (0, 1, 2), ((1, ("n", "t")),), workers=8)


def test_no_cell_of_the_grid_scores_below_a_model_it_nests(seed2_grid):
    _, cells = seed2_grid
    assert sel.nesting_violations(cells) == []
    assert sel.nesting_violations(cells, tolerance=0.0) == [] or max(g for *_, g in sel.nesting_violations(cells, tolerance=0.0)) <= sel.NESTING_TOLERANCE
    assert {"default", "nested", "random"} <= {c["start"].split()[0] for c in cells}  # every kind of start wins somewhere


def test_no_cell_is_left_at_the_optimum_of_a_model_it_nests():
    # Seed 7: without perturbed padded starts and the polish stage, ARIMA(1, 1, 2) with a drift kept a
    # zero-padded start from ARIMA(1, 1, 1) with a drift that L-BFGS could not leave, so its llf equals
    # the smaller model's although better points exist (the round-2 review's stall).
    cells = sel.fit_grid(walk(400, 7), (0, 1, 2), ((1, ("n", "t")),), workers=8)
    fitted = [c for c in cells if c["llf"] is not None]
    key = lambda c: (c["d"], c["p"], c["q"], c["trend"])  # noqa: E731
    ties = [(key(s), key(b)) for b in fitted for s in fitted if sel.nests(key(s), key(b)) and abs(b["llf"] - s["llf"]) <= sel.TIE]
    assert ties == []
    by = {key(c): c for c in fitted}
    assert by[(1, 1, 2, "t")]["llf"] > by[(1, 1, 1, "t")]["llf"] + 1e-4  # 2.4e-4 above it with the fix
    assert sel.nesting_violations(cells) == []


def test_the_polish_stage_alone_frees_the_same_stalled_cell(monkeypatch):
    # The same walk with the perturbed starts switched off: only the polish stage (Nelder-Mead from
    # the neighbours' estimates, then L-BFGS) can move ARIMA(1, 1, 2) with a drift off the tie.
    monkeypatch.setattr(sel, "perturbed_starts", lambda *args, **kwargs: [])
    cells = sel.fit_grid(walk(400, 7), (0, 1, 2), ((1, ("n", "t")),), workers=8)
    by = {(c["d"], c["p"], c["q"], c["trend"]): c for c in cells}
    assert by[(1, 1, 2, "t")]["llf"] > by[(1, 1, 1, "t")]["llf"] + 1e-4
    assert by[(1, 1, 2, "t")]["start"].startswith("polished from")


def test_perturbed_starts_change_only_the_new_coefficients_and_stay_valid():
    y = walk(400, 2)
    small = sel.run_start(y, (1, 1, 2, "n"), "default", None)
    model = sel._model(y, 1, 2, 2, "n")
    starts = dict(sel.perturbed_starts(model, small["params"], (1, 2, 2, "n"), "nested (1, 1, 2) n"))
    assert set(starts) == {"+", "-"}
    i = model.param_names.index("ar.L2")
    assert starts["+"][i] * starts["-"][i] < 0  # nonzero, of both signs
    assert np.isfinite(model.loglike(starts["+"])) and np.isfinite(model.loglike(starts["-"]))
    again = dict(sel.perturbed_starts(model, small["params"], (1, 2, 2, "n"), "nested (1, 1, 2) n"))
    assert np.array_equal(again["+"], starts["+"])  # seeded
    trend_step = sel._model(y, 1, 1, 2, "t")
    assert sel.perturbed_starts(trend_step, small["params"], (1, 1, 2, "t"), "nested (1, 1, 2) n") == []  # nothing to perturb


def test_the_readers_pin_the_nesting_tolerance_of_the_selection():
    from arima_forecasting import payloads

    assert payloads.NESTING_TOLERANCE == sel.NESTING_TOLERANCE == 2e-3


def test_nesting_violations_finds_a_bigger_model_with_a_lower_likelihood():
    def cell(p, q, trend, llf):
        return {"d": 1, "p": p, "q": q, "trend": trend, "llf": llf}

    cells = [cell(0, 1, "n", 100.0), cell(1, 1, "n", 99.0), cell(1, 1, "t", 101.0), cell(1, 0, "t", None)]
    assert sel.nesting_violations(cells) == [((1, 0, 1, "n"), (1, 1, 1, "n"), 1.0)]
    assert sel.nesting_violations([cell(0, 1, "n", 100.0), cell(1, 1, "n", 100.0 - sel.NESTING_TOLERANCE / 2)]) == []


def test_refit_cell_reproduces_every_cell_from_its_recorded_start_alone(seed2_grid):
    y, cells = seed2_grid
    memo: dict = {}
    for c in cells:
        refit, _ = sel.refit_cell(y, cells, (c["d"], c["p"], c["q"], c["trend"]), memo)
        if not sel.replayable(cells, (c["d"], c["p"], c["q"], c["trend"])):  # the polish stage: its recorded point is checked
            assert refit["llf"] == pytest.approx(c["llf"], abs=1e-6), (c["p"], c["q"], c["trend"])
        else:
            assert refit == c, (c["p"], c["q"], c["trend"], c["start"])


def test_the_grid_does_not_depend_on_the_number_of_worker_processes():
    y, orders, specs = walk(300, 5), (0, 1), ((1, ("n", "t")),)
    assert sel.fit_grid(y, orders, specs, workers=2) == sel.fit_grid(y, orders, specs, workers=1)


def test_random_starts_are_seeded_by_the_cell_stationary_and_invertible():
    model = sel._model(walk(), 1, 2, 2, "t")
    first, again = sel.random_starts(model, (1, 2, 2, "t")), sel.random_starts(model, (1, 2, 2, "t"))
    assert len(first) == sel.RANDOM_STARTS and all(np.array_equal(a, b) for a, b in zip(first, again))
    other = sel.random_starts(model, (1, 2, 2, "n"))  # another cell, another seed
    assert not np.array_equal(first[0], other[0])
    names = model.param_names
    for start in first:
        ar = [start[names.index(f"ar.L{i}")] for i in (1, 2)]
        ma = [start[names.index(f"ma.L{i}")] for i in (1, 2)]
        assert sel.largest_inverse_root(np.array([1.0, -ar[0], -ar[1]])) < 1
        assert sel.largest_inverse_root(np.array([1.0, ma[0], ma[1]])) < 1


def test_largest_inverse_root_reads_a_zero_top_coefficient_as_a_root_at_zero():
    # A padded start that never moved has a last AR coefficient of exactly 0: statsmodels' arroots
    # divides by that root, this does not.
    assert sel.largest_inverse_root(np.array([1.0, -0.5, 0.0])) == pytest.approx(0.5, abs=1e-15)
    assert sel.largest_inverse_root(np.array([1.0])) is None
    poly = np.array([1.0, -0.3, 0.2])
    assert sel.largest_inverse_root(poly) == pytest.approx(float(np.max(np.abs(1 / (np.roots(poly) ** -1)))), rel=1e-12)


# --- deltas, ranking and near-ties on hand-built cells -----------------------------------------

def c(d, p, q, trend, status, aic, bic=None, k=None):
    return {"d": d, "p": p, "q": q, "trend": trend, "status": status, "aic": aic, "bic": aic if bic is None else bic, "k_params": k}


def test_delta_aic_is_measured_from_the_best_eligible_cell_of_the_same_d_only():
    cells = [
        c(0, 1, 0, "c", "ok", -500.0, k=3),  # d = 0 is far lower, but AIC is never compared across d
        c(1, 0, 1, "t", "ok", -100.0, k=3),
        c(1, 1, 1, "t", "ok", -98.5, k=4),
        c(1, 2, 2, "t", "near_unit_root", -120.0, k=6),  # lower AIC, but not eligible
        c(1, 3, 3, "t", "failed", None, k=8),
        c(2, 0, 1, "n", "near_unit_root", -90.0, k=2),  # d = 2 has no eligible cell
    ]
    sel.add_delta_aic(cells)
    assert [x["delta_aic"] for x in cells] == [0.0, 0.0, 1.5, -20.0, None, None]


def test_ties_are_broken_by_fewer_parameters_then_smaller_p_plus_q_then_smaller_p():
    cells = [
        c(1, 1, 1, "n", "ok", -100.0, k=3),
        c(1, 0, 2, "n", "ok", -100.0, k=3),
        c(1, 2, 0, "n", "ok", -100.0, k=3),
        c(1, 0, 1, "t", "ok", -100.0, k=3),  # same k, but p + q = 1: wins over the three above
    ]
    sel.add_delta_aic(cells)
    assert sel.best_eligible(cells, 1)["trend"] == "t"
    cells.append(c(1, 0, 0, "t", "ok", -100.0, k=2))  # fewer parameters wins over everything
    assert (sel.best_eligible(cells, 1)["p"], sel.best_eligible(cells, 1)["q"]) == (0, 0)
    same_pq = [c(1, 2, 0, "n", "ok", -100.0, k=3), c(1, 1, 1, "n", "ok", -100.0, k=3)]
    assert sel.best_eligible(same_pq, 1)["p"] == 1  # equal k and p + q: smaller p


def test_select_reports_near_ties_bic_the_best_of_each_d_and_the_counts():
    cells = [
        c(0, 0, 1, "c", "ok", -50.0, k=3),
        c(0, 1, 0, "c", "near_unit_root", -200.0, k=3),
        c(1, 0, 0, "n", "ok", -98.0, bic=-95.0, k=1),  # delta exactly 2.0: a near tie
        c(1, 0, 1, "t", "ok", -100.0, bic=-90.0, k=3),  # the AIC choice
        c(1, 1, 1, "t", "ok", -97.9999, bic=-80.0, k=4),  # delta 2.0001: not a near tie
        c(1, 1, 0, "n", "not_converged", -101.0, k=2),
        c(2, 0, 1, "n", "near_unit_root", -99.0, k=2),
    ]
    sel.add_delta_aic(cells)
    s = sel.select(cells, 1, sel.GRID_SPECS)
    assert (s["d_selected"], s["order"], s["trend"], s["aic"], s["k_params"]) == (1, [0, 1, 1], "t", -100.0, 3)
    assert [(x["p"], x["q"], x["trend"], x["delta_aic"]) for x in s["within_2_aic"]] == [(0, 1, "t", 0.0), (0, 0, "n", 2.0)]
    assert (s["bic_choice"]["p"], s["bic_choice"]["q"], s["bic_choice"]["trend"]) == (0, 0, "n")  # BIC prefers the smaller model
    assert s["best_per_d"] == [
        {"d": 0, "cell": {"p": 0, "q": 1, "trend": "c", "aic": -50.0}},
        {"d": 1, "cell": {"p": 0, "q": 1, "trend": "t", "aic": -100.0}},
        {"d": 2, "cell": None},
    ]
    assert s["status_counts"][1] == {"d": 1, "ok": 3, "not_converged": 1, "near_unit_root": 0, "failed": 0}


def test_select_refuses_when_the_chosen_d_has_no_eligible_cell():
    cells = [c(1, 0, 1, "t", "near_unit_root", -100.0, k=3)]
    sel.add_delta_aic(cells)
    with pytest.raises(sel.ModelSearchError, match="no cell with d = 1 has status ok"):
        sel.select(cells, 1, sel.GRID_SPECS)


@pytest.mark.parametrize("d, intercept, expected", [(0, True, "c"), (1, True, "t"), (2, True, None), (1, False, "n"), (0, False, "n")])
def test_pmdarimas_intercept_maps_to_our_trend_code(d, intercept, expected):
    assert sel.pmdarima_trend(d, intercept) == expected


# --- the payload, with a small grid -------------------------------------------------------------

@pytest.fixture(scope="module")
def small_payload():
    return sel.aic_grid_payload(walk(), 1, orders=(0, 1))


def test_the_small_grid_payload_is_valid_complete_and_sorted(small_payload):
    assert validate_aic_grid(small_payload) == []
    cells = small_payload["cells"]
    assert len(cells) == 16  # 4 specs x 2 x 2
    assert [(x["d"], x["trend"], x["p"], x["q"]) for x in cells] == sorted((x["d"], x["trend"], x["p"], x["q"]) for x in cells)
    assert small_payload["grid"] == {"p": [0, 1], "q": [0, 1], "specs": [{"d": 0, "trends": ["c"]}, {"d": 1, "trends": ["n", "t"]}, {"d": 2, "trends": ["n"]}]}
    assert small_payload["selection"]["d_selected"] == 1 and small_payload["selection"]["order"][1] == 1


def test_pmdarima_runs_twice_on_the_same_data_and_its_choice_is_compared_with_the_grid(small_payload):
    check = small_payload["pmdarima_check"]
    assert check["status"] == "ok" and check["version"] == "2.1.1" and check["reason"] is None
    assert [r["label"] for r in check["runs"]] == ["course", "defaults"]
    course = check["runs"][0]
    assert course["settings"]["test"] == "adf" and course["settings"]["start_p"] == 1 and course["settings"]["return_valid_fits"] is True
    for run in check["runs"]:
        first = run["visited"][0]
        assert (first["order"], first["with_intercept"], first["aic"]) == (run["order"], run["with_intercept"], run["aic"])
        assert run["trend"] == sel.pmdarima_trend(run["order"][1], run["with_intercept"])
        assert run["agreement"]["d"] == (run["order"][1] == 1)


def test_the_agreement_compares_the_same_order_and_trend_cell_with_pmdarimas_fit():
    cells = [c(1, 0, 1, "t", "ok", -100.0, k=3), c(1, 0, 1, "n", "ok", -95.0, k=2)]
    selection = {"d_selected": 1, "order": [0, 1, 1], "trend": "t"}
    agreed = sel._agreement([0, 1, 1], "n", -96.0, cells, selection)
    assert agreed == {"d": True, "order": True, "trend": False, "same_order_status": "ok", "aic_gap_same_order": -1.0}
    missing = sel._agreement([2, 2, 1], None, -50.0, cells, selection)
    assert (missing["d"], missing["same_order_status"], missing["aic_gap_same_order"]) == (False, None, None)


def test_a_missing_pmdarima_makes_its_check_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "pmdarima", None)
    found = sel.pmdarima_check(walk(), [], {})
    assert found["status"] == "unavailable" and found["runs"] == [] and found["version"] is None
    assert found["reason"].startswith("ModuleNotFoundError")


def test_a_d_outside_the_grid_is_refused_before_any_fit():
    with pytest.raises(sel.ModelSearchError, match="not in the grid"):
        sel.aic_grid_payload(walk(), 3, orders=(0,))
