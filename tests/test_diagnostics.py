"""Residual diagnostics (src/arima_forecasting/diagnostics.py).

Simulated series with fixed seeds, and small hand-worked cases; no market data.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.arima.model import ARIMA

from arima_forecasting import diagnostics as dg


def walk(n: int = 600, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return math.log(30.0) + np.cumsum(0.0008 + 0.017 * rng.standard_normal(n))


def fit(y: np.ndarray, order: tuple[int, int, int]):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ARIMA(y, order=order).fit()


@pytest.mark.parametrize("d", [0, 1, 2])
def test_the_burn_in_is_d_and_matches_statsmodels_own_rule(d):
    y = walk()
    result = fit(np.diff(y) if d == 0 else (y if d == 1 else np.cumsum(y)), (1, d, 0))
    assert dg.burn_in(result) == d == result.loglikelihood_burn
    # statsmodels' own normality test drops max(loglikelihood_burn, nobs_diffuse) (mlemodel.py:3552);
    # our Jarque-Bera on our burned series must give its exact statistic.
    assert dg.normality(dg.standardized_residuals(result))["statistic"] == pytest.approx(result.test_normality("jarquebera")[0][0], rel=1e-12)
    assert len(dg.standardized_residuals(result)) == len(result.resid) - d


def test_the_burned_residual_is_the_level_not_a_shock():
    # With d = 1 the first one-step forecast has nothing to go on, so the first residual is about the
    # first log price (here ln 30 + a step), and every later one is a daily-size shock.
    y = walk()
    result = fit(y, (0, 1, 1))
    assert result.resid[0] == pytest.approx(y[0], abs=1e-6)
    assert abs(result.resid[0]) > 50 * np.max(np.abs(result.resid[1:]))


def test_ljung_box_uses_p_plus_q_degrees_of_freedom_and_skips_lags_it_cannot_test():
    x = np.random.default_rng(5).standard_normal(500)
    rows = dg.ljung_box(x, model_df=7, lags=(5, 10, 20))
    plain = acorr_ljungbox(x, lags=[5, 10, 20])  # no model_df: same statistic, df = lag
    assert [r["statistic"] for r in rows] == pytest.approx(list(plain["lb_stat"]), rel=1e-12)
    assert [(r["lag"], r["applied"], r["df"]) for r in rows] == [(5, False, None), (10, True, 3), (20, True, 13)]
    assert rows[0]["p_value"] is None
    # At lag == model_df no degrees of freedom are left, so the test is not applied there either.
    assert [(r["lag"], r["applied"], r["df"]) for r in dg.ljung_box(x, model_df=10, lags=(10, 11))] == [(10, False, None), (11, True, 1)]
    for r in rows[1:]:
        assert r["p_value"] == pytest.approx(stats.chi2.sf(r["statistic"], r["lag"] - 7), rel=1e-12)
        assert r["p_value"] != pytest.approx(stats.chi2.sf(r["statistic"], r["lag"]), rel=1e-6)


def test_the_acf_band_is_the_white_noise_band_and_a_negative_spike_is_flagged():
    # Alternating +1, -1 has ACF -1 at lag 1 (well, -(n-1)/n): far below -band, so it must be flagged
    # although the value is negative.
    x = np.array([1.0, -1.0] * 50)
    g = dg.correlogram(x, nlags=3)
    assert g["band"] == dg.Z / math.sqrt(100)
    assert g["rows"][0]["acf"] == pytest.approx(-0.99)
    assert [r["outside"] for r in g["rows"]] == [True, True, True]  # lag 2 is +0.98, lag 3 is -0.97
    assert g["outside_count"] == 3
    quiet = dg.correlogram(np.random.default_rng(3).standard_normal(400), nlags=10)
    assert all(r["outside"] == (abs(r["acf"]) > quiet["band"]) for r in quiet["rows"])
    assert dg.outside(0.1, 0.1) is False and dg.outside(-0.11, 0.1) is True


def garch(n: int, seed: int) -> np.ndarray:
    # GARCH(1, 1): sigma2_t = 0.05 + 0.15 e_{t-1}^2 + 0.8 sigma2_{t-1}, a series with clustering.
    rng = np.random.default_rng(seed)
    e = np.zeros(n)
    s2 = 1.0
    for t in range(1, n):
        s2 = 0.05 + 0.15 * e[t - 1] ** 2 + 0.8 * s2
        e[t] = math.sqrt(s2) * rng.standard_normal()
    return e


def test_arch_lm_finds_clustering_where_there_is_some_and_not_in_white_noise():
    clustered = dg.arch_lm(garch(2000, 1), lags=(5,))[0]
    calm = dg.arch_lm(np.random.default_rng(2).standard_normal(2000), lags=(5,))[0]
    assert clustered["p_value"] < 1e-6 < 0.05 < calm["p_value"]


def test_arch_lm_is_engles_n_r_squared_with_no_degrees_of_freedom_taken_off():
    # By hand with numpy: regress e_t^2 on 1 and e_{t-1}^2 ... e_{t-m}^2 over the n - m usable rows;
    # LM = (n - m) R^2 (ddof 0), on a chi-squared with m degrees of freedom. ddof = p + q would
    # multiply the statistic by (n - m - ddof) / (n - m).
    x = garch(300, 7)
    m = 3
    sq = x**2
    target = sq[m:]
    design = np.column_stack([np.ones(len(target)), *(sq[m - k : len(sq) - k] for k in range(1, m + 1))])
    fitted = design @ np.linalg.lstsq(design, target, rcond=None)[0]
    r2 = 1 - np.sum((target - fitted) ** 2) / np.sum((target - target.mean()) ** 2)
    row = dg.arch_lm(x, lags=(m,))[0]
    assert row["statistic"] == pytest.approx(len(target) * r2, rel=1e-9)
    assert row["p_value"] == pytest.approx(stats.chi2.sf(len(target) * r2, m), rel=1e-9)


def burned_fake(x: np.ndarray, first: float):
    """A stand-in for a fitted result whose first residual, burned, is `first`: huge, made up."""
    from types import SimpleNamespace

    std = np.concatenate([[first], x])
    return SimpleNamespace(loglikelihood_burn=1, nobs_diffuse=0, standardized_forecasts_error=std[None, :], resid=0.01 * std)


def test_every_diagnostic_leaves_the_burned_residual_out():
    # A first residual of 1000 standard deviations would move every statistic if any one diagnostic
    # saw it. Each output must equal that diagnostic on the burned series, and differ from it on the
    # whole series (so the test can tell the two apart).
    x = garch(400, 3)
    whole = np.concatenate([[1000.0], x])
    tests, series = dg.model_diagnostics("aic", burned_fake(x, 1000.0), [1, 1, 1], pd.bdate_range("2015-01-01", periods=len(whole)))
    checks = {
        "ljung_box": (tests["ljung_box"], dg.ljung_box(x, 2), dg.ljung_box(whole, 2)),
        "jarque_bera": (tests["jarque_bera"], dg.normality(x), dg.normality(whole)),
        "arch_lm": (tests["arch_lm"], dg.arch_lm(x), dg.arch_lm(whole)),
        "acf": (series["acf"], dg.correlogram(x), dg.correlogram(whole)),
        "acf_squared": (series["acf_squared"], dg.correlogram(x**2), dg.correlogram(whole**2)),
        "qq": (series["qq"], dg.qq_points(x)[0], dg.qq_points(whole)[0]),
        "max_abs_resid_after_burn": (tests["max_abs_resid_after_burn"], float(np.max(np.abs(0.01 * x))), 10.0),
    }
    for name, (got, burned, unburned) in checks.items():
        assert got == burned, name
        assert got != unburned, name
    assert tests["burned"][0]["resid_std"] == 1000.0 and max(p["sample"] for p in series["qq"]) < 10


def test_jarque_bera_reports_pearson_kurtosis():
    out = dg.normality(np.random.default_rng(4).standard_normal(20000))
    assert out["kurtosis"] == pytest.approx(3.0, abs=0.1) and out["p_value"] > 0.01
    heavy = dg.normality(np.random.default_rng(4).standard_t(3, 20000))
    assert heavy["kurtosis"] > 5 and heavy["p_value"] < 1e-6


def test_qq_points_use_filliben_positions_and_sort_the_sample():
    # Filliben's medians for n = 5: m5 = 0.5^(1/5) = 0.870550563, m1 = 1 - m5 = 0.129449437, and
    # m_i = (i - 0.3175) / (5 + 0.365) for i = 2..4: 0.313887, 0.5, 0.686113. The normal quantiles of
    # those are the theoretical values.
    x = np.array([0.3, -1.2, 2.5, 0.0, -0.4])
    points, t_fit = dg.qq_points(x)
    m5 = 0.5 ** (1 / 5)
    medians = [1 - m5, (2 - 0.3175) / 5.365, 0.5, (4 - 0.3175) / 5.365, m5]
    assert [p["theoretical"] for p in points] == pytest.approx(list(stats.norm.ppf(medians)), rel=1e-9)
    assert [p["sample"] for p in points] == sorted(x.tolist())
    want_t = stats.t.ppf(medians, t_fit["df"], t_fit["loc"], t_fit["scale"])
    assert [p["t_theoretical"] for p in points] == pytest.approx(list(want_t), rel=1e-9)


def test_verdicts_by_hand():
    lb = [{"applied": False, "p_value": None}, {"applied": True, "p_value": 0.2}, {"applied": True, "p_value": 0.04}]
    jb = {"p_value": 0.5}
    arch = [{"p_value": 0.06}]
    assert dg.verdicts(lb, jb, arch) == {"serial_correlation": "found", "normality": "not_rejected", "arch": "not_found"}
    assert dg.verdicts(lb[:2], {"p_value": 0.01}, [{"p_value": 0.01}])["normality"] == "rejected"
    assert dg.verdicts(lb[:1], jb, arch)["serial_correlation"] == "not_tested"
    assert dg.verdicts(lb[:2], jb, arch)["serial_correlation"] == "not_found"
    # Any one rejecting row is enough, for ARCH-LM as for Ljung-Box (no correction for several lags).
    assert dg.verdicts(lb, jb, [{"p_value": 0.2}, {"p_value": 0.01}])["arch"] == "found"
    assert dg.verdicts(lb, jb, [{"p_value": 0.2}, {"p_value": 0.06}])["arch"] == "not_found"


def test_model_diagnostics_shapes_and_the_dropped_residual():
    y = walk(300)
    result = fit(y, (1, 1, 1))
    dates = pd.bdate_range("2015-01-01", periods=len(y))
    tests, series = dg.model_diagnostics("aic", result, [1, 1, 1], dates)
    assert tests["burn_excluded"] == 1 and tests["n"] == 299 == len(series["rows"]) == len(series["qq"])
    assert tests["burned"] == [{"date": "2015-01-01", "resid": float(result.resid[0]), "resid_std": float(result.standardized_forecasts_error[0, 0])}]
    assert series["rows"][0]["date"] == "2015-01-02"
    assert [r["model_df"] for r in tests["ljung_box"]] == [2, 2, 2]
    assert tests["acf_outside_count"] == series["acf"]["outside_count"]


def test_the_readers_pin_the_settings_the_exporter_writes():
    # payloads.py (and contract.fit.ts, whose test holds the same literals) keep the residual tests'
    # settings themselves and refuse a file that states others. They must be what this module runs
    # and writes: a pin that drifted from diagnostics.py would refuse every real export.
    from arima_forecasting import payloads

    assert payloads.ALPHA == dg.ALPHA == 0.05
    assert list(payloads.LJUNG_BOX_LAGS) == list(dg.LJUNG_BOX_LAGS) == [5, 10, 20]
    assert list(payloads.ARCH_LM_LAGS) == list(dg.ARCH_LM_LAGS) == [5, 10]
    assert payloads.NLAGS == dg.NLAGS == 50
    # The ddof het_arch is given is in test_arch_lm_is_engles_n_r_squared...; the file states it too.
    result = fit(walk(), (1, 1, 1))
    written = {"primary": "aic", "models": [{"id": "aic", "order": [1, 1, 1]}]}
    dg.residual_payloads(written, {"aic": result}, pd.bdate_range("2015-01-01", periods=len(walk())))
    settings = written["diagnostic_settings"]
    assert (settings["alpha"], settings["ljung_box_lags"], settings["arch_lm_lags"], settings["arch_lm_ddof"], settings["nlags"]) == (
        payloads.ALPHA,
        list(payloads.LJUNG_BOX_LAGS),
        list(payloads.ARCH_LM_LAGS),
        payloads.ARCH_LM_DDOF,
        payloads.NLAGS,
    )
