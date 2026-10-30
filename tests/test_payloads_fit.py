"""The rules of validate_fit and validate_residuals that only Python applies (contract.md 3.7, "What
each reader checks"). Each recomputes a statistic or compares one with a threshold, which the app
never does (ADR-0001), so these cases cannot go in the shared corpus, whose verdicts both readers
must reach. The shared rules are in app/src/test/fixtures/payload_cases.json. The check that
fit.json and the three residuals files agree (validate_fit_residuals) is at the end of this file.

The bases are the corpus's hand-made fixtures; every case changes one value and names the rule.
"""

from __future__ import annotations

import copy
import json
import math
import signal
import time
from pathlib import Path

import pytest
from scipy import stats

from arima_forecasting import payloads
from arima_forecasting.payloads import validate_fit, validate_fit_residuals, validate_residuals

FIXTURES = Path(__file__).resolve().parent.parent / "app" / "src" / "test" / "fixtures"
FIT = json.loads((FIXTURES / "fit.data.json").read_text(encoding="utf-8"))
RESIDUALS = json.loads((FIXTURES / "residuals_aic.data.json").read_text(encoding="utf-8"))
Z95 = 1.959963984540054  # the contract's z for alpha 0.05


def edited(base: dict, path: list, change) -> dict:
    data = copy.deepcopy(base)
    *parents, last = path
    node = data
    for key in parents:
        node = node[key]
    node[last] = change(node[last]) if callable(change) else change
    return data


def test_the_bases_are_valid():
    assert validate_fit(FIT) == []
    assert validate_residuals(RESIDUALS, "aic") == []


PARAM = ["models", 0, "params", 1]
DIAG = ["models", 0, "diagnostics"]
BIC_DIAG = ["models", 1, "diagnostics"]
INFO = ["models", 0, "information"]
DRIFT = ["course_track", "drift_dropped"]

FIT_CASES = [
    ("z is not value / std_err", [*PARAM, "z"], lambda v: v * 1.001, "value / std_err"),
    ("the p-value is not 2 (1 - Phi(|z|))", [*PARAM, "p_value"], lambda v: min(1.0, v + 0.01), "2 * (1 - Phi(|z|))"),
    ("the interval is not value +- z95 std_err", [*PARAM, "ci_high"], lambda v: v + 0.01, "value +- z * std_err"),
    ("sigma2's interval is not value +- z95 std_err", ["models", 0, "params", 5, "ci_high"], lambda v: v * 1.01, "value +- z * std_err"),
    ("AIC is not -2 llf + 2k", [*INFO, "aic"], lambda v: v + 0.5, "-2 llf + 2 k"),
    ("BIC is not -2 llf + ln(n) k with n = nobs_effective", [*INFO, "bic"], lambda v: v + 0.5, "-2 llf + ln(n) k"),
    ("AICc is not -2 llf + 2 k n / (n - k - 1)", [*INFO, "aicc"], lambda v: v + 0.5, "2 k n / (n - k - 1)"),
    ("llf_gap is not llf - grid_llf", ["models", 0, "llf_gap"], lambda v: v + 1e-9, "llf - grid_llf"),
    ("the refit is outside the llf tolerance", ["models", 0], lambda m: {**m, "grid_llf": m["information"]["llf"] - 2e-6, "llf_gap": m["information"]["llf"] - (m["information"]["llf"] - 2e-6)}, "outside llf_tolerance 1e-06"),
    ("a modulus is not |re + i im|", ["models", 0, "inv_roots_ar", 0, "modulus"], lambda v: v + 0.01, "|re + i im|"),
    ("roots out of modulus order", ["models", 0, "inv_roots_ma", 1], {"re": 0.99, "im": 0.0, "modulus": 0.99}, "largest first"),
    ("a pair's distance is wrong", ["models", 0, "cancelling_pairs", 0, "distance"], lambda v: v + 0.01, "apart"),
    # MA roots moved to 0.3 -+ 0.25i, 0.15 from their AR roots, past cancel_distance 0.1; the pairs keep their true distances.
    ("a pair the rule does not make", ["models", 0], lambda m: {**m, "inv_roots_ma": [{"re": 0.3, "im": -0.25, "modulus": abs(complex(0.3, 0.25))}, {"re": 0.3, "im": 0.25, "modulus": abs(complex(0.3, 0.25))}], "cancelling_pairs": [{"ar": i, "ma": i, "distance": abs(complex(0.3, s * 0.4) - complex(0.3, s * 0.25))} for i, s in ((0, -1), (1, 1))]}, "the stated rule"),
    ("a pair the rule makes, left out", ["models", 0, "cancelling_pairs"], lambda v: v[:1], "the stated rule"),
    ("pairs not listed by AR index", ["models", 0, "cancelling_pairs"], lambda v: v[::-1], "listed by AR index"),
    ("a serial-correlation verdict against its p-values", [*DIAG, "verdicts", "serial_correlation"], "found", "Ljung-Box p-values"),
    ("a normality verdict against its p-value", [*DIAG, "verdicts", "normality"], "not_rejected", "Jarque-Bera"),
    ("an ARCH verdict against its p-values", [*DIAG, "verdicts", "arch"], "not_found", "the ARCH-LM p-values give"),
    ("arch_lm_rejections against the p-values", ["clustering_prediction", "arch_lm_rejections"], lambda v: v + 1, "ARCH-LM p-values are below"),
    ("expected-by-chance is not alpha * nlags", ["clustering_prediction", "acf_squared_expected_by_chance"], lambda v: v + 1, "alpha * nlags"),
    ("aic_gap is not without - with", [*DRIFT, "aic_gap"], lambda v: v + 0.1, "aic_without_drift - aic_with_drift"),
    # Each test's p-value is the chi-squared tail of its statistic (made-up statistics, scipy's p).
    ("a Ljung-Box p-value that is not chi2.sf(statistic, df)", [*DIAG, "ljung_box", 1, "p_value"], lambda v: v * 1.01, "the Ljung-Box statistic 5.9 on 5 df"),
    ("a Ljung-Box statistic that does not give its p-value", [*BIC_DIAG, "ljung_box", 0, "statistic"], lambda v: v + 0.1, "the Ljung-Box statistic"),
    ("a Jarque-Bera p-value that is not chi2.sf(statistic, 2)", [*DIAG, "jarque_bera", "p_value"], lambda v: v * 1.01, "the Jarque-Bera statistic 9.5 on 2 df"),
    ("an ARCH-LM p-value that is not chi2.sf(statistic, lags)", [*DIAG, "arch_lm", 1, "p_value"], lambda v: v * 1.01, "the ARCH-LM statistic 21.3 on 10 df"),
    # chi2.sf(14.2, 10), the tail of the lag-5 statistic on the other row's df.
    ("an ARCH-LM p-value from the wrong df", [*DIAG, "arch_lm", 0, "p_value"], float(stats.chi2.sf(14.2, 10)), "the ARCH-LM statistic 14.2 on 5 df"),
    ("a negative Ljung-Box statistic", [*DIAG, "ljung_box", 0, "statistic"], -0.4, "must be >= 0"),
    ("a negative Jarque-Bera statistic", [*DIAG, "jarque_bera", "statistic"], -9.5, "must be >= 0"),
    ("a negative ARCH-LM statistic", [*DIAG, "arch_lm", 0, "statistic"], -6.2, "must be >= 0"),
    ("a Pearson kurtosis below 1", [*DIAG, "jarque_bera", "kurtosis"], 0.9, "at least 1"),
    ("a drift p-value that is not 2 (1 - Phi(|drift / se|))", [*DRIFT, "drift_p_value"], lambda v: v * 1.01, "drift / drift_std_err"),
    # Jarque-Bera's statistic is n / 6 (S^2 + (K - 3)^2 / 4) of the exported skew and kurtosis. 1600
    # with p 0.0 (chi2.sf(1600, 2) = e^-800 underflows) passes the p-value tie, so only this rule sees it.
    ("a Jarque-Bera statistic that is not n / 6 (S^2 + (K - 3)^2 / 4)", [*DIAG, "jarque_bera"], lambda j: {**j, "statistic": 1600.0, "p_value": 0.0}, "n / 6 (skew^2 + (kurtosis - 3)^2 / 4) with n 39"),
    # Skew 3 and kurtosis 9.5: above 1, below 1 + 3^2 = 10. JB = 39 / 6 (9 + 6.5^2 / 4) = 127.15625 and
    # its p-value (scipy's), so only the kurtosis rule is broken.
    ("a Pearson kurtosis below 1 + skew^2", [*DIAG, "jarque_bera"], lambda j: {**j, "skew": 3.0, "kurtosis": 9.5, "statistic": 127.15625, "p_value": float(stats.chi2.sf(127.15625, 2))}, "at least 1 + skew^2 = 10.0"),
    # Q(20) 15.0 below Q(10) 17.9, its p-value chi2.sf(15.0, 19) (the verdict stays "found").
    ("a Ljung-Box Q that falls as the lag grows", [*BIC_DIAG, "ljung_box", 2], lambda r: {**r, "statistic": 15.0, "p_value": float(stats.chi2.sf(15.0, 19))}, "below 17.9 at lag 10"),
    # (n - m) R^2 <= n - m = 39 - 5 = 34: 34.5 with its p-value chi2.sf(34.5, 5).
    ("an ARCH-LM statistic above n - lags", [*DIAG, "arch_lm", 0], lambda r: {**r, "statistic": 34.5, "p_value": float(stats.chi2.sf(34.5, 5))}, "at most n - lags - ddof = 34"),
    ("a negative sigma2, its interval moved with it", ["models", 0, "params", 6], lambda r: {**r, "value": -r["value"], "ci_low": -r["value"] - Z95 * r["std_err"], "ci_high": -r["value"] + Z95 * r["std_err"]}, "sigma2 is a variance"),
    ("a sigma2 of zero", ["models", 1, "params", 1], lambda r: {**r, "value": 0.0, "ci_low": -Z95 * r["std_err"], "ci_high": Z95 * r["std_err"]}, "must be positive, got 0.0"),
]


@pytest.mark.parametrize(("name", "path", "change", "message"), FIT_CASES, ids=[c[0] for c in FIT_CASES])
def test_python_refuses_a_fit_that_breaks_a_statistical_rule(name, path, change, message):
    data = edited(FIT, path, change)
    assert data != FIT, f"the case {name!r} changed nothing in the base"
    problems = validate_fit(data)
    assert any(message in p for p in problems), problems


def jarque_bera_at(statistic: float, p: float) -> dict:
    """The base with the AIC model's Jarque-Bera statistic and p-value replaced, and a skew of 0 and
    the kurtosis that give that statistic with n = 39: K = 3 + 2 sqrt(6 JB / 39) solves
    JB = 39 / 6 ((K - 3)^2 / 4)."""
    return edited(FIT, [*DIAG, "jarque_bera"], {"statistic": statistic, "p_value": p, "skew": 0.0, "kurtosis": 3.0 + 2.0 * math.sqrt(6.0 * statistic / 39.0)})


def test_a_p_value_that_underflows_to_zero_passes_within_the_floor():
    # chi2.sf(1600, 2) = exp(-800) is below the smallest double, so the exporter writes 0.0; 1e-310
    # (a subnormal) is as good. P_FLOOR is 1e-300, so neither is refused, and 1e-299 is.
    assert validate_fit(jarque_bera_at(1600.0, 0.0)) == validate_fit(jarque_bera_at(1600.0, 1e-310)) == []
    assert any("the Jarque-Bera statistic 1600.0" in p for p in validate_fit(jarque_bera_at(1600.0, 1e-299)))


def test_a_p_value_of_zero_is_taken_only_where_the_tail_is_below_the_floor():
    # chi2.sf(1382, 2) = e^-691 = 8.0e-301 is below P_FLOOR (1e-300): a 0 there is an underflow.
    # chi2.sf(1381, 2) = e^-690.5 = 1.3e-300 is not, so a 0 there is refused.
    assert validate_fit(jarque_bera_at(1382.0, 0.0)) == []
    assert any("is 0, but the Jarque-Bera statistic 1381.0 on 2 df" in p and "above the underflow floor 1e-300" in p for p in validate_fit(jarque_bera_at(1381.0, 0.0)))
    # A 0 beside a moderate statistic, for each test: Ljung-Box 5.9 on 5 df, Jarque-Bera 9.5, ARCH-LM 14.2 on 5 df.
    for path, statistic in (([*DIAG, "ljung_box", 1, "p_value"], "Ljung-Box statistic 5.9 on 5 df"), ([*DIAG, "jarque_bera", "p_value"], "Jarque-Bera statistic 9.5 on 2 df"), ([*DIAG, "arch_lm", 0, "p_value"], "ARCH-LM statistic 14.2 on 5 df")):
        problems = validate_fit(edited(FIT, path, 0.0))
        assert any(f"is 0, but the {statistic}" in p and "above the underflow floor" in p for p in problems), problems


def test_the_chi_squared_tail_is_scipys():
    from scipy import stats

    from arima_forecasting.payloads import _chi2_sf

    for k in range(1, 31):
        for x in (0.0, 1e-9, 0.3, 1.0, 2.1, 9.5, 37.0, 242.39, 1415.1, 1e5):
            want = stats.chi2.sf(x, k)
            assert _chi2_sf(x, k) == pytest.approx(want, rel=1e-12, abs=1e-300), (x, k)


def test_the_chi_squared_tail_of_zero_and_of_the_smallest_subnormals_is_one():
    # h = x / 2 is 0.0 for 0 and for 5e-324 (halving the smallest subnormal rounds to 0), and
    # math.log(0.0) raises; 1e-323 is the next double up, whose half is 5e-324.
    for k in range(1, 31):
        assert [payloads._chi2_sf(x, k) for x in (0.0, 5e-324, 1e-323, 1e-300)] == [1.0, 1.0, 1.0, 1.0], k


def tiny_statistic(which: str, statistic: float, p: float) -> dict:
    """The AIC model with one test's statistic replaced by a tiny one and its p-value by `p`, the verdict
    that goes with p kept, and every other row consistent: Ljung-Box lag 10 (0.0 at lag 5 before it, so
    Q does not fall), Jarque-Bera with a skew of 0 and a kurtosis of 3, ARCH-LM at 5 lags."""
    if which == "ljung_box":
        data = edited(FIT, [*DIAG, "ljung_box", 0, "statistic"], 0.0)
        return edited(edited(data, [*DIAG, "ljung_box", 1, "statistic"], statistic), [*DIAG, "ljung_box", 1, "p_value"], p)
    if which == "jarque_bera":
        data = edited(FIT, [*DIAG, "jarque_bera"], {"statistic": statistic, "p_value": p, "skew": 0.0, "kurtosis": 3.0})
        return edited(data, [*DIAG, "verdicts", "normality"], "not_rejected" if p >= 0.05 else "rejected")
    data = edited(edited(FIT, [*DIAG, "arch_lm", 0, "statistic"], statistic), [*DIAG, "arch_lm", 0, "p_value"], p)
    return edited(data, ["clustering_prediction", "arch_lm_rejections"], 1)  # the lag-10 row alone rejects


@pytest.mark.parametrize("statistic", [0.0, 5e-324, 1e-323])
@pytest.mark.parametrize("which", ["ljung_box", "jarque_bera", "arch_lm"])
def test_a_statistic_of_zero_or_a_subnormal_has_a_p_value_of_one_and_never_raises(which, statistic):
    # Before the fix 5e-324 raised "math domain error" out of validate_fit for each of the three tests.
    assert validate_fit(tiny_statistic(which, statistic, 1.0)) == []
    problems = validate_fit(tiny_statistic(which, statistic, 0.5))
    assert len(problems) == 1 and "gives p = 1.0" in problems[0], problems


@pytest.mark.parametrize(
    ("which", "verdict_path", "wrong", "message"),
    [
        ("ljung_box", [*DIAG, "verdicts", "serial_correlation"], "found", "the Ljung-Box p-values give 'not_found'"),
        ("jarque_bera", [*DIAG, "verdicts", "normality"], "rejected", "Jarque-Bera's p-value is 1.0"),
        ("arch_lm", [*DIAG, "verdicts", "arch"], "not_found", "the ARCH-LM p-values give 'found'"),
    ],
)
def test_a_verdict_is_judged_on_the_p_value_of_a_tiny_statistic(which, verdict_path, wrong, message):
    # p = 1 from a statistic of 5e-324: ARCH-LM still finds clustering through its lag-10 row (p 0.019), the
    # other two read "no autocorrelation" and "normality not rejected"; the opposite verdict is refused.
    data = tiny_statistic(which, 5e-324, 1.0)
    problems = validate_fit(edited(data, verdict_path, wrong))
    assert any(message in p for p in problems), problems


def far_lag_file(case: str, lag: int) -> dict:
    """The re-review's probes: a lag of `lag` in the Ljung-Box or ARCH-LM rows (of every model), with the
    settings agreeing ("settings_and_rows") or the settings left at the pins ("rows")."""
    data = copy.deepcopy(FIT)
    if case.startswith("lb"):
        if case == "lb_settings_and_rows":
            data["diagnostic_settings"]["ljung_box_lags"] = [5, 10, lag]
        for m in data["models"]:
            m["diagnostics"]["ljung_box"][2].update(lag=lag, applied=True, df=lag - m["diagnostics"]["ljung_box"][2]["model_df"], p_value=0.5)
    else:
        data["diagnostic_settings"]["arch_lm_lags"] = [5, lag]
        for m in data["models"]:
            m["diagnostics"]["arch_lm"][1].update(lags=lag, p_value=0.5)
    return data


@pytest.mark.parametrize("lag", [10**9, 2**53 - 1])
@pytest.mark.parametrize("case", ["lb_settings_and_rows", "lb_rows", "arch_settings_and_rows"])
def test_a_lag_far_past_the_pinned_ones_never_reaches_the_chi_squared(case, lag):
    # The tail is a loop of df / 2 steps: a lag of 1e9 ran for over a minute before the pins, and
    # 2^53 - 1 was effectively unbounded. The row is a problem (its lag is not the pinned one) and
    # its p-value is not tied to anything.
    problems, seconds = timed(lambda: validate_fit(far_lag_file(case, lag)), limit=5.0)
    assert seconds < 1.0
    assert problems and not any("gives p" in p for p in problems), problems
    assert any(f"is {lag}, expected" in p for p in problems), problems


def test_a_ljung_box_row_whose_df_is_not_the_pinned_one_skips_the_p_value_tie():
    # model_df 3 instead of p + q = 5 on the lag-10 row, its df 7 = lag - model_df and its p-value
    # (the base's, for 5 df): the model_df is the one problem. A chi-squared on 7 df would add "gives p".
    row = FIT["models"][0]["diagnostics"]["ljung_box"][1]
    data = edited(FIT, [*DIAG, "ljung_box", 1], {**row, "model_df": 3, "df": 7})
    assert validate_fit(data) == ["data.models[0].diagnostics.ljung_box[1].model_df: is 3, but p + q is 5"]


def lags5_file() -> dict:
    """The re-review's probe: ljung_box_lags [5] and every model's rows cut to lag 5, each model's verdict
    that of its own rows. The course model's serial-correlation verdict, "found" on the real lags (its
    lag-10 p-value is 0.025; lag 5's is 0.099), becomes "not_found"; the AIC model's, whose lag-5 row is
    not applied, "not_tested"."""
    data = edited(FIT, ["diagnostic_settings", "ljung_box_lags"], [5])
    for i, verdict in enumerate(("not_tested", "found", "not_found")):
        data = edited(data, ["models", i, "diagnostics", "ljung_box"], lambda rows: rows[:1])
        data = edited(data, ["models", i, "diagnostics", "verdicts", "serial_correlation"], verdict)
    return data


def test_a_file_cannot_change_a_verdict_by_stating_other_lags():
    assert [m["diagnostics"]["verdicts"]["serial_correlation"] for m in FIT["models"]] == ["not_found", "found", "found"]
    data = lags5_file()
    assert [m["diagnostics"]["verdicts"]["serial_correlation"] for m in data["models"]] == ["not_tested", "found", "not_found"]
    # Read at its own lags this file is consistent (the re-review found 0 problems); it is judged at the pinned ones.
    assert validate_fit(data) == [
        "data.diagnostic_settings.ljung_box_lags: is [5], but this reader checks Ljung-Box at lags [5, 10, 20]",
        *[f"data.models[{i}].diagnostics.ljung_box: has 1 rows, but ljung_box_lags has 3" for i in range(3)],
    ]


@pytest.mark.parametrize(
    ("key", "stated", "message"),
    [
        ("alpha", 0.1, "is 0.1, but this reader tests at alpha 0.05"),
        ("ljung_box_lags", [5, 10, 21], "is [5, 10, 21], but this reader checks Ljung-Box at lags [5, 10, 20]"),
        ("arch_lm_lags", [5], "is [5], but this reader checks ARCH-LM at lags [5, 10]"),
        ("arch_lm_ddof", 1, "is 1, but this reader checks ARCH-LM with ddof 0"),
        ("nlags", 49, "is 49, but this reader checks the correlograms at nlags 50"),
    ],
)
def test_a_stated_residual_test_setting_other_than_the_pinned_one_is_refused(key, stated, message):
    problems = validate_fit(edited(FIT, ["diagnostic_settings", key], stated))
    assert f"data.diagnostic_settings.{key}: {message}" in problems, problems


def test_a_self_consistent_file_with_other_nlags_is_judged_at_the_pinned_one():
    # nlags 49 and expected-by-chance 0.05 * 49: consistent with itself, refused, and the page's
    # expected count is still judged as alpha * 50.
    data = edited(edited(FIT, ["diagnostic_settings", "nlags"], 49), ["clustering_prediction", "acf_squared_expected_by_chance"], 0.05 * 49)
    problems = validate_fit(data)
    assert any("nlags: is 49" in p for p in problems) and any("but alpha * nlags is 2.5" in p for p in problems), problems


def test_a_stated_pin_one_part_in_a_trillion_away_is_refused():
    # Pinned values are compared exactly: 1e-12 away is another value (a tolerance of 1e-9 would pass it).
    for key, pin in (("llf_tolerance", 1e-6), ("cancel_distance", 0.1)):
        problems = validate_fit(edited(FIT, [key], pin + 1e-12))
        assert any(p.startswith(f"data.{key}: is {pin + 1e-12}, but this reader") for p in problems), (key, problems)
    problems = validate_fit(edited(FIT, ["diagnostic_settings", "alpha"], 0.05 + 1e-12))
    assert any(p.startswith("data.diagnostic_settings.alpha: is 0.050000000001, but this reader tests at alpha 0.05") for p in problems), problems


def test_the_jarque_bera_statistic_is_tied_to_its_formula_to_a_part_in_a_billion():
    # Statistic 1600 with p 0.0 (its tail underflows, so the p-value tie sees nothing): 1e-6 relative off
    # is refused by the formula tie alone, 1e-11 off is not. A tie at 1e-2 would pass the first.
    base = jarque_bera_at(1600.0, 0.0)
    off = validate_fit(edited(base, [*DIAG, "jarque_bera", "statistic"], 1600.0 * (1 + 1e-6)))
    assert len(off) == 1 and "n / 6 (skew^2 + (kurtosis - 3)^2 / 4)" in off[0], off
    assert validate_fit(edited(base, [*DIAG, "jarque_bera", "statistic"], 1600.0 * (1 + 1e-11))) == []


def test_the_kurtosis_bound_is_1_plus_skew_squared_with_no_slack_to_speak_of():
    # Skew 3: the least possible kurtosis is 1 + 9 = 10, a two-point sample. At 10 the file is valid (JB =
    # 39 / 6 (9 + 49 / 4) = 138.125); at 9.99999, 1e-6 relative below, it is refused (JB 138.1247725001625).
    def at(kurtosis: float, statistic: float) -> dict:
        return edited(FIT, [*DIAG, "jarque_bera"], lambda j: {**j, "skew": 3.0, "kurtosis": kurtosis, "statistic": statistic, "p_value": float(stats.chi2.sf(statistic, 2))})

    assert validate_fit(at(10.0, 138.125)) == []
    assert validate_fit(at(9.99999, 138.1247725001625)) == ["data.models[0].diagnostics.jarque_bera.kurtosis: is 9.99999, but Pearson's kurtosis is at least 1 + skew^2 = 10.0"]


def test_a_ljung_box_q_at_a_lag_that_is_not_applied_may_not_exceed_a_later_one():
    # The AIC model is (3, 1, 2): its lag-5 row is not applied (5 <= p + q), so it has no p-value, but its
    # Q is a running sum all the same: 7.0 at lag 5 above 5.9 at lag 10 is refused.
    problems = validate_fit(edited(FIT, [*DIAG, "ljung_box", 0, "statistic"], 7.0))
    assert problems == ["data.models[0].diagnostics.ljung_box[1].statistic: is 5.9, below 7.0 at lag 5: Ljung-Box Q is a running sum of non-negative terms, so it cannot fall as the lag grows"]


def test_aicc_where_n_minus_k_minus_1_is_not_positive_is_refused():
    # With k = 6 and n = nobs_effective = 7, statsmodels' AICc is +inf, which no JSON file can hold.
    data = edited(FIT, ["n_train"], 7)
    for i in range(3):
        data = edited(data, ["models", i, "nobs"], 7)
        data = edited(data, ["models", i, "nobs_effective"], 6)
        data = edited(data, ["models", i, "diagnostics", "n"], 6)
    data = edited(data, ["course_track", "n_train"], 7)
    data = edited(data, ["course_track", "test_rows_seen"], 5)
    assert any("models[0].information.aicc" in p and "undefined" in p for p in validate_fit(data)), validate_fit(data)


def test_the_cancelling_rule_is_a_maximum_matching_not_closest_first():
    # AR 0.6, 0.5 and MA 0.51, 0.41: closest first pairs 0.5 with 0.51 (0.01 apart) and leaves 0.6
    # and 0.41 (0.19 apart) unpaired; the rule pairs 0.6 with 0.51 and 0.5 with 0.41, 0.09 each.
    def roots(*xs: float) -> list[dict]:
        return [{"re": x, "im": 0.0, "modulus": x} for x in xs]

    # The AIC model is (3, 1, 2): a third AR root, 0.2, far from every MA root here, sorts last.
    base = edited(edited(FIT, ["models", 0, "inv_roots_ar"], roots(0.6, 0.5, 0.2)), ["models", 0, "inv_roots_ma"], roots(0.51, 0.41))
    greedy = edited(base, ["models", 0, "cancelling_pairs"], [{"ar": 1, "ma": 0, "distance": abs(0.5 - 0.51)}])
    assert any("gives 2 pairs" in p for p in validate_fit(greedy)), validate_fit(greedy)
    best = edited(base, ["models", 0, "cancelling_pairs"], [{"ar": 0, "ma": 0, "distance": abs(0.6 - 0.51)}, {"ar": 1, "ma": 1, "distance": abs(0.5 - 0.41)}])
    assert validate_fit(best) == []
    # Two pairs, but not the least total: 0.6 with 0.41 is 0.19 apart, past the threshold anyway.
    crossed = edited(base, ["models", 0, "cancelling_pairs"], [{"ar": 0, "ma": 1, "distance": abs(0.6 - 0.41)}, {"ar": 1, "ma": 0, "distance": abs(0.5 - 0.51)}])
    assert any("above cancel_distance" in p for p in validate_fit(crossed))
    # As many pairs either way, both within 0.1: AR 0.6, 0.5 against MA 0.58, 0.52. The rule takes the
    # least total, 0.02 + 0.02, not 0.08 + 0.08.
    near = edited(base, ["models", 0, "inv_roots_ma"], roots(0.58, 0.52))
    least = edited(near, ["models", 0, "cancelling_pairs"], [{"ar": 0, "ma": 0, "distance": abs(0.6 - 0.58)}, {"ar": 1, "ma": 1, "distance": abs(0.5 - 0.52)}])
    assert validate_fit(least) == []
    larger = edited(near, ["models", 0, "cancelling_pairs"], [{"ar": 0, "ma": 1, "distance": abs(0.6 - 0.52)}, {"ar": 1, "ma": 0, "distance": abs(0.5 - 0.58)}])
    assert any("gives 2 pairs with total distance 0.04" in p for p in validate_fit(larger)), validate_fit(larger)


def test_a_pair_exactly_cancel_distance_apart_is_a_pair():
    # 0.32 - 0.22 is exactly the double 0.1, so these conjugate pairs sit on the threshold, which is
    # inclusive (|a - m| <= 0.1): both pairs are made, and leaving them out is refused.
    def at(re: float) -> list[dict]:
        return [{"re": re, "im": -0.4, "modulus": abs(complex(re, 0.4))}, {"re": re, "im": 0.4, "modulus": abs(complex(re, 0.4))}]

    assert abs(complex(0.32, 0.4) - complex(0.22, 0.4)) == 0.1
    base = edited(edited(FIT, ["models", 0, "inv_roots_ar"], [*at(0.32), {"re": 0.2, "im": 0.0, "modulus": 0.2}]), ["models", 0, "inv_roots_ma"], at(0.22))
    paired = edited(base, ["models", 0, "cancelling_pairs"], [{"ar": 0, "ma": 0, "distance": 0.1}, {"ar": 1, "ma": 1, "distance": 0.1}])
    assert validate_fit(paired) == []
    unpaired = edited(base, ["models", 0, "cancelling_pairs"], [])
    assert any("gives 2 pairs with total distance 0.2" in p for p in validate_fit(unpaired)), validate_fit(unpaired)


def test_the_readers_tolerances_are_their_own_not_the_files():
    # A self-consistent file stating llf_tolerance 1.0 and a refit 0.5 from the grid's llf: the
    # stated value is refused, and the gap is judged at the reader's 1e-6 all the same.
    llf = FIT["models"][0]["information"]["llf"]
    loose = edited(edited(FIT, ["llf_tolerance"], 1.0), ["models", 0], lambda m: {**m, "grid_llf": llf - 0.5, "llf_gap": llf - (llf - 0.5)})
    problems = validate_fit(loose)
    assert "data.llf_tolerance: is 1.0, but this reader checks the refit's llf at 1e-06" in problems
    assert any("models[0].llf_gap" in p and "is outside llf_tolerance 1e-06" in p for p in problems), problems
    # cancel_distance 1.0 with the MA roots 0.3 from the AR roots, paired as a rule of 1.0 would.
    far = edited(edited(FIT, ["cancel_distance"], 1.0), ["models", 0], lambda m: {**m, "inv_roots_ma": [{"re": 0.3, "im": s * 0.1, "modulus": abs(complex(0.3, 0.1))} for s in (-1, 1)], "cancelling_pairs": [{"ar": i, "ma": i, "distance": abs(complex(0.3, s * 0.4) - complex(0.3, s * 0.1))} for i, s in ((0, -1), (1, 1))]})
    problems = validate_fit(far)
    assert "data.cancel_distance: is 1.0, but this reader pairs roots within 0.1" in problems
    assert any("above cancel_distance 0.1" in p for p in problems), problems


def test_the_arch_lm_bound_is_n_minus_lags_minus_ddof_and_inclusive(monkeypatch):
    # n = 39, lags 5: (n - 5) R^2 is at most 34, reached when R^2 = 1.
    at_bound = edited(FIT, [*DIAG, "arch_lm", 0], lambda r: {**r, "statistic": 34.0, "p_value": float(stats.chi2.sf(34.0, 5))})
    assert validate_fit(at_bound) == []
    # The ddof is the reader's own (payloads.ARCH_LM_DDOF = 0, a stated value is refused): the bound
    # takes it off, so with a ddof of 1 the same file is 34 against a bound of 33.
    monkeypatch.setattr(payloads, "ARCH_LM_DDOF", 1)
    problems = validate_fit(at_bound)
    assert any("arch_lm[0].statistic: is 34.0, but (n - lags - ddof) R^2 is at most n - lags - ddof = 33" in p for p in problems), problems


def test_a_ljung_box_q_may_stay_level_from_one_lag_to_the_next():
    # A running sum of terms >= 0 can add nothing: Q(20) equal to Q(10) is allowed (p-value scipy's).
    level = edited(FIT, [*BIC_DIAG, "ljung_box", 2], lambda r: {**r, "statistic": 17.9, "p_value": float(stats.chi2.sf(17.9, 19))})
    assert validate_fit(level) == []


def close_roots(k: int, start: float) -> list[dict]:
    """k real inverse roots 0.001 apart, from `start` down: sorted largest first, all within 0.1."""
    return [{"re": start - 0.001 * i, "im": 0.0, "modulus": start - 0.001 * i} for i in range(k)]


def timed(call, limit: float = 10.0):
    """call()'s result and the seconds it took. SIGALRM stops it with TimeoutError after `limit`
    seconds, so a matching that grows like 2^k fails the test instead of hanging the suite."""

    def stop(signum, frame):
        raise TimeoutError(f"still running after {limit} s")

    old = signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, limit)
    try:
        start = time.perf_counter()
        out = call()
        return out, time.perf_counter() - start
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def test_root_lists_longer_than_the_order_are_refused_at_once():
    # 30 close AR and 30 close MA roots for an order of (2, 1, 2), no pairs. Before the fix the count
    # was flagged but the roots kept, and the matching ran over 2^30 sets of MA roots (16 roots
    # each took 0.96 s, 21 took 58 s, 26 ran out of memory).
    data = edited(edited(edited(FIT, ["models", 0, "inv_roots_ar"], close_roots(30, 0.5)), ["models", 0, "inv_roots_ma"], close_roots(30, 0.4995)), ["models", 0, "cancelling_pairs"], [])
    problems, seconds = timed(lambda: validate_fit(data))
    assert problems == ["data.models[0].inv_roots_ar: has 30 roots, expected 3", "data.models[0].inv_roots_ma: has 30 roots, expected 2"]
    assert seconds < 2.0


def test_no_matching_is_run_on_roots_of_the_wrong_count():
    # Four AR and three MA roots within 0.1 of each other for an order of (3, 1, 2), no pairs. The
    # count is the only problem: the rule is not applied to roots the order does not have.
    data = edited(edited(edited(FIT, ["models", 0, "inv_roots_ar"], close_roots(4, 0.5)), ["models", 0, "inv_roots_ma"], close_roots(3, 0.4995)), ["models", 0, "cancelling_pairs"], [])
    assert validate_fit(data) == ["data.models[0].inv_roots_ar: has 4 roots, expected 3", "data.models[0].inv_roots_ma: has 3 roots, expected 2"]


def test_no_matching_is_run_past_max_pq_roots_when_the_order_is_unknown():
    # An order past the bound gives no count to check the roots against; 30 close roots a side
    # must still not reach the matching.
    data = edited(FIT, ["models", 0], lambda m: {**m, "order": [30, 1, 30], "inv_roots_ar": close_roots(30, 0.5), "inv_roots_ma": close_roots(30, 0.4995), "cancelling_pairs": []})
    problems, seconds = timed(lambda: validate_fit(data))
    assert problems == [
        "data.models[0].order[0]: expected an integer from 0 to 10, got 30",
        "data.models[0].order[2]: expected an integer from 0 to 10, got 30",
        "data.models[0].inv_roots_ar: has 30 roots, more than the 10 a reader takes",
        "data.models[0].inv_roots_ma: has 30 roots, more than the 10 a reader takes",
    ]
    assert seconds < 2.0


@pytest.mark.parametrize("p", [100_000_000, 2**32, 2**53 - 1])
def test_a_huge_order_gives_one_short_problem(p):
    # The order is bounded before the parameter names are built: no MemoryError, no giant message.
    problems = validate_fit(edited(FIT, ["models", 0, "order"], [p, 1, 2]))
    assert problems == [f"data.models[0].order[0]: expected an integer from 0 to 10, got {p}"]
    assert validate_residuals(edited(RESIDUALS, ["burn_excluded"], p), "aic") == [f"data.burn_excluded: expected an integer from 0 to 2, got {p}"]


def test_orders_at_the_bounds_are_not_refused_for_their_size():
    # p = q = 10 and d = 2 are the largest orders allowed; whatever else they break, not the bound.
    problems = validate_fit(edited(FIT, ["models", 1, "order"], [10, 2, 10]))
    assert problems and not any(".order" in p for p in problems), problems


RESIDUAL_CASES = [
    ("an outside flag against its band", ["acf", "rows", 0, "outside"], lambda v: not v, "band"),
    ("a band that is not z / sqrt(n)", ["acf_squared", "band"], lambda v: v * 1.01, "z / sqrt(n)"),
    ("unsorted QQ samples", ["qq", 0, "sample"], lambda v: v + 100.0, "sorted"),
    ("unsorted normal quantiles", ["qq", 1, "theoretical"], lambda v: v - 100.0, "sorted"),
]


@pytest.mark.parametrize(("name", "path", "change", "message"), RESIDUAL_CASES, ids=[c[0] for c in RESIDUAL_CASES])
def test_python_refuses_residuals_that_break_a_statistical_rule(name, path, change, message):
    data = edited(RESIDUALS, path, change)
    problems = validate_residuals(data, "aic")
    assert problems and any(message in p for p in problems), problems


def test_a_ljung_box_row_applied_against_its_lag_is_named_for_that_rule():
    # A shared rule (the corpus has it), but in every corpus case the df and p-value nulls also break,
    # so only the message shows that the applied rule itself fired.
    rows = FIT["models"][0]["diagnostics"]["ljung_box"]
    index = next(i for i, r in enumerate(rows) if r["applied"])
    data = edited(FIT, [*DIAG, "ljung_box", index, "applied"], False)
    assert any("applies exactly when lag" in p for p in validate_fit(data)), validate_fit(data)


def matching_residuals() -> dict[str, dict]:
    """One residuals payload per fit model, each made to agree with that model's diagnostics."""
    out = {}
    for model in FIT["models"]:
        dg = model["diagnostics"]
        data = copy.deepcopy(RESIDUALS)
        data.update(model_id=model["id"], n=dg["n"], burn_excluded=dg["burn_excluded"], nlags=FIT["diagnostic_settings"]["nlags"])
        data["acf"]["outside_count"] = dg["acf_outside_count"]
        data["acf_squared"]["outside_count"] = dg["acf_squared_outside_count"]
        out[f"residuals_{model['id']}"] = data
    return out


def test_fit_and_matching_residuals_agree():
    assert validate_fit_residuals(FIT, matching_residuals()) == []


@pytest.mark.parametrize(
    ("field", "change", "message"),
    [
        (["model_id"], "aic", "residuals_bic: model_id is 'aic', but fit.json says 'bic'"),
        (["n"], 7, "residuals_bic: n is 7, but fit.json says 39"),
        (["burn_excluded"], 2, "residuals_bic: burn_excluded is 2, but fit.json says 1"),
        (["nlags"], 40, "residuals_bic: nlags is 40, but fit.json says 50"),
        (["acf", "outside_count"], 0, "residuals_bic: acf.outside_count is 0, but fit.json says 1"),
        (["acf_squared", "outside_count"], 0, "residuals_bic: acf_squared.outside_count is 0, but fit.json says 1"),
    ],
    ids=["model_id", "n", "burn_excluded", "nlags", "acf count", "acf_squared count"],
)
def test_a_residuals_file_that_contradicts_fit_is_named(field, change, message):
    files = matching_residuals()
    files["residuals_bic"] = edited(files["residuals_bic"], field, change)
    assert validate_fit_residuals(FIT, files) == [message]


def test_a_missing_or_extra_residuals_file_is_named():
    files = matching_residuals()
    del files["residuals_course"]
    files["residuals_hqic"] = files["residuals_aic"]
    assert validate_fit_residuals(FIT, files) == ["residuals_course: missing, but fit has model 'course'", "residuals_hqic: fit.json has no model 'hqic'"]
    assert validate_fit_residuals("not a fit", {}) == []  # never raises; validate_fit reports the shape
