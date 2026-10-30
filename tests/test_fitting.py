"""The three fits and how each is described (src/arima_forecasting/fitting.py).

Every series here is simulated with a fixed seed; no market data is used. The hand-worked values
(roots, pairs) are derived in the comments, never from the code under test.
"""

from __future__ import annotations

import math
import warnings
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import stats
from statsmodels.tsa.arima.model import ARIMA

from arima_forecasting import fitting, selection
from arima_forecasting.diagnostics import residual_payloads
from arima_forecasting.payloads import validate_fit, validate_residuals


def random_walk(n: int = 400, seed: int = 20261029, drift: float = 0.0008) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return math.log(30.0) + np.cumsum(drift + 0.017 * rng.standard_normal(n))


def test_the_drift_is_renamed_and_nothing_else_is():
    assert fitting.parameter_name("x1", "t") == "drift"
    assert fitting.parameter_name("x1", "n") == "x1"  # only trend 't' puts the drift in x1
    for name in ("const", "ar.L1", "ma.L2", "sigma2"):
        assert fitting.parameter_name(name, "t") == name


def test_inverse_roots_by_hand():
    # 1 - 0.5L: the root of the lag polynomial is L = 2, its inverse 0.5.
    assert fitting.inverse_roots(np.array([1.0, -0.5])) == [{"re": 0.5, "im": 0.0, "modulus": 0.5}]
    # 1 + 0.25L^2: inverse roots solve z^2 + 0.25 = 0, so z = +-0.5i, both of modulus 0.5.
    roots = fitting.inverse_roots(np.array([1.0, 0.0, 0.25]))
    assert sorted(r["im"] for r in roots) == pytest.approx([-0.5, 0.5])
    assert [r["re"] for r in roots] + [r["modulus"] for r in roots] == pytest.approx([0.0, 0.0, 0.5, 0.5])
    # (1 - 0.9L)(1 - 0.2L) = 1 - 1.1L + 0.18L^2: inverse roots 0.9 and 0.2, largest first.
    assert [r["modulus"] for r in fitting.inverse_roots(np.array([1.0, -1.1, 0.18]))] == pytest.approx([0.9, 0.2])
    assert fitting.inverse_roots(np.array([1.0])) == []


def root(re: float, im: float = 0.0) -> dict[str, float]:
    return {"re": re, "im": im, "modulus": math.hypot(re, im)}


def test_cancelling_pairs_follow_the_stated_rule():
    # 0.5 and 0.55 are 0.05 apart: one pair. 0.5 and 0.7 are 0.2 apart: none.
    assert fitting.cancelling_pairs([root(0.5)], [root(0.55)]) == [{"ar": 0, "ma": 0, "distance": pytest.approx(0.05)}]
    assert fitting.cancelling_pairs([root(0.5)], [root(0.7)]) == []
    # One to one: MA 0.51 is 0.01 from AR 0.5 and 0.02 from AR 0.53. One pair either way, so the
    # least total distance decides: AR 0.5, and AR 0.53 stays unpaired although it is within 0.1 too.
    pairs = fitting.cancelling_pairs([root(0.53), root(0.5)], [root(0.51)])
    assert [(p["ar"], p["ma"]) for p in pairs] == [(1, 0)]
    # Complex roots: -0.8 +- 0.4i against -0.75 +- 0.42i, each conjugate pairs with its own.
    ar = [root(-0.8, 0.4), root(-0.8, -0.4)]
    ma = [root(-0.75, -0.42), root(-0.75, 0.42)]
    assert sorted((p["ar"], p["ma"]) for p in fitting.cancelling_pairs(ar, ma)) == [(0, 1), (1, 0)]
    # The threshold is inclusive and adjustable.
    assert fitting.cancelling_pairs([root(0.5)], [root(0.75)], distance=0.25) != []
    assert fitting.cancelling_pairs([root(0.5)], [root(0.75)], distance=0.24) == []
    assert fitting.cancelling_pairs([], [root(0.5)]) == fitting.cancelling_pairs([root(0.5)], []) == []


def test_cancelling_pairs_are_a_maximum_matching_not_closest_first():
    # AR 0.5, 0.6 and MA 0.51, 0.41. The distances: 0.5-0.51 0.01, 0.5-0.41 0.09, 0.6-0.51 0.09,
    # 0.6-0.41 0.19. Closest first takes 0.5-0.51 and is left with 0.6-0.41, past 0.1: one pair. Two
    # pairs within 0.1 exist, 0.5-0.41 and 0.6-0.51, so the rule gives those, listed by AR index.
    pairs = fitting.cancelling_pairs([root(0.5), root(0.6)], [root(0.51), root(0.41)])
    assert [(p["ar"], p["ma"]) for p in pairs] == [(0, 1), (1, 0)]
    assert [p["distance"] for p in pairs] == pytest.approx([0.09, 0.09])
    # With as many pairs either way, the least total distance wins: AR 0.5, 0.6 against MA 0.52,
    # 0.58 pairs 0.5-0.52 and 0.6-0.58 (0.04 in all), not 0.5-0.58 and 0.6-0.52 (0.16).
    pairs = fitting.cancelling_pairs([root(0.6), root(0.5)], [root(0.58), root(0.52)])
    assert [(p["ar"], p["ma"]) for p in pairs] == [(0, 0), (1, 1)]


def test_a_single_eligible_pair_at_distance_zero_is_found():
    # AR 0.5 against MA 0.9 (0.4 apart, too far) and MA 0.5 (0 apart): one pair, (0, 1). The only
    # eligible distance is 0, so the cost given to a pair past the threshold must still be above it.
    assert fitting.cancelling_pairs([root(0.5)], [root(0.9), root(0.5)]) == [{"ar": 0, "ma": 1, "distance": 0.0}]


def test_a_pair_exactly_cancel_distance_apart_is_a_pair():
    # 0.32 - 0.22 is exactly the double 0.1 = CANCEL_DISTANCE: the threshold is inclusive.
    assert abs(complex(0.32, 0.0) - complex(0.22, 0.0)) == fitting.CANCEL_DISTANCE == 0.1
    assert fitting.cancelling_pairs([root(0.32)], [root(0.22)]) == [{"ar": 0, "ma": 0, "distance": 0.1}]
    assert fitting.cancelling_pairs([root(0.32, 0.4), root(0.32, -0.4)], [root(0.22, -0.4), root(0.22, 0.4)]) == [{"ar": 0, "ma": 1, "distance": 0.1}, {"ar": 1, "ma": 0, "distance": 0.1}]


def test_the_readers_pin_the_llf_tolerance_and_cancel_distance_of_the_fits():
    from arima_forecasting import payloads

    assert payloads.LLF_TOLERANCE == fitting.LLF_TOLERANCE == 1e-6
    assert payloads.CANCEL_DISTANCE == fitting.CANCEL_DISTANCE == 0.1


def fitted(y: np.ndarray, order=(1, 1, 1), trend="t"):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return selection._model(y, order[1], order[0], order[2], trend).fit(method="statespace", method_kwargs={"method": "lbfgs", "maxiter": 200})


def test_parameter_rows_define_z_p_and_the_interval_and_agree_with_statsmodels():
    result = fitted(random_walk())
    rows = fitting.parameter_rows(result, "t")
    assert [r["name"] for r in rows] == ["drift", "ar.L1", "ma.L1", "sigma2"]
    assert [r["library_name"] for r in rows] == ["x1", "ar.L1", "ma.L1", "sigma2"]
    for row, se, z, p in zip(rows, result.bse, result.zvalues, result.pvalues, strict=True):
        assert row["std_err"] == se
        assert row["ci_high"] - row["value"] == pytest.approx(fitting.Z95 * row["std_err"])
        if row["name"] == "sigma2":
            # A variance's null value 0 is on the boundary: no z, no p-value (statsmodels prints one).
            assert (row["z"], row["p_value"]) == (None, None) and np.isfinite(z)
            continue
        assert row["z"] == row["value"] / row["std_err"]
        assert row["z"] == pytest.approx(z, rel=1e-12)
        assert row["p_value"] == pytest.approx(p, rel=1e-9, abs=1e-300)


def test_inference_is_null_when_the_standard_error_is_not_usable():
    fake = SimpleNamespace(model=SimpleNamespace(param_names=["ar.L1", "sigma2"]), params=np.array([0.3, 1.0]), bse=np.array([np.nan, 0.0]))
    for row in fitting.parameter_rows(fake, "n"):
        assert [row[k] for k in ("std_err", "z", "p_value", "ci_low", "ci_high")] == [None] * 5


def grid_cell(y: np.ndarray, d: int, p: int, q: int, trend: str) -> dict:
    # A single run from the default start stops a little short here (a restart from its estimates
    # gains 5.4e-6 in llf, more than LLF_TOLERANCE), so the cell takes the restarted run, as the
    # grid's ", polished" and polish stage do.
    first = selection.run_start(y, (d, p, q, trend), "default", None)
    run = selection.run_start(y, (d, p, q, trend), "default, polished", np.array(list(first["params"].values())))
    return {"d": d, "p": p, "q": q, "trend": trend, "llf": run["llf"], "params": run["params"]}


def test_a_grid_cell_refits_to_the_grid_llf_and_a_wrong_record_is_refused():
    y = random_walk()
    cell = grid_cell(y, 1, 1, 1, "t")
    result, _ = fitting.fit_grid_cell(y, cell)
    assert abs(result.llf - cell["llf"]) <= fitting.LLF_TOLERANCE
    with pytest.raises(fitting.GridMismatch, match="gap"):
        fitting.fit_grid_cell(y, {**cell, "llf": cell["llf"] + 1e-3})


@pytest.fixture(scope="module")
def walk_cell():
    y = random_walk()
    cell = grid_cell(y, 1, 1, 1, "t")
    return y, cell, fitting.fit_grid_cell(y, cell)[0].llf


@pytest.mark.parametrize("factor", [2.0, -2.0, 0.5, -0.5])
def test_the_llf_guard_refuses_a_gap_past_the_tolerance_on_either_side_and_only_then(walk_cell, factor):
    # The refit from the same recorded estimates is deterministic, so a record moved by `gap` from
    # the refit's own llf gives exactly that gap. Twice the documented tolerance, 1e-6, either way
    # must stop the fit, half of it either way must not: that pins 1e-6 (not 1e-4 or 1e-7) and both
    # signs. The gaps are written from 1e-6 itself, not from the constant, so changing it fails here.
    y, cell, llf = walk_cell
    gap = factor * 1e-6
    record = {**cell, "llf": llf - gap}  # refit llf - record = gap
    if abs(factor) > 1:
        with pytest.raises(fitting.GridMismatch, match="gap"):
            fitting.fit_grid_cell(y, record)
    else:
        result, _ = fitting.fit_grid_cell(y, record)
        assert result.llf - record["llf"] == pytest.approx(gap, rel=1e-6)


def test_the_course_refit_drops_the_drift_at_d_1():
    result, _ = fitting.course_refit(random_walk(), [0, 1, 1])
    assert result.model.trend == "n"
    assert list(result.model.param_names) == ["ma.L1", "sigma2"]


@pytest.fixture(scope="module")
def small_grid():
    # A real aic_grid payload on a simulated series, with a 2 x 2 grid and a stand-in pmdarima run so
    # course_track has a training-only order to compare with.
    y = random_walk(500)
    run = {"label": "course", "order": [0, 1, 1], "with_intercept": True, "trend": "t"}
    grid = selection.aic_grid_payload(y, 1, orders=(0, 1), specs=((1, ("n", "t")),), cross_check=lambda *_: {"status": "ok", "reason": None, "version": "x", "runs": [run]})
    return y, grid


def test_fit_models_fits_the_aic_bic_and_course_models(small_grid):
    y, grid = small_grid
    course = np.concatenate([y, random_walk(60, seed=7) - math.log(30.0) + y[-1]])
    fit, results = fitting.fit_models(y, course, grid)
    assert [m["id"] for m in fit["models"]] == ["aic", "bic", "course"] == list(results)
    s = grid["selection"]
    assert (fit["models"][0]["order"], fit["models"][0]["trend"]) == (s["order"], s["trend"])
    assert (fit["models"][1]["order"][0], fit["models"][1]["order"][2], fit["models"][1]["trend"]) == (s["bic_choice"]["p"], s["bic_choice"]["q"], s["bic_choice"]["trend"])
    for m in fit["models"][:2]:
        assert abs(m["llf_gap"]) <= fitting.LLF_TOLERANCE
    track = fit["course_track"]
    assert track["test_rows_seen"] == 60 and track["n_course"] == 560
    assert track["refit_trend"] == fit["models"][2]["trend"] == "n"
    assert track["full_series"]["order"] == fit["models"][2]["order"]
    dd = track["drift_dropped"]
    assert dd["aic_gap"] == dd["aic_without_drift"] - dd["aic_with_drift"]
    # The drift put back is the drifted fit's own row: about the mean daily change of the training
    # walk (simulated with 0.0008), with a positive standard error and its two-sided p-value.
    assert dd["drift"] != 0 and dd["drift_std_err"] > 0
    assert abs(dd["drift"] - np.mean(np.diff(y))) < 3 * dd["drift_std_err"]
    assert dd["drift_p_value"] == pytest.approx(2 * stats.norm.sf(abs(dd["drift"] / dd["drift_std_err"])), rel=1e-9)
    series = residual_payloads(fit, results, __import__("pandas").bdate_range("2015-01-01", periods=len(y)))
    assert validate_fit(fit) == []
    for model_id in ("aic", "bic", "course"):
        assert validate_residuals(series[f"residuals_{model_id}"], model_id) == []


@pytest.mark.parametrize(("intercept", "same"), [(True, True), (False, False)])
def test_same_order_compares_the_intercept_too(monkeypatch, intercept, same):
    # The training-only search chose (0, 1, 1) with an intercept. A full-series search with the same
    # order is "the same" only if it chose the intercept too.
    y = random_walk(300)
    stand_in = {"order": [0, 1, 1], "with_intercept": intercept, "trend": "t" if intercept else "n", "aic": -1.0, "nobs": 330, "params": [], "warnings": [], "pmdarima_version": "x"}
    monkeypatch.setattr(fitting, "auto_arima_full", lambda course: dict(stand_in))
    grid = {"pmdarima_check": {"runs": [{"label": "course", "order": [0, 1, 1], "with_intercept": True, "trend": "t"}]}}
    track, _ = fitting.course_track(y, np.concatenate([y, y[-1] + np.zeros(30)]), grid)
    assert track["train_only"]["order"] == track["full_series"]["order"]
    assert track["same_order"] is same


def test_fit_models_refuses_a_course_series_that_does_not_extend_the_training_one(small_grid):
    y, grid = small_grid
    with pytest.raises(ValueError, match="must start with the training series"):
        fitting.fit_models(y, np.concatenate([y[1:], y[:5]]), grid)


def test_the_course_model_is_the_plain_statsmodels_default_fit():
    # The course's call, ARIMA(train, order=order).fit(), must give the very numbers course_refit does.
    y = random_walk()
    ours, _ = fitting.course_refit(y, [1, 1, 0])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plain = ARIMA(y, order=(1, 1, 0)).fit()
    assert ours.llf == plain.llf and list(ours.params) == list(plain.params)
