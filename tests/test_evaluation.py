"""The scores (src/arima_forecasting/evaluation.py): metrics, Diebold-Mariano with the Harvey-Leybourne-
Newbold correction, interval coverage with Kupiec's test, the verdicts, and the course's module-10
failure.

Made-up numbers only. Every expected value is worked by hand in the comments, or taken from scipy
(an implementation independent of the code under test), never from evaluation.py itself.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from arima_forecasting import evaluation, payloads
from arima_forecasting.evaluation import coverage, coverage_verdict, dm_test, dm_verdict, evaluation_payload, hln_factor, kupiec, mae, mape_pct, random_walk_forecasts, rmse
from arima_forecasting.forecasting import Spec, forecast_payloads
from arima_forecasting.payloads import validate_evaluation, validate_forecast_evaluation

from test_forecasting import COURSE, DRIFT, fit_entry, simulated, table_for


def test_the_pins_equal_the_producer_constants():
    assert evaluation.ALPHA == payloads.ALPHA
    assert evaluation.DM_VERDICTS == payloads.DM_VERDICTS
    assert evaluation.COVERAGE_VERDICTS == payloads.COVERAGE_VERDICTS
    assert evaluation.DISTRIBUTIONS == payloads.DISTRIBUTIONS
    assert evaluation.DM_LOSSES == payloads.DM_LOSSES
    assert evaluation.SAME_TOLERANCE == payloads.DM_SETTINGS["same_tolerance"] == 1e-9
    assert evaluation.METHOD_LABELS == payloads.METHOD_LABELS


# --- metrics --------------------------------------------------------------------------------------------


def test_the_metrics_by_hand():
    # Errors 100 - 105, 110 - 100, 90 - 90 = -5, 10, 0. RMSE = sqrt((25 + 100 + 0) / 3) = sqrt(41.67)
    # = 6.454972243679028; MAE = 15 / 3 = 5; MAPE = 100 (5 / 100 + 10 / 110 + 0) / 3 = 4.696969696969697.
    actual, forecast = [100.0, 110.0, 90.0], [105.0, 100.0, 90.0]
    assert rmse(actual, forecast) == pytest.approx(6.454972243679028, rel=1e-15)
    assert mae(actual, forecast) == pytest.approx(5.0, rel=1e-15)
    assert mape_pct(actual, forecast) == pytest.approx(4.696969696969697, rel=1e-15)
    with pytest.raises(ValueError, match="same length"):
        rmse([1.0, 2.0], [1.0])
    with pytest.raises(ValueError, match="one is 0"):
        mape_pct([0.0, 1.0], [1.0, 1.0])


def test_the_course_mape_is_nan_on_a_one_column_frame_and_ours_refuses_it():
    # The course's module 10: forecast_series = np.exp(forecast) is a Series; test_data_actual =
    # np.exp(test_data) is a one-column DataFrame (yfinance 1.7.0's Close). Series - DataFrame lines
    # the Series' index up against the DataFrame's column labels, not its rows: every cell is NaN.
    dates = pd.bdate_range("2023-02-06", periods=3)
    test_data_actual = pd.DataFrame({"AAPL": [100.0, 110.0, 90.0]}, index=dates)
    forecast_series = pd.Series([105.0, 100.0, 90.0], index=dates)
    course_mape = np.mean(np.abs(forecast_series - test_data_actual) / np.abs(test_data_actual)) * 100
    assert math.isnan(course_mape)
    # Ours takes one-dimensional numbers only: the frame is refused, its column gives the hand value.
    with pytest.raises(ValueError, match="one-dimensional"):
        mape_pct(test_data_actual, forecast_series)
    assert mape_pct(test_data_actual["AAPL"], forecast_series) == pytest.approx(4.696969696969697, rel=1e-15)


def test_the_random_walk_forecasts_of_a_window_by_hand():
    # Origin 0.5 (the day before the window), actuals 1, 2, 3: one step ahead the random walk says
    # 0.5, 1, 2; static, 0.5 every day. The dollars follow the same rule.
    window = {"origin": {"log_close": 0.5, "close_usd": 5.0}, "rows": [{"actual_log": v, "actual_usd": 10.0 * v} for v in (1.0, 2.0, 3.0)]}
    one_log, one_usd = random_walk_forecasts(window, "one_step")
    assert list(one_log) == [0.5, 1.0, 2.0] and list(one_usd) == [5.0, 10.0, 20.0]
    static_log, static_usd = random_walk_forecasts(window, "multi_step")
    assert list(static_log) == [0.5, 0.5, 0.5] and list(static_usd) == [5.0, 5.0, 5.0]


# --- Diebold-Mariano with the HLN correction ----------------------------------------------------------------

E_MODEL = [0.01, -0.02, 0.03, 0.00, -0.01]
E_RW = [0.02, -0.01, 0.01, 0.02, -0.03]


def test_dm_by_hand_on_made_up_errors():
    # Squared loss: d = e_model^2 - e_rw^2 = 0.0001 - 0.0004, 0.0004 - 0.0001, 0.0009 - 0.0001,
    # 0 - 0.0004, 0.0001 - 0.0009 = -0.0003, 0.0003, 0.0008, -0.0004, -0.0008. Mean -0.0004 / 5 = -8e-5.
    # Deviations -2.2e-4, 3.8e-4, 8.8e-4, -3.2e-4, -7.2e-4; their squares sum to 1.588e-6, so
    # gamma_0 = 1.588e-6 / 5 = 3.176e-7 (divisor n). DM = -8e-5 / sqrt(3.176e-7 / 5) = -0.3174203325...
    # HLN (1997): DM* = DM sqrt((n + 1 - 2h + h (h - 1) / n) / n) = DM sqrt(4 / 5) with n = 5, h = 1,
    # compared with a Student t on n - 1 = 4 df, two-sided.
    row = dm_test(E_MODEL, E_RW, "squared")
    assert row["mean_diff"] == pytest.approx(-8e-5, rel=1e-12)
    assert row["var_diff"] == pytest.approx(3.176e-7, rel=1e-12)
    assert row["statistic"] == pytest.approx(-8e-5 / math.sqrt(3.176e-7 / 5), rel=1e-12)
    assert row["statistic"] == pytest.approx(-0.3174203325, rel=1e-9)
    assert row["hln_factor"] == pytest.approx(math.sqrt(0.8), rel=1e-15)
    assert row["statistic_hln"] == pytest.approx(row["statistic"] * math.sqrt(0.8), rel=1e-15)
    assert row["df"] == 4
    assert row["p_value"] == pytest.approx(2 * stats.t.sf(abs(row["statistic_hln"]), 4), rel=1e-12)
    assert row["verdict"] == "no_difference"
    # Absolute loss: d = 0.01 - 0.02, 0.02 - 0.01, 0.03 - 0.01, 0 - 0.02, 0.01 - 0.03 = -0.01, 0.01,
    # 0.02, -0.02, -0.02: mean -0.004, gamma_0 = (0.006^2 + 0.014^2 + 0.024^2 + 0.016^2 + 0.016^2) / 5 = 2.64e-4.
    row = dm_test(E_MODEL, E_RW, "absolute")
    assert row["mean_diff"] == pytest.approx(-0.004, rel=1e-12)
    assert row["var_diff"] == pytest.approx(2.64e-4, rel=1e-12)


def test_dm_with_the_hln_correction_is_the_one_sample_t_test_at_h_1():
    # At h = 1, gamma_0 has divisor n and the HLN factor is sqrt((n - 1) / n), so DM* = mean(d) /
    # sqrt(s^2 / n) with s^2 the variance of d with divisor n - 1: the one-sample t statistic, on n - 1
    # df. scipy's ttest_1samp is an independent implementation of exactly that.
    rng = np.random.default_rng(3)
    e_model, e_rw = 0.012 * rng.standard_normal(227), 0.012 * rng.standard_normal(227)
    for kind, loss in (("squared", np.square), ("absolute", np.abs)):
        row = dm_test(e_model, e_rw, kind)
        reference = stats.ttest_1samp(loss(e_model) - loss(e_rw), 0.0)
        assert row["statistic_hln"] == pytest.approx(reference.statistic, rel=1e-12)
        assert row["p_value"] == pytest.approx(reference.pvalue, rel=1e-10)


def test_the_hln_factor_is_the_published_formula():
    # sqrt((n + 1 - 2h + h (h - 1) / n) / n): n = 10, h = 2 gives sqrt(7.2 / 10) = sqrt(0.72); h = 1 gives sqrt(9 / 10).
    assert hln_factor(10, 2) == pytest.approx(math.sqrt(0.72), rel=1e-15)
    assert hln_factor(10, 1) == pytest.approx(math.sqrt(0.9), rel=1e-15)
    with pytest.raises(ValueError, match="h = 1"):
        dm_test(E_MODEL, E_RW, "squared", h=2)


def test_the_dm_verdict_at_its_boundary():
    assert dm_verdict(0.05, -1.0) == "no_difference"  # p equal to alpha is not below it
    assert dm_verdict(0.049999999999999996, -1.0) == "beats_rw"
    assert dm_verdict(0.049999999999999996, 1.0) == "worse_than_rw"
    assert dm_verdict(0.01, 0.0) == "no_difference"


def test_forecasts_that_are_the_random_walks_are_not_tested():
    # Forecasts within same_tolerance (1e-9 log points) of the random walk's leave a loss differential
    # of 0 or rounding noise: no statistic, verdict "same_as_rw". The boundary is inclusive.
    e_rw = np.array(E_RW)
    for gap in (0.0, 1e-9):
        row = dm_test(e_rw - gap, e_rw, "squared", max_forecast_gap=gap)
        assert (row["verdict"], row["statistic"], row["statistic_hln"], row["p_value"]) == ("same_as_rw", None, None, None)
        assert row["hln_factor"] == pytest.approx(math.sqrt(0.8)) and row["df"] == 4
    # One ulp above the tolerance, the test runs.
    above = math.nextafter(1e-9, 1.0)
    row = dm_test(e_rw - above, e_rw, "squared", max_forecast_gap=above)
    assert row["verdict"] != "same_as_rw" and row["p_value"] is not None
    # Forecasts that differ but leave a constant loss differential have no variance: refused.
    with pytest.raises(ValueError, match="constant"):
        dm_test([0.1, 0.1], [-0.1, -0.1], "squared", max_forecast_gap=0.2)
    with pytest.raises(ValueError, match="at least two"):
        dm_test([0.1], [0.2], "squared")


# --- coverage and Kupiec ----------------------------------------------------------------------------------------


def test_kupiec_by_hand():
    # 8 of 10 inside at level 0.8: the observed rate is the level, LR 0, p 1.
    assert kupiec(10, 8, 0.8) == (0.0, 1.0)
    # 10 of 10: LR = -2 (10 ln 0.8 - 10 ln 1) = -20 ln 0.8 = 4.462871026284195.
    # 5 of 10: LR = -2 (5 ln 0.8 + 5 ln 0.2 - 10 ln 0.5) = -10 ln 0.64, the same number.
    for inside in (10, 5):
        lr, p = kupiec(10, inside, 0.8)
        assert lr == pytest.approx(-20 * math.log(0.8), rel=1e-12)
        assert p == pytest.approx(stats.chi2.sf(-20 * math.log(0.8), 1), rel=1e-12)
    with pytest.raises(ValueError):
        kupiec(10, 11, 0.8)


def test_the_coverage_verdict_at_its_boundary():
    assert coverage_verdict("multi_step", None, 1.0, 0.8) == "not_tested"
    assert coverage_verdict("one_step", 0.05, 1.0, 0.8) == "consistent"  # p equal to alpha: not rejected
    assert coverage_verdict("one_step", 0.049999999999999996, 1.0, 0.8) == "too_wide"
    assert coverage_verdict("one_step", 0.049999999999999996, 0.5, 0.8) == "too_narrow"


def test_coverage_counts_a_bound_as_inside():
    # mean_log 0, sd_log 1, multiplier 2: the interval is [-2, 2]. Actuals -2 and 2 are on its bounds
    # and count; -2.000000000000001 and 3 do not. So 3 of 5 are inside.
    rows = [{"mean_log": 0.0, "sd_log": 1.0, "actual_log": v} for v in (-2.0, 2.0, 0.5, -2.000000000000001, 3.0)]
    row = coverage(rows, "one_step", "normal", 0.8, 2.0)
    assert (row["n"], row["inside"], row["rate"]) == (5, 3, 0.6)
    assert row["lr"] == pytest.approx(kupiec(5, 3, 0.8)[0]) and row["verdict"] == coverage_verdict("one_step", row["p_value"], 0.6, 0.8)
    static = coverage(rows, "multi_step", "t", 0.95, 2.0)
    assert (static["inside"], static["lr"], static["p_value"], static["verdict"]) == (3, None, None, "not_tested")


# --- the payload ----------------------------------------------------------------------------------------------------

RANDOM_WALK_MODEL = Spec((0, 1, 0), "n", np.array([0.0003]))  # ARIMA(0, 1, 0) without a drift: the random walk


@pytest.fixture(scope="module")
def scored():
    y = simulated(330)
    table = table_for(y, 250, 30)
    fit = {"n_train": 250, "models": [fit_entry("aic", DRIFT), fit_entry("bic", RANDOM_WALK_MODEL), fit_entry("course", COURSE)]}
    residuals = {f"residuals_{m}": {"t_fit": {"df": df}} for m, df in (("aic", 4.0), ("bic", 3.5), ("course", 6.0))}
    forecasts = forecast_payloads(table, fit, residuals)
    return forecasts, evaluation_payload(forecasts, fit), y


def test_the_evaluation_passes_both_python_readers(scored):
    forecasts, data, _ = scored
    assert validate_evaluation(data) == []
    assert validate_forecast_evaluation(data, forecasts) == []


def test_the_random_walk_and_the_ratios(scored):
    forecasts, data, y = scored
    rw = {(r["kind"], r["window"]): r for r in data["random_walk"]}
    # Static on the test window: the origin y[249] every day; one step: y[249..278] for y[250..279].
    assert rw[("multi_step", "test")]["log"]["mae"] == pytest.approx(np.mean(np.abs(y[250:280] - y[249])), rel=1e-12)
    assert rw[("one_step", "test")]["log"]["mae"] == pytest.approx(np.mean(np.abs(y[250:280] - y[249:279])), rel=1e-12)
    assert rw[("one_step", "oos")]["log"]["rmse"] == pytest.approx(np.sqrt(np.mean((y[280:] - y[279:-1]) ** 2)), rel=1e-12)
    for row in data["metrics"]:
        base = rw[(evaluation.KINDS[row["method"]], row["window"])]
        assert row["ratio_to_rw"]["log"]["rmse"] == row["log"]["rmse"] / base["log"]["rmse"]
        assert row["ratio_to_rw"]["usd_mean"]["mape_pct"] == row["usd_mean"]["mape_pct"] / base["usd"]["mape_pct"]


def test_a_random_walk_model_is_the_random_walk_and_is_not_tested(scored):
    _, data, _ = scored
    # bic is ARIMA(0, 1, 0) without a drift here: its one-step forecasts are the random walk's.
    walk = [r for r in data["metrics"] if (r["model_id"], r["method"]) == ("bic", "walk_forward")]
    assert all(r["ratio_to_rw"]["log"]["rmse"] == pytest.approx(1.0, abs=1e-12) for r in walk)
    rows = [r for r in data["dm"] if r["model_id"] == "bic"]
    assert len(rows) == 4 and all(r["verdict"] == "same_as_rw" and r["max_forecast_gap"] <= 1e-9 and r["p_value"] is None for r in rows)
    others = [r for r in data["dm"] if r["model_id"] != "bic"]
    assert all(r["verdict"] in ("beats_rw", "no_difference", "worse_than_rw") and r["max_forecast_gap"] > 1e-9 for r in others)


def test_the_back_transform_gap_is_mean_over_median(scored):
    forecasts, data, _ = scored
    for row in data["metrics"]:
        window = next(w for w in forecasts[f"forecast_{row['model_id']}_{row['method']}"]["windows"] if w["id"] == row["window"])
        gaps = [100 * (r["mean_usd"] / r["median_usd"] - 1) for r in window["rows"]]
        assert row["back_transform"]["max_pct"] == pytest.approx(max(gaps), rel=1e-9)
        assert row["back_transform"]["mean_pct"] == pytest.approx(np.mean(gaps), rel=1e-9)
