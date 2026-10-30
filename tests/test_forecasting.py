"""The forecasts (src/arima_forecasting/forecasting.py): static, walk-forward, the expanding refit and
the random walk, the dollar values, and the course's module-9 failure.

Every series here is simulated with a fixed seed; no market data is used. Hand-worked values are
derived in the comments, never from the code under test.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from statsmodels.tsa.arima.model import ARIMA

from arima_forecasting import forecasting, payloads
from arima_forecasting.fitting import LABELS, course_refit
from arima_forecasting.forecasting import Spec, forecast_payload, forecast_rows, refit_walk_forward, static_forecast, t_multipliers, walk_forward, walk_forward_loop
from arima_forecasting.payloads import validate_forecast

# ARIMA(1, 1, 1) with a drift: drift, ar.L1, ma.L1, sigma2 (statsmodels' order for trend 't').
DRIFT = Spec((1, 1, 1), "t", np.array([0.0008, 0.3, -0.2, 0.0003]))
# ARIMA(0, 1, 1) without a trend, the course model's shape.
COURSE = Spec((0, 1, 1), "n", np.array([-0.08, 0.00035]))


def simulated(n: int = 300, seed: int = 20261029) -> np.ndarray:
    """A log price whose returns are ARMA(1, 1) around 0.0008: r_t = 0.0008 + 0.3 (r_(t-1) - 0.0008) + e_t - 0.2 e_(t-1)."""
    rng = np.random.default_rng(seed)
    e = 0.017 * rng.standard_normal(n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = 0.0008 + 0.3 * (r[t - 1] - 0.0008) + e[t] - 0.2 * e[t - 1]
    return math.log(30.0) + np.cumsum(r)


def table_for(y: np.ndarray, n_train: int, n_test: int, dates: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """A price table (prep.price_table's columns) over business days: train, test, then oos rows."""
    index = dates if dates is not None else pd.bdate_range("2021-01-04", periods=len(y))
    segment = ["train"] * n_train + ["test"] * n_test + ["oos"] * (len(y) - n_train - n_test)
    return pd.DataFrame({"close_usd": np.exp(y), "log_close": y, "segment": segment}, index=pd.DatetimeIndex(index, name="date"))


def fit_entry(model_id: str, spec: Spec) -> dict:
    """A `fit.models[]` entry with what forecast_payload reads: the id, label, order, trend and parameters."""
    names = list(spec.model(np.zeros(8)).param_names)
    ours = {"x1": "drift"} if spec.trend == "t" else {}
    return {
        "id": model_id,
        "label": LABELS[model_id],  # pinned per model id in both readers (payloads.MODEL_LABELS), so not made up
        "order": list(spec.order),
        "trend": spec.trend,
        "params": [{"name": ours.get(n, n), "library_name": n, "value": float(v)} for n, v in zip(names, spec.params, strict=True)],
    }


# --- the producer's constants are the readers' pins --------------------------------------------------


def test_the_pins_equal_the_producer_constants():
    assert forecasting.LEVELS == payloads.LEVELS
    assert forecasting.NORMAL_Z == payloads.NORMAL_Z == (float(stats.norm.ppf(0.9)), float(stats.norm.ppf(0.975)))
    assert forecasting.REFIT_EVERY == payloads.REFIT_EVERY == 21
    assert forecasting.FORECASTS == payloads.FORECASTS
    assert forecasting.KINDS == payloads.FORECAST_KINDS
    assert forecasting.WINDOWS == payloads.WINDOW_IDS
    assert forecasting.METHODS == payloads.FORECAST_METHODS


# --- walk-forward: the single pass is the append loop, and never looks ahead ---------------------------


@pytest.mark.parametrize("spec", [DRIFT, COURSE], ids=["(1, 1, 1) with a drift", "(0, 1, 1)"])
def test_the_single_filter_pass_equals_the_append_loop(spec):
    y = simulated()
    start, stop = 220, 260
    mean, var = walk_forward(y, start, stop, spec)
    loop_mean, loop_var = walk_forward_loop(y, start, stop, spec)
    np.testing.assert_allclose(mean, loop_mean, rtol=0, atol=1e-12)
    np.testing.assert_allclose(var, loop_var, rtol=1e-12, atol=0)


def extend_loop(y: np.ndarray, start: int, stop: int, spec: Spec) -> np.ndarray:
    """statsmodels' other route: extend() starts a model on the new row alone, from the last state."""
    result = spec.model(y[:start]).filter(spec.params)
    means = []
    for t in range(start, stop):
        means.append(float(result.get_forecast(1).predicted_mean[0]))
        result = result.extend(y[t : t + 1])
    return np.array(means)


def test_an_extend_loop_agrees_without_a_trend_and_restarts_the_drift_with_one():
    # Why the reference loop appends instead of extending. Without a trend the extend loop agrees
    # (to 6.9e-10 measured: it starts each new model from the last filtered state as a known one).
    y = simulated()
    np.testing.assert_allclose(extend_loop(y, 220, 260, COURSE), walk_forward(y, 220, 260, COURSE)[0], rtol=0, atol=1e-8)
    # With trend 't' it does not. ARIMA keeps the drift's time trend t = 1, 2, ... as an exog column.
    # Measured on statsmodels 0.15.0: after one extend the new row's trend value is right (221), but the
    # extended model's own trend_offset stays 1 (its _spec_arima has 221), and its one-step forecast is
    # lower by drift x 220 = 0.0008 x 220 = 0.176, as if the next day were t = 2; a second extend then
    # writes t = 2 into the data (SARIMAXResults.extend sets trend_offset = self.nobs + 1,
    # statsmodels/tsa/statespace/sarimax.py:1955, and the extended result has nobs 1). append(refit=False)
    # refilters the whole series and has none of this.
    gap = extend_loop(y, 220, 222, DRIFT) - walk_forward(y, 220, 222, DRIFT)[0]
    assert gap[0] == pytest.approx(0.0, abs=1e-12)
    assert gap[1] == pytest.approx(-0.0008 * 220, rel=1e-9)


def test_no_walk_forward_forecast_uses_its_own_day_or_a_later_one():
    y = simulated()
    start, stop, t = 200, 260, 230
    mean, var = walk_forward(y, start, stop, DRIFT)
    changed = y.copy()
    changed[t:] += 0.5  # a jump on day t and every day after it
    after, after_var = walk_forward(changed, start, stop, DRIFT)
    # The forecasts of days start..t are made from days before t: unchanged, the one of day t too.
    np.testing.assert_array_equal(after[: t - start + 1], mean[: t - start + 1])
    np.testing.assert_array_equal(after_var, var)  # the variances depend on no observation at all
    # The forecast of day t + 1 is made after seeing day t, so the jump reaches it.
    assert after[t - start + 1] - mean[t - start + 1] > 0.4


def test_no_refit_forecast_uses_its_own_day_or_a_later_one():
    # The same for the expanding refit: day t's jump reaches no forecast of day t or earlier, neither
    # through the state nor through a refit. Blocks of 10 rows: refits at 210, 220, ...
    y = simulated()
    start, stop, t = 200, 240, 225
    mean, _, refits = refit_walk_forward(y, start, stop, COURSE, every=10)
    changed = y.copy()
    changed[t:] += 0.5
    after, _, after_refits = refit_walk_forward(changed, start, stop, COURSE, every=10)
    np.testing.assert_array_equal(after[: t - start + 1], mean[: t - start + 1])
    assert after[t - start + 1] != mean[t - start + 1]
    # The refits fitted before day t saw no changed observation; the one at 230 did.
    assert [r["n_obs"] for r in refits] == [210, 220, 230]
    assert after_refits[:2] == refits[:2] and after_refits[2]["params"] != refits[2]["params"]


def test_the_refit_schedule_and_its_first_block():
    y = simulated()
    start, stop = 200, 250  # 50 rows: blocks at rows 0, 21 and 42, so two refits
    mean, var, refits = refit_walk_forward(y, start, stop, COURSE)
    assert [(r["row"], r["n_obs"]) for r in refits] == [(21, 221), (42, 242)]
    # The first 21 rows keep the given parameters: the plain walk-forward's forecasts.
    first_mean, first_var = walk_forward(y, start, start + 21, COURSE)
    np.testing.assert_array_equal(mean[:21], first_mean)
    np.testing.assert_array_equal(var[:21], first_var)
    # Block 2 is the refit on y[:242] from block 1's estimates, with the grid's optimiser settings.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        again = COURSE.model(y[:242]).fit(start_params=np.array(refits[0]["params"]), method="statespace", method_kwargs={"method": "lbfgs", "maxiter": 200}, cov_type="none")
    assert list(again.params) == refits[1]["params"]
    block_mean, _ = walk_forward(y, 242, 250, Spec(COURSE.order, COURSE.trend, np.array(refits[1]["params"])))
    np.testing.assert_array_equal(mean[42:], block_mean)
    with pytest.raises(ValueError, match="at least 1"):
        refit_walk_forward(y, start, stop, COURSE, every=0)


# --- static: the course's get_forecast ----------------------------------------------------------------


def test_the_static_path_is_the_course_get_forecast_from_the_training_fit():
    # The course's module 9: model_fit.get_forecast(steps) on ARIMA(train, order).fit(). The static
    # path from the same estimates is that forecast, mean and variance.
    y = simulated()
    train = y[:240]
    result, _ = course_refit(train, (0, 1, 1))
    spec = Spec((0, 1, 1), "n", np.asarray(result.params))
    mean, var = static_forecast(y, 240, 30, spec)
    course = result.get_forecast(30)
    np.testing.assert_allclose(mean, course.predicted_mean, rtol=0, atol=1e-12)
    np.testing.assert_allclose(var, course.var_pred_mean, rtol=1e-12, atol=0)
    # The oos path starts after the test rows with the state updated through them, no refit:
    # statsmodels' append(refit=False) is the other route to the same state.
    later_mean, later_var = static_forecast(y, 270, 30, spec)
    appended = result.append(y[240:270], refit=False).get_forecast(30)
    np.testing.assert_allclose(later_mean, appended.predicted_mean, rtol=0, atol=1e-12)
    np.testing.assert_allclose(later_var, appended.var_pred_mean, rtol=1e-12, atol=0)
    # The h-step variance never falls as h grows (a running sum of squared weights).
    assert np.all(np.diff(var) >= 0) and np.all(np.diff(later_var) >= 0)


# --- dollars and intervals ------------------------------------------------------------------------------


def test_the_dollar_values_of_one_row_by_hand():
    # mu = ln 100 and s = 0.2: the median is 100, the mean 100 e^(0.02) = 102.02013400267558, and the
    # 80% normal bounds 100 e^(-+0.2 x 1.2815515655446004), 77.39017796600125 and 129.2153637945265.
    intervals = {"normal_z": list(forecasting.NORMAL_Z), "t_multiplier": [1.0, 2.0]}
    (row,) = forecast_rows(["2024-01-02"], np.array([4.7]), np.array([109.94717245212638]), np.array([math.log(100.0)]), np.array([0.04]), intervals)
    assert row["median_usd"] == pytest.approx(100.0, rel=1e-14)
    assert row["mean_usd"] == pytest.approx(102.02013400267558, rel=1e-14)
    assert row["lower_80_usd"] == pytest.approx(77.39017796600125, rel=1e-13)
    assert row["upper_80_usd"] == pytest.approx(129.2153637945265, rel=1e-13)
    # The t bounds use the multipliers given: 1 and 2 standard deviations.
    assert row["t_lower_80_usd"] == pytest.approx(100.0 * math.exp(-0.2), rel=1e-14)
    assert row["t_upper_95_usd"] == pytest.approx(100.0 * math.exp(0.4), rel=1e-14)
    assert row["sd_log"] == pytest.approx(0.2, rel=1e-15)


def test_the_mean_is_the_mean_of_the_price_and_the_median_its_median():
    # A million log-normal prices drawn with mu = ln 100 and s = 0.3: their mean is exp(mu + s^2 / 2)
    # (104.6027859908717) to Monte Carlo error, and half of them lie below exp(mu) = 100.
    intervals = {"normal_z": list(forecasting.NORMAL_Z), "t_multiplier": [1.0, 2.0]}
    (row,) = forecast_rows(["2024-01-02"], np.array([4.6]), np.array([99.48]), np.array([math.log(100.0)]), np.array([0.09]), intervals)
    prices = np.exp(math.log(100.0) + 0.3 * np.random.default_rng(7).standard_normal(1_000_000))
    assert prices.mean() == pytest.approx(row["mean_usd"], rel=2e-3)
    assert prices.mean() != pytest.approx(row["median_usd"], rel=2e-2)
    assert np.mean(prices < row["median_usd"]) == pytest.approx(0.5, abs=2e-3)


def test_the_t_multipliers_give_the_t_the_forecast_variance():
    df = 3.4
    t = t_multipliers(df)
    # The scale makes the t's variance df / (df - 2) times scale^2 equal to 1.
    assert stats.t.var(df) * t["t_scale"] ** 2 == pytest.approx(1.0, rel=1e-14)
    for q, k, level in zip(t["t_quantile"], t["t_multiplier"], forecasting.LEVELS, strict=True):
        assert stats.t.cdf(q, df) == pytest.approx(0.5 + level / 2, abs=1e-14)
        assert k == pytest.approx(q * t["t_scale"], rel=1e-15)
    # Matching the variance, the t is narrower than the normal at 80% and 95% (concept note 11) ...
    assert t["t_multiplier"][0] < forecasting.NORMAL_Z[0] and t["t_multiplier"][1] < forecasting.NORMAL_Z[1]
    # ... and wider far out in the tails, at 99.9%.
    assert stats.t.ppf(0.9995, df) * t["t_scale"] > stats.norm.ppf(0.9995)
    for bad in (2.0, 1.5, math.inf, math.nan):
        with pytest.raises(ValueError, match="no finite variance"):
            t_multipliers(bad)


# --- the payload ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["static", "walk_forward", "refit"])
def test_a_forecast_payload_passes_the_reader_and_has_its_shape(method):
    y = simulated(330)
    table = table_for(y, 250, 30)
    data = forecast_payload(table, fit_entry("aic", DRIFT), 4.5, method)
    assert validate_forecast(data, "aic", method) == []
    test, oos = data["windows"]
    assert (test["n"], oos["n"]) == (30, 50)
    assert test["origin"]["date"] == table.index[249].date().isoformat() and oos["origin"]["date"] == table.index[279].date().isoformat()
    assert [r["date"] for r in test["rows"]] == [d.date().isoformat() for d in table.index[250:280]]
    assert [r["actual_log"] for r in oos["rows"]] == list(y[280:])
    assert (data["refits"] is None) == (method != "refit")
    if method == "static":
        # The oos path starts from the last test day, the state filtered through the test rows at the
        # training parameters: statsmodels' append(refit=False) is the other route to it.
        appended = DRIFT.model(y[:250]).filter(DRIFT.params).append(y[250:280], refit=False).get_forecast(50)
        assert [r["mean_log"] for r in oos["rows"]] == pytest.approx(list(appended.predicted_mean), rel=0, abs=1e-12)
        assert [r["sd_log"] for r in oos["rows"]] == pytest.approx(list(np.sqrt(appended.var_pred_mean)), rel=1e-12)
    if method == "refit":
        assert [r["n_obs"] for r in data["refits"]] == [271, 292, 313]  # 80 rows: refits at rows 21, 42 and 63
        assert [r["start_date"] for r in data["refits"]] == [table.index[i].date().isoformat() for i in (271, 292, 313)]


def test_the_payload_refuses_a_refit_of_another_model_and_a_mislabelled_parameter_list():
    table = table_for(simulated(300), 250, 20)
    with pytest.raises(ValueError, match="no 'refit' forecast for model 'bic'"):
        forecast_payload(table, fit_entry("bic", COURSE), 4.5, "refit")
    entry = fit_entry("course", COURSE)
    entry["params"][0]["library_name"] = "ar.L1"
    with pytest.raises(ValueError, match="are not statsmodels'"):
        forecast_payload(table, entry, 4.5, "static")


def test_the_windows_of_a_price_table():
    table = table_for(simulated(40), 20, 5)
    test, oos = forecasting.windows(table)
    assert (test.start, test.stop, oos.start, oos.stop) == (20, 25, 25, 40)
    shuffled = table.copy()
    shuffled.iloc[21, shuffled.columns.get_loc("segment")] = "oos"
    with pytest.raises(ValueError, match="train, then test, then oos"):
        forecasting.windows(shuffled)


# --- the course's module-9 failure --------------------------------------------------------------------------


def trading_days(n: int) -> pd.DatetimeIndex:
    """Business days with three holidays taken out: like an exchange calendar, no inferable frequency."""
    days = pd.bdate_range("2022-01-03", periods=n + 3)
    return days.delete([5, 40, 77])


def test_the_course_forecast_step_fails_on_a_trading_day_index_and_ours_does_not():
    # The course: df_log = np.log(df_close), where yfinance 1.7.0 gives df_close as a one-column
    # DataFrame with the trading dates as its index; ARIMA(train_data, order).fit(), then
    # get_forecast(steps=len(test_data)). With no frequency on the index, statsmodels 0.15 refuses.
    y = simulated(300)
    dates = trading_days(300)
    assert pd.infer_freq(dates) is None
    df_log = pd.DataFrame({"AAPL": y}, index=dates)
    train_data, test_data = df_log[:270], df_log[270:]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model_fit = ARIMA(train_data, order=(0, 1, 1)).fit()
        with pytest.raises(ValueError, match="No supported index is available"):
            model_fit.get_forecast(steps=len(test_data))
    # Ours builds every model on a numpy array and puts the dates back from the table.
    table = table_for(y, 250, 20, dates=dates)
    data = forecast_payload(table, fit_entry("course", COURSE), 4.5, "static")
    assert [r["date"] for r in data["windows"][1]["rows"]] == [d.date().isoformat() for d in dates[270:]]
    assert validate_forecast(data, "course", "static") == []
