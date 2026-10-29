"""Tests for eda.py: the summary, the KDEs and the decomposition.

Expected values are worked out by hand (arithmetic in the comments) or come from an independent
formula, never from the function under test.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from arima_forecasting import eda


def table(closes, start="2015-01-02") -> pd.DataFrame:
    closes = np.asarray(closes, dtype="float64")
    index = pd.bdate_range(start, periods=len(closes), name="date")
    return pd.DataFrame({"close_usd": closes, "log_close": np.log(closes), "segment": "train"}, index=index)


# --- 1. Summary ------------------------------------------------------------------------

def test_log_returns_are_first_differences_of_the_log_close():
    returns = eda.log_returns(table([100.0, 110.0, 99.0])["log_close"])
    # ln(110/100) and ln(99/110) = ln(0.9).
    assert returns.tolist() == pytest.approx([math.log(1.1), math.log(0.9)], abs=1e-15)


def test_summary_by_hand_on_doubling_and_halving_prices():
    # Closes 10, 20, 40, 20, 10: min 10, max 40, mean 100 / 5 = 20, median 20.
    # Log returns: +a, +a, -a, -a with a = ln 2. Mean 0. Sample variance = 4a^2 / 3, so
    # std = 2a / sqrt(3). Symmetric, so skew 0. Excess kurtosis by the bias-corrected formula:
    # population g2 = m4 / m2^2 - 3 = a^4 / a^4 - 3 = -2, and
    # G2 = ((n + 1) g2 + 6)(n - 1) / ((n - 2)(n - 3)) = (5 * -2 + 6) * 3 / (2 * 1) = -6.
    s = eda.summary(table([10.0, 20.0, 40.0, 20.0, 10.0]))
    a = math.log(2)
    assert s["n"] == 5
    assert (s["start"], s["end"]) == ("2015-01-02", "2015-01-08")
    assert s["close_usd"] == {"min": 10.0, "max": 40.0, "mean": 20.0, "median": 20.0}
    lr = s["log_return"]
    assert lr["n"] == 4
    assert lr["mean"] == pytest.approx(0.0, abs=1e-15)
    assert lr["std"] == pytest.approx(2 * a / math.sqrt(3), rel=1e-12)
    assert lr["skew"] == pytest.approx(0.0, abs=1e-12)
    assert lr["excess_kurtosis"] == pytest.approx(-6.0, rel=1e-12)


def test_summary_skew_and_kurtosis_are_the_bias_corrected_estimators():
    # An independent library as the oracle: scipy's skew and kurtosis with bias=False are G1 and
    # G2, the estimators the contract names. bias=True (scipy's default) would differ.
    rng = np.random.default_rng(3)
    closes = 50 * np.exp(np.cumsum(0.02 * rng.standard_t(4, 400)))
    s = eda.summary(table(closes))["log_return"]
    r = np.diff(np.log(closes))
    assert s["skew"] == pytest.approx(stats.skew(r, bias=False), rel=1e-10)
    assert s["excess_kurtosis"] == pytest.approx(stats.kurtosis(r, bias=False), rel=1e-10)
    assert s["skew"] != pytest.approx(stats.skew(r, bias=True), rel=1e-6)  # sanity: they differ
    assert s["std"] == pytest.approx(np.std(r, ddof=1), rel=1e-12)


def test_summary_refuses_to_write_a_nan():
    # Constant prices give a zero standard deviation and an undefined skew; NaN must not reach JSON.
    with pytest.raises(ValueError, match="non-finite"):
        eda.summary(table([10.0, 10.0, 10.0, 10.0]))


# --- 2. KDE --------------------------------------------------------------------------------

def test_kde_bandwidth_is_scotts_rule_times_the_sample_sd():
    values = np.array([0.0, 1.0, 3.0, 4.0, 7.0])
    k = eda.kde(values, "x")
    # Scott: factor = n^(-1/5) = 5^(-0.2); h = factor * s, with s the ddof=1 standard deviation.
    # mean 3; squares of deviations 9 + 4 + 0 + 1 + 16 = 30; s = sqrt(30 / 4) = sqrt(7.5).
    assert k["bandwidth_method"] == "scott"
    assert k["bandwidth_factor"] == pytest.approx(5 ** -0.2, rel=1e-12)
    assert k["bandwidth"] == pytest.approx(5 ** -0.2 * math.sqrt(7.5), rel=1e-12)
    assert k["n"] == 5


def test_kde_grid_has_200_points_from_three_bandwidths_below_to_three_above():
    values = np.array([0.0, 1.0, 3.0, 4.0, 7.0])
    k = eda.kde(values, "x")
    h = k["bandwidth"]
    xs = [p["x"] for p in k["points"]]
    assert len(xs) == eda.KDE_POINTS == 200
    assert xs[0] == pytest.approx(0.0 - 3 * h, rel=1e-12)
    assert xs[-1] == pytest.approx(7.0 + 3 * h, rel=1e-12)
    assert all(b > a for a, b in zip(xs, xs[1:]))


def test_kde_density_is_the_average_of_normal_bumps_and_the_normal_uses_the_sample_moments():
    values = np.array([0.0, 1.0, 3.0, 4.0, 7.0])
    k = eda.kde(values, "x")
    h = k["bandwidth"]
    s = math.sqrt(7.5)
    for p in k["points"][::37]:
        x = p["x"]
        # By the definition of a Gaussian KDE: (1 / n) * sum of N(x; x_i, h^2).
        by_hand = sum(math.exp(-((x - v) ** 2) / (2 * h * h)) / (h * math.sqrt(2 * math.pi)) for v in values) / 5
        assert p["density"] == pytest.approx(by_hand, rel=1e-9)
        normal = math.exp(-((x - 3.0) ** 2) / (2 * s * s)) / (s * math.sqrt(2 * math.pi))
        assert p["normal_density"] == pytest.approx(normal, rel=1e-9)


def test_kde_integrates_to_one_over_its_grid():
    rng = np.random.default_rng(5)
    k = eda.kde(rng.standard_normal(2000) * 0.02, "log_return")
    xs = np.array([p["x"] for p in k["points"]])
    ds = np.array([p["density"] for p in k["points"]])
    # The grid stops 3 bandwidths past the extremes, so a little mass (< 0.2%) falls outside it.
    assert np.trapezoid(ds, xs) == pytest.approx(1.0, abs=2e-3)


@pytest.mark.parametrize("values", [[1.0], [1.0, float("nan"), 2.0]])
def test_kde_refuses_too_few_or_non_finite_values(values):
    with pytest.raises(ValueError):
        eda.kde(np.array(values), "x")


# --- 3. Decomposition ------------------------------------------------------------------------

def seasonal_series(n: int = 700) -> pd.Series:
    t = np.arange(n)
    # A trend, a yearly wave with period 252 and a little noise, all in log points.
    rng = np.random.default_rng(11)
    values = 3.0 + 0.001 * t + 0.05 * np.sin(2 * np.pi * t / 252) + 0.002 * rng.standard_normal(n)
    return pd.Series(values, index=pd.bdate_range("2015-01-02", periods=n))


def test_decomposition_has_null_trend_and_residual_on_exactly_126_rows_at_each_end():
    rows = eda.decomposition(seasonal_series())["rows"]
    nulls = [r["trend_log"] is None for r in rows]
    # period 252 -> a centred moving average needs 252 // 2 = 126 days on each side.
    assert nulls == [i < 126 or i >= 700 - 126 for i in range(700)]
    assert [r["resid_log"] is None for r in rows] == nulls
    assert all(r["seasonal_log"] is not None for r in rows)


def test_decomposition_adds_up_to_the_observed_value():
    rows = eda.decomposition(seasonal_series())["rows"]
    for r in rows[126:-126]:
        assert r["trend_log"] + r["seasonal_log"] + r["resid_log"] == pytest.approx(r["observed_log"], abs=1e-12)


def test_the_seasonal_part_repeats_every_period_and_averages_to_zero():
    rows = eda.decomposition(seasonal_series())["rows"]
    seasonal = np.array([r["seasonal_log"] for r in rows])
    assert np.allclose(seasonal[:252], seasonal[252:504], atol=1e-15)
    assert seasonal[:252].mean() == pytest.approx(0.0, abs=1e-12)


def test_decomposition_needs_two_full_periods():
    with pytest.raises(ValueError, match="at least 504"):
        eda.decomposition(seasonal_series(503))


def test_the_course_comparison_by_hand_on_a_level_plus_a_pure_seasonal_pattern():
    # log price = 3 + s, with s repeating [0.2, 0.1, -0.2, -0.1] and period 4. Worked by hand:
    # - The 2x4 moving average (weights 1/8, 1/4, 1/4, 1/4, 1/8) covers one whole period, and s
    #   sums to 0 over a period, so the trend is exactly 3 and the additive seasonal part is s.
    # - Multiplicative on logs: detrended (3 + s) / 3 = 1 + s / 3, already averaging 1, so the
    #   factors are 1 + s / 3: min 1 - 0.2/3, max 1 + 0.2/3. Put on our scale, T * (S - 1) = s
    #   exactly, so the seasonal gap is 0.
    # - Dollars: e^(3 + s). Its trend is e^3 * m, m = mean(e^s) = (cosh 0.2 + cosh 0.1) / 2, so
    #   exp(T_log) / T_usd = 1 / m; its seasonal is e^s / m, so exp(S_add) / S_usd = m.
    pattern = np.array([0.2, 0.1, -0.2, -0.1])
    logs = 3.0 + np.tile(pattern, 10)
    t = pd.DataFrame({"close_usd": np.exp(logs), "log_close": logs}, index=pd.bdate_range("2015-01-02", periods=40))
    c = eda.course_comparison(t, period=4)
    m = (math.cosh(0.2) + math.cosh(0.1)) / 2
    assert c["trend_max_abs_diff"] == pytest.approx(0.0, abs=1e-12)
    assert c["additive_seasonal_range"] == pytest.approx(0.4, abs=1e-12)
    assert c["multiplicative_seasonal_min"] == pytest.approx(1 - 0.2 / 3, abs=1e-12)
    assert c["multiplicative_seasonal_max"] == pytest.approx(1 + 0.2 / 3, abs=1e-12)
    assert c["seasonal_gap_max_abs"] == pytest.approx(0.0, abs=1e-12)
    assert c["dollar_trend_max_rel_gap"] == pytest.approx(1 - 1 / m, rel=1e-9)
    assert c["dollar_seasonal_max_rel_gap"] == pytest.approx(m - 1, rel=1e-9)
    assert 0.0124 < m - 1 < 0.0126  # sanity: (cosh 0.2 + cosh 0.1) / 2 - 1 = 0.012515...


def test_the_course_comparison_trends_agree_and_the_seasonal_gap_appears_with_a_slope():
    # On a sloping series the log level, and so the course's factor-to-log-points conversion,
    # changes over time: the seasonal gap is then strictly positive.
    s = seasonal_series()
    t = pd.DataFrame({"close_usd": np.exp(s.to_numpy()), "log_close": s.to_numpy()}, index=s.index)
    c = eda.course_comparison(t)
    assert c["trend_max_abs_diff"] == 0.0
    assert c["seasonal_gap_max_abs"] > 1e-4


def test_tail_share_uses_the_sample_sd_and_exactly_k_of_them():
    # 15 zeros, -1, 1, -6, 6 (n = 19): mean 0, sum of squares 74. Sample sd (n - 1) = sqrt(74/18)
    # = 2.0276, so 3 sd = 6.083 and the two 6s are NOT beyond it: share 0. With n instead of n - 1,
    # 3 sd would be 3 * sqrt(74/19) = 5.920 and both 6s would count; at 2.4 sd (4.866) too.
    values = np.array([0.0] * 15 + [-1.0, 1.0, -6.0, 6.0])
    assert eda.tail_share(values, 3.0)["observed"] == 0.0
    assert eda.tail_share(values, 2.9)["observed"] == pytest.approx(2 / 19, abs=1e-15)  # 2.9 sd = 5.880


def test_tail_share_counts_values_beyond_k_sample_sds():
    # Values 0 x 18, then -10 and +10: mean 0, sum of squares 200, sample variance 200 / 19,
    # sd = 3.244; 3 sd = 9.73, so exactly the two extremes are beyond it: 2 / 20 = 10%.
    values = np.array([0.0] * 18 + [-10.0, 10.0])
    share = eda.tail_share(values, 3.0)
    assert share["observed"] == pytest.approx(0.1, abs=1e-15)
    # Normal: 2 * (1 - Phi(3)) = 0.0026998 (a standard table value).
    assert share["normal"] == pytest.approx(0.0026998, abs=1e-7)
    assert share["k"] == 3.0
