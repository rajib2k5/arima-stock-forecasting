"""The rules of validate_forecast and validate_evaluation that only Python applies (contract.md 3.9 and
3.10, "What each reader checks (1.5.0)"), the special functions behind them, and the checks across
files (validate_forecast_fit, validate_forecast_evaluation). Each recomputes a number from others or
compares one with alpha, which the app never does (ADR-0001), so these cases cannot go in the shared
corpus, whose verdicts both readers must reach. The shared rules are in
app/src/test/fixtures/payload_cases.json.

The bases are the corpus's fixtures (made-up values: the production code run on a simulated series);
every case changes one value, names the rule, and checks that the base had no problem before.
"""

from __future__ import annotations

import copy
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from arima_forecasting import payloads
from arima_forecasting.payloads import _t_sf, kupiec_lr, validate_evaluation, validate_forecast, validate_forecast_evaluation, validate_forecast_fit

FIXTURES = Path(__file__).resolve().parent.parent / "app" / "src" / "test" / "fixtures"
FORECASTS = {f"forecast_{m}_{meth}": json.loads((FIXTURES / f"forecast_{m}_{meth}.data.json").read_text(encoding="utf-8")) for m, meth in payloads.FORECASTS}
STATIC = FORECASTS["forecast_aic_static"]
WALK = FORECASTS["forecast_aic_walk_forward"]
REFIT = FORECASTS["forecast_aic_refit"]
EVALUATION = json.loads((FIXTURES / "evaluation.data.json").read_text(encoding="utf-8"))


def edited(base: dict, path: list, change) -> dict:
    data = copy.deepcopy(base)
    *parents, last = path
    node = data
    for key in parents:
        node = node[key]
    node[last] = change(node[last]) if callable(change) else change
    return data


def test_the_bases_are_valid():
    for name, data in FORECASTS.items():
        _, model, method = name.split("_", 2)
        assert validate_forecast(data, model, method) == [], name
    assert validate_evaluation(EVALUATION) == []
    assert validate_forecast_evaluation(EVALUATION, FORECASTS) == []


ROW = ["windows", 0, "rows", 1]
STATIC_ROW = ["windows", 1, "rows", 3]

FORECAST_CASES = [
    ("the median is not exp(mean_log)", WALK, [*ROW, "median_usd"], lambda v: v * 1.001, "but exp(mean_log) is"),
    # The course's mistake 4 as data: the mean written as the median.
    ("the mean is the median", WALK, ROW, lambda r: {**r, "mean_usd": r["median_usd"]}, "but exp(mean_log + sd_log^2 / 2) is"),
    ("a normal bound off", WALK, [*ROW, "upper_95_usd"], lambda v: v * 1.0001, "upper_95_usd: is"),
    ("a t bound from the normal multiplier", WALK, ROW, lambda r: {**r, "t_lower_80_usd": r["lower_80_usd"]}, "t_lower_80_usd: is"),
    ("actual_usd is not exp(actual_log)", WALK, [*ROW, "actual_usd"], lambda v: v + 0.01, "but exp(actual_log) is"),
    ("the origin's dollars are not exp(log_close)", STATIC, ["windows", 1, "origin", "close_usd"], lambda v: v + 0.01, "but exp(log_close) is"),
    # sd_log falling on a static path (row 3 below row 2), its dollars recomputed so only this rule breaks.
    ("a static path's sd_log falls", STATIC, STATIC_ROW, None, "cannot fall as h grows"),
    ("t_scale is not sqrt((df - 2) / df)", STATIC, ["intervals", "t_scale"], lambda v: v * 1.001, "sqrt((t_df - 2) / t_df)"),
    ("a t multiplier is not quantile x scale", STATIC, ["intervals", "t_multiplier", 1], lambda v: v * 1.001, "t_quantile x t_scale"),
    ("a t quantile that is the normal's", STATIC, ["intervals", "t_quantile", 1], 1.959963984540054, "puts"),
    # Past T_ASYMPTOTIC_DF the quantile is checked by the Cornish-Fisher expansion: the base's quantiles are 4.5 df's.
    ("t quantiles of another df past T_ASYMPTOTIC_DF", STATIC, ["t_df"], 2e6, "(Cornish-Fisher)"),
    ("a refit's sigma2 of 0", REFIT, ["refits", 0, "params", 3, "value"], 0.0, "sigma2 is a variance"),
]


def _falling(data: dict, factor: float = 0.9) -> dict:
    """STATIC with row 3 of the oos path given row 2's sd_log times `factor`, and its dollars recomputed."""
    rows = data["windows"][1]["rows"]
    row = rows[3]
    sd = rows[2]["sd_log"] * factor
    mu = row["mean_log"]
    z, k = payloads.NORMAL_Z, data["intervals"]["t_multiplier"]
    row.update(sd_log=sd, mean_usd=math.exp(mu + sd * sd / 2))
    for field, key, i, sign in payloads._BOUNDS:
        row[field] = math.exp(mu + sign * (z if key == "normal_z" else k)[i] * sd)
    return data


@pytest.mark.parametrize(("name", "base", "path", "change", "message"), FORECAST_CASES, ids=[c[0] for c in FORECAST_CASES])
def test_python_refuses_a_forecast_that_breaks_a_numeric_rule(name, base, path, change, message):
    data = _falling(copy.deepcopy(base)) if change is None else edited(base, path, change)
    assert data != base, f"the case {name!r} changed nothing in the base"
    model, method = data["model_id"], data["method"]
    problems = validate_forecast(data, model, method)
    assert any(message in p for p in problems), problems


def test_a_falling_sd_is_fine_on_a_one_step_path():
    # A one-step forecast's spread follows the state, not the horizon: it may fall. Only the static rule applies.
    data = _falling(copy.deepcopy(STATIC))
    data.update(method="walk_forward", kind="one_step")
    assert validate_forecast(data, "aic", "walk_forward") == []


DM = ["dm", 0]
COVERAGE_ONE_STEP = ["coverage", 8]

EVALUATION_CASES = [
    ("a ratio that is not metric / random walk", ["metrics", 0, "ratio_to_rw", "usd_median", "rmse"], lambda v: v * 1.000001, "the random walk's"),
    ("an RMSE below its MAE", ["random_walk", 0, "log"], lambda b: {**b, "rmse": b["mae"] * 0.99}, "below the MAE"),
    ("a negative MAPE", ["random_walk", 1, "usd", "mape_pct"], -1.0, "must be >= 0"),
    ("a back-transform max below its mean", ["metrics", 1, "back_transform"], lambda b: {**b, "max_pct": b["mean_pct"] * 0.5}, "the largest gap is at least the mean one"),
    ("a DM statistic that is not mean_diff / sqrt(var_diff / n)", [*DM, "statistic"], lambda v: v * 1.001, "mean_diff / sqrt(var_diff / n)"),
    # The DM row as if computed with gamma_0's divisor n - 1: its statistic, factor, p and verdict all
    # consistent with that variance, so only the tie to var_diff breaks.
    ("DM without the HLN correction (factor 1)", DM, lambda r: {**r, "hln_factor": 1.0, "statistic_hln": r["statistic"], "p_value": float(2 * stats.t.sf(abs(r["statistic"]), r["df"]))}, "sqrt((n + 1 - 2h + h (h - 1) / n) / n)"),
    ("statistic_hln that is not statistic x factor", [*DM, "statistic_hln"], lambda v: v * 1.001, "statistic x hln_factor"),
    ("a DM p-value that is not the t tail", [*DM, "p_value"], lambda v: v * 1.01, "2 P(T > |statistic_hln|)"),
    ("a DM p-value from the normal, not the t", DM, lambda r: {**r, "p_value": float(2 * stats.norm.sf(abs(r["statistic_hln"])))}, "2 P(T > |statistic_hln|)"),
    ("a DM p-value of 0 beside a moderate statistic", [*DM, "p_value"], 0.0, "above the underflow floor"),
    ("a DM verdict against its p-value", [*DM, "verdict"], "worse_than_rw", "give 'no_difference'"),
    ("same_as_rw for forecasts that differ", DM, lambda r: {**r, "statistic": None, "statistic_hln": None, "p_value": None, "verdict": "same_as_rw"}, "more than same_tolerance"),
    ("a tested row for forecasts that are the random walk's", [*DM, "max_forecast_gap"], 1e-9, "'same_as_rw'"),
    ("a coverage rate that is not inside / n", [*COVERAGE_ONE_STEP, "rate"], lambda v: v + 0.01, "inside / n"),
    ("a Kupiec LR that is not the formula", [*COVERAGE_ONE_STEP], lambda r: {**r, "lr": 1.0, "p_value": float(stats.chi2.sf(1.0, 1))}, "Kupiec's LR"),
    ("a coverage p-value that is not the chi-squared tail", ["coverage", 12, "p_value"], lambda v: v * 0.9, "Kupiec LR statistic"),
    ("a coverage verdict against its p-value", [*COVERAGE_ONE_STEP, "verdict"], "too_wide", "give 'consistent'"),
]


@pytest.mark.parametrize(("name", "path", "change", "message"), EVALUATION_CASES, ids=[c[0] for c in EVALUATION_CASES])
def test_python_refuses_an_evaluation_that_breaks_a_numeric_rule(name, path, change, message):
    data = edited(EVALUATION, path, change)
    assert data != EVALUATION, f"the case {name!r} changed nothing in the base"
    problems = validate_evaluation(data)
    assert any(message in p for p in problems), problems


def test_the_coverage_verdict_follows_the_rate_side():
    # Row 12: 17 of 20 at 0.8. Rewrite it as 20 of 20 and 10 of 20 with their own LR and p: both
    # rejected at 5% (p 0.0118 and 0.0101), one too wide, one too narrow; each verdict swapped is refused.
    for inside, verdict, wrong in ((20, "too_wide", "too_narrow"), (10, "too_narrow", "too_wide")):
        lr = kupiec_lr(20, inside, 0.8)
        row = {**EVALUATION["coverage"][12], "inside": inside, "rate": inside / 20, "lr": lr, "p_value": float(stats.chi2.sf(lr, 1))}
        assert row["p_value"] < 0.05
        assert validate_evaluation(edited(EVALUATION, ["coverage", 12], {**row, "verdict": verdict})) == []
        assert any(f"give {verdict!r}" in p for p in validate_evaluation(edited(EVALUATION, ["coverage", 12], {**row, "verdict": wrong})))


def test_a_dm_row_reaches_each_verdict_by_its_p_value_and_sign():
    # mean_diff -1e-4 or +1e-4 with the base's variance: the statistic, its HLN version and the p-value
    # recomputed; at n = 5 a |DM*| of 2.78 or more is significant at 5% two-sided (t on 4 df).
    base = EVALUATION["dm"][0]
    for mean_diff, var_diff, verdict in ((-1e-4, 1e-10, "beats_rw"), (1e-4, 1e-10, "worse_than_rw"), (1e-4, 1e-8, "no_difference")):
        statistic = mean_diff / math.sqrt(var_diff / 5)
        corrected = statistic * base["hln_factor"]
        row = {**base, "mean_diff": mean_diff, "var_diff": var_diff, "statistic": statistic, "statistic_hln": corrected, "p_value": float(2 * stats.t.sf(abs(corrected), 4)), "verdict": verdict}
        assert validate_evaluation(edited(EVALUATION, DM, row)) == [], verdict
        for other in set(payloads.DM_VERDICTS) - {verdict, "same_as_rw"}:
            assert validate_evaluation(edited(EVALUATION, DM, {**row, "verdict": other})), (verdict, other)


def test_a_ratio_over_a_zero_random_walk_metric_is_a_problem_not_a_crash():
    data = edited(EVALUATION, ["random_walk", 0, "log", "mae"], 0.0)
    assert any("so there is no ratio" in p for p in validate_evaluation(data))


# --- each tolerance, just inside and just past it ------------------------------------------------------------
# A tolerance loosened (1e-9 to 1e-3, say) passed every case above, whose values were off by 0.1% or
# more. Each test here puts one value just past its tolerance (refused, and nothing else is) and one
# just inside it (accepted). The tolerances are written here as the contract states them, not read
# from payloads, so a loosened constant cannot move the test with it.
REL, P_REL, T_CDF_TOLERANCE, SIGMA2_REL = 1e-9, 1e-9, 1e-10, 1e-4


def test_a_static_sd_log_may_fall_by_rel_and_no_more():
    rel = REL
    assert validate_forecast(_falling(copy.deepcopy(STATIC), 1 - rel / 2), "aic", "static") == []
    problems = validate_forecast(_falling(copy.deepcopy(STATIC), 1 - 2 * rel), "aic", "static")
    assert len(problems) == 1 and problems[0].startswith("data.windows[1].rows[3].sd_log: is") and "cannot fall as h grows" in problems[0], problems


def test_an_rmse_may_sit_below_its_mae_by_rel_and_no_more():
    mae = EVALUATION["metrics"][0]["log"]["mae"]
    for times, ok in ((1 - REL / 2, True), (1 - 2 * REL, False)):
        data = copy.deepcopy(EVALUATION)
        _metric(data, 0, "log", "rmse", mae * times)
        problems = validate_evaluation(data)
        assert (problems == []) if ok else (len(problems) == 1 and problems[0].startswith("data.metrics[0].log.rmse: is") and "below the MAE" in problems[0]), problems


def test_the_hln_factor_is_compared_at_rel():
    # The review's case: at n = 689 a factor of 1.0 (no correction) is 7.3e-4 from sqrt(688 / 689), so a
    # tolerance of 1e-3 took it. Here the factor moves by 2 _REL (refused) and _REL / 2 (accepted), with
    # statistic_hln and the p-value recomputed from it.
    for times, ok in ((1 + REL / 2, True), (1 + 2 * REL, False)):
        data = copy.deepcopy(EVALUATION)
        row = data["dm"][0]
        row["hln_factor"] *= times
        row["statistic_hln"] = row["statistic"] * row["hln_factor"]
        row["p_value"] = float(2 * stats.t.sf(abs(row["statistic_hln"]), row["df"]))
        problems = validate_evaluation(data)
        assert (problems == []) if ok else (len(problems) == 1 and problems[0].startswith("data.dm[0].hln_factor: is")), problems
    assert abs(1 - math.sqrt(688 / 689)) > REL * 1e5  # the review's factor 1.0 is far past _REL


def test_a_t_quantile_is_compared_at_the_cdf_tolerance():
    # The 95% quantile moved so that the t's CDF at it is off by 10 and by 0.5 T_CDF_TOLERANCE; its
    # multiplier and every t bound follow, so only the quantile's own check can refuse it.
    from arima_forecasting.forecasting import forecast_rows

    df = STATIC["t_df"]
    q = STATIC["intervals"]["t_quantile"][1]
    for off, ok in ((0.5 * T_CDF_TOLERANCE, True), (10 * T_CDF_TOLERANCE, False)):
        moved = q + off / float(stats.t.pdf(q, df))
        assert abs(float(stats.t.cdf(moved, df)) - 0.975 - off) < 0.01 * off
        data = copy.deepcopy(STATIC)
        data["intervals"]["t_quantile"][1] = moved
        data["intervals"]["t_multiplier"][1] = moved * data["intervals"]["t_scale"]
        for w in data["windows"]:
            w["rows"] = forecast_rows([r["date"] for r in w["rows"]], np.array([r["actual_log"] for r in w["rows"]]), np.array([r["actual_usd"] for r in w["rows"]]), np.array([r["mean_log"] for r in w["rows"]]), np.array([r["sd_log"] ** 2 for r in w["rows"]]), data["intervals"])
        problems = validate_forecast(data, "aic", "static")
        assert (problems == []) if ok else (len(problems) == 1 and problems[0].startswith("data.intervals.t_quantile[1]: is")), problems


@pytest.mark.parametrize("which", ["dm", "coverage"])
def test_a_p_value_is_compared_at_p_rel(which):
    path = [*DM, "p_value"] if which == "dm" else ["coverage", 12, "p_value"]
    for times, ok in ((1 + P_REL / 2, True), (1 + 2 * P_REL, False)):
        problems = validate_evaluation(edited(EVALUATION, path, lambda v: v * times))
        at = "data.dm[0].p_value: is" if which == "dm" else "data.coverage[12].p_value: is"
        assert (problems == []) if ok else (len(problems) == 1 and problems[0].startswith(at)), problems


def test_a_dm_p_value_of_0_needs_a_tail_below_the_underflow_floor():
    # DM* of 1e7 on 4 df: a tail of about 1e-28, too small for any test to matter but far above
    # P_FLOOR, so a 0 is refused (a floor of 1e-10 took it). DM* of 1e80 on 19 df has a tail below
    # 1e-300, which scipy writes as 0: accepted.
    for i, corrected in ((0, 1e7), (2, 1e80)):
        base = EVALUATION["dm"][i]
        tail = float(2 * stats.t.sf(corrected, base["df"]))
        statistic = corrected / base["hln_factor"]
        var_diff = 1e-10
        row = {**base, "var_diff": var_diff, "statistic": statistic, "statistic_hln": corrected, "mean_diff": statistic * math.sqrt(var_diff / base["n"]), "p_value": 0.0, "verdict": "worse_than_rw"}
        problems = validate_evaluation(edited(EVALUATION, ["dm", i], row))
        if i == 0:
            assert 1e-300 < tail < 1e-20
            assert len(problems) == 1 and problems[0].startswith("data.dm[0].p_value: is 0, but 2 P(T > |") and "above the underflow floor" in problems[0], problems
        else:
            assert tail == 0.0 and problems == [], problems


# --- the special functions -------------------------------------------------------------------------------------


def test_the_t_tail_is_scipys_and_the_closed_forms():
    # Degrees of freedom of the DM rows (n - 1 up to MAX_ROWS - 1) and a made-up one like the t fits' (non-integer, near 3).
    for df in (1, 2, 3.3125, 4, 10, 226, 688, 9999):
        for i in range(1, 400):
            x = i / 8
            want = float(stats.t.sf(x, df))
            assert _t_sf(x, df) == pytest.approx(want, rel=1e-10, abs=1e-300), (df, x)
            assert _t_sf(-x, df) == pytest.approx(1 - want, rel=1e-12), (df, x)
    # Closed forms where scipy loses digits near 0: Cauchy (1 df) 1/2 - atan(x)/pi, and 2 df 1/2 - x / (2 sqrt(2 + x^2)).
    for x in (1e-12, 1e-8, 1e-4):
        assert _t_sf(x, 1) == pytest.approx(0.5 - math.atan(x) / math.pi, rel=1e-15)
        assert _t_sf(x, 2) == pytest.approx(0.5 - x / (2 * math.sqrt(2 + x * x)), rel=1e-15)


def test_the_t_tail_takes_0_subnormal_and_huge_arguments():
    for df in (1, 4, 9999, 1e6):
        assert _t_sf(0.0, df) == 0.5
        assert _t_sf(5e-324, df) == 0.5  # its square underflows to 0
        assert _t_sf(1e200, df) == 0.0  # its square overflows: the tail is 0
        assert _t_sf(math.inf, df) == 0.0
        assert _t_sf(-math.inf, df) == 1.0
    assert math.isnan(_t_sf(math.nan, 4))
    # A tail below the smallest double is 0, and a p-value of 0 is then taken (P_FLOOR).
    assert _t_sf(1e100, 4) == 0.0
    t0 = time.perf_counter()
    for _ in range(1000):
        _t_sf(2.3, 9999)
    assert time.perf_counter() - t0 < 1.0


def test_the_t_quantile_check_holds_at_the_bounds_of_df():
    # One ulp above 2 (the scale is about 1.5e-8), on each side of T_ASYMPTOTIC_DF, and at the df a
    # near-normal series gives (scipy's t.fit can return more than 1e6), the producer's numbers pass.
    from arima_forecasting.forecasting import t_multipliers

    below = math.nextafter(payloads.T_ASYMPTOTIC_DF, 0.0)
    for df in (2.0000000000000004, 3.3125, below, payloads.T_ASYMPTOTIC_DF, 1e6, 1e12, 1e300):
        t = t_multipliers(df)
        problems = []
        data = edited(STATIC, ["intervals"], {"levels": [0.8, 0.95], "normal_z": list(payloads.NORMAL_Z), **t})
        data["t_df"] = df
        problems = [p for p in validate_forecast(data, "aic", "static") if "intervals" in p or "t_df" in p]
        assert problems == [], (df, problems)


def test_the_cornish_fisher_quantile_is_scipys_for_a_large_df():
    for df in (1e3, 1e4, 1e5, 1e8, 1e12, 1e300):
        for z, p in zip(payloads.NORMAL_Z, (0.9, 0.975)):
            assert payloads._t_quantile_expansion(z, df) == pytest.approx(float(stats.t.ppf(p, df)), rel=1e-15)


def test_kupiec_matches_the_producer_and_scipy():
    from arima_forecasting.evaluation import kupiec

    for n, inside, level in ((227, 217, 0.8), (689, 655, 0.95), (5, 0, 0.8), (5, 5, 0.95), (10, 8, 0.8)):
        lr = kupiec_lr(n, inside, level)
        assert (lr, float(stats.chi2.sf(lr, 1))) == pytest.approx(kupiec(n, inside, level), rel=1e-15)
        assert lr >= 0 and math.copysign(1.0, lr) == 1.0


# --- bounded work -----------------------------------------------------------------------------------------------


def test_no_input_makes_a_reader_slow():
    # A refits list of a million entries, a coverage list of a million rows, a window of MAX_ROWS rows.
    big_refits = edited(REFIT, ["refits"], [REFIT["refits"][0]] * 1_000_000)
    big_coverage = edited(EVALUATION, ["coverage"], [EVALUATION["coverage"][0]] * 1_000_000)
    row = WALK["windows"][1]["rows"][0]
    dates = [(date(2030, 1, 1) + timedelta(days=i)).isoformat() for i in range(payloads.MAX_ROWS)]
    rows = [{**row, "date": d} for d in dates]
    full = edited(WALK, ["windows", 1], lambda w: {**w, "n": payloads.MAX_ROWS, "start": rows[0]["date"], "end": rows[-1]["date"], "rows": rows})
    for data, check, expected in (
        (big_refits, lambda d: validate_forecast(d, "aic", "refit"), "has 1000000 entries"),
        (big_coverage, validate_evaluation, "has 1000000 rows"),
        (full, lambda d: validate_forecast(d, "aic", "walk_forward"), None),
    ):
        t0 = time.perf_counter()
        problems = check(data)
        assert time.perf_counter() - t0 < 1.0
        assert sum(len(p) for p in problems) < 10_000
        assert (problems == []) if expected is None else (len(problems) == 1 and expected in problems[0]), problems[:3]


# --- across files --------------------------------------------------------------------------------------------------

# The training estimates of the fixtures' three models (made-up: fitted to the simulated series the
# fixtures were built from). Each walk-forward fixture row's sd_log^2 is its model's sigma2 to 3.4e-7.
FIT_PARAMS = {
    "aic": [("drift", 0.002938203997194112), ("ar.L1", 0.18838571336126542), ("ma.L1", -0.034536495686331964), ("sigma2", 0.0003594876328532193)],
    "bic": [("ar.L1", 0.16188337595839825), ("sigma2", 0.0003656218535403076)],
    "course": [("ma.L1", 0.1558605223489943), ("sigma2", 0.00036581340240569296)],
}
FIT = {
    "n_train": 80,
    "models": [
        {"id": data["model_id"], "label": data["label"], "order": data["order"], "trend": data["trend"], "params": [{"name": n, "value": v} for n, v in FIT_PARAMS[data["model_id"]]]}
        for data in (STATIC, FORECASTS["forecast_bic_static"], FORECASTS["forecast_course_static"])
    ],
}
RESIDUALS = {f"residuals_{m}": {"t_fit": {"df": FORECASTS[f"forecast_{m}_static"]["t_df"]}} for m in ("aic", "bic", "course")}


def test_the_forecasts_agree_with_the_fit_and_its_residual_files():
    assert validate_forecast_fit(FIT, RESIDUALS, FORECASTS) == []
    other = copy.deepcopy(FIT)
    other["models"][1]["order"] = [2, 1, 2]
    assert any("forecast_bic_walk_forward: order is [1, 1, 0], but fit.json says [2, 1, 2]" in p for p in validate_forecast_fit(other, RESIDUALS, FORECASTS))
    residuals = copy.deepcopy(RESIDUALS)
    residuals["residuals_course"]["t_fit"]["df"] = 3.0
    assert any("forecast_course_static: t_df is 3.75, but residuals_course.json's t fit has df 3.0" in p for p in validate_forecast_fit(FIT, residuals, FORECASTS))
    shifted = copy.deepcopy(FIT)
    shifted["n_train"] = 79
    assert any("refits[0].n_obs is 101, but fit.n_train + 21 is 100" in p for p in validate_forecast_fit(shifted, RESIDUALS, FORECASTS))
    missing = {k: v for k, v in FORECASTS.items() if k != "forecast_aic_refit"}
    assert "forecast_aic_refit: missing" in validate_forecast_fit(FIT, RESIDUALS, missing)


def _metric(data: dict, i: int, block: str, metric: str, value: float) -> None:
    """metrics[i].<block>.<metric> set to `value`, with its ratio to the random walk kept the quotient
    validate_evaluation requires, so the file stays valid on its own."""
    row = data["metrics"][i]
    rw = next(r for r in data["random_walk"] if (r["kind"], r["window"]) == (payloads.FORECAST_KINDS[row["method"]], row["window"]))
    row[block][metric] = value
    row["ratio_to_rw"][block][metric] = value / rw["log" if block == "log" else "usd"][metric]


def _offset_rw(data: dict) -> None:
    """The one-step test window's random-walk log MAE times 1.01, every ratio over it kept a quotient."""
    data["random_walk"][2]["log"]["mae"] *= 1.01
    for row in data["metrics"]:
        if payloads.FORECAST_KINDS[row["method"]] == "one_step" and row["window"] == "test":
            row["ratio_to_rw"]["log"]["mae"] = row["log"]["mae"] / data["random_walk"][2]["log"]["mae"]


def _dm(data: dict, i: int, **change: float) -> None:
    """DM row i with `change` applied and its statistic, HLN statistic and p-value recomputed (scipy)."""
    row = data["dm"][i]
    row.update(change)
    row["statistic"] = row["mean_diff"] / math.sqrt(row["var_diff"] / row["n"])
    row["statistic_hln"] = row["statistic"] * row["hln_factor"]
    row["p_value"] = float(2 * stats.t.sf(abs(row["statistic_hln"]), row["df"]))


def _one_fewer_inside(data: dict) -> None:
    """Coverage row 12 (17 of 20 at 0.8) as 16 of 20, with its rate, LR and p-value (scipy): 16 / 20 is the level."""
    row = data["coverage"][12]
    row.update(inside=16, rate=16 / 20, lr=kupiec_lr(20, 16, 0.8))
    row["p_value"] = float(stats.chi2.sf(row["lr"], 1))


# Each case keeps the evaluation valid on its own (checked below), so only the tie to the forecast rows
# can refuse it: validate_forecast_evaluation leaves out a file that is not.
CROSS_CASES = [
    ("a model metric", lambda d: _metric(d, 2, "log", "rmse", d["metrics"][2]["log"]["rmse"] * 1.000001), "metrics aic walk_forward test log.rmse"),
    ("a mean-based dollar metric from the median", lambda d: [_metric(d, 2, "usd_mean", k, d["metrics"][2]["usd_median"][k]) for k in ("rmse", "mae", "mape_pct")], "usd_mean.rmse"),
    ("a random-walk metric offset by one day", _offset_rw, "random_walk one_step test log.mae"),
    ("a DM mean_diff", lambda d: _dm(d, 0, mean_diff=d["dm"][0]["mean_diff"] * 1.000001), "mean_diff"),
    ("a DM var_diff with divisor n - 1", lambda d: _dm(d, 0, var_diff=d["dm"][0]["var_diff"] * 5 / 4), "var_diff"),
    ("a DM max_forecast_gap", lambda d: d["dm"][0].update(max_forecast_gap=d["dm"][0]["max_forecast_gap"] * 2), "max_forecast_gap"),
    ("a coverage count off by one", _one_fewer_inside, "inside is 16, but 17 rows lie inside"),
    ("a back-transform gap", lambda d: d["metrics"][0]["back_transform"].update(max_pct=d["metrics"][0]["back_transform"]["max_pct"] * 1.001), "back_transform.max_pct"),
    ("a window's end", lambda d: d["windows"][0].update(end="2021-06-24"), "windows 'test'.end"),
    ("a model's t_df", lambda d: d["models"][1].update(t_df=6.0), "models 'bic'.t_df"),
]


@pytest.mark.parametrize(("name", "change", "message"), CROSS_CASES, ids=[c[0] for c in CROSS_CASES])
def test_python_refuses_an_evaluation_the_forecast_rows_do_not_give(name, change, message):
    data = copy.deepcopy(EVALUATION)
    change(data)
    assert data != EVALUATION
    assert validate_evaluation(data) == []
    problems = validate_forecast_evaluation(data, FORECASTS)
    assert any(message in p for p in problems), problems


def test_a_coverage_count_uses_the_closed_interval_of_the_file_multipliers():
    # Put one actual exactly on its normal 80% bound: still inside, so the count stands; one ulp
    # beyond it the count drops by one and the evaluation is refused.
    forecasts = copy.deepcopy(FORECASTS)
    rows = forecasts["forecast_aic_walk_forward"]["windows"][1]["rows"]
    inside_before = EVALUATION["coverage"][12]["inside"]
    row = next(r for r in rows if abs(r["actual_log"] - r["mean_log"]) <= payloads.NORMAL_Z[0] * r["sd_log"])
    bound = row["mean_log"] + payloads.NORMAL_Z[0] * row["sd_log"]
    # actual_usd follows actual_log, so the file stays valid on its own and is not left out.
    row.update(actual_log=bound, actual_usd=math.exp(bound))

    def count_problems() -> list[str]:
        assert validate_forecast(forecasts["forecast_aic_walk_forward"], "aic", "walk_forward") == []
        return [p for p in validate_forecast_evaluation(EVALUATION, forecasts) if "coverage aic walk_forward oos normal 0.8 inside" in p]

    assert count_problems() == []
    row.update(actual_log=math.nextafter(bound, math.inf), actual_usd=math.exp(math.nextafter(bound, math.inf)))
    assert any(f"inside is {inside_before}, but {inside_before - 1} rows" in p for p in count_problems())


# --- the review's holes, each pinned ----------------------------------------------------------------------------


def test_a_dollar_value_cannot_hide_behind_an_overflow():
    # mean_log 710 makes exp overflow to inf; a recomputed inf once matched any stored number.
    data = edited(WALK, ["windows", 1, "rows", 5, "mean_log"], 710.0)
    problems = validate_forecast(data, "aic", "walk_forward")
    assert any("median_usd: is" in p and "but exp(mean_log) is inf" in p for p in problems), problems
    assert not payloads._close(183.18, math.inf) and not payloads._near(183.18, math.inf) and not payloads._close(math.inf, math.inf)


def test_every_forecast_file_must_describe_the_same_days_and_actuals():
    # bic's oos actuals moved one day earlier, each file still valid alone and the evaluation
    # rebuilt from them: only the tie across files sees it.
    from arima_forecasting.evaluation import evaluation_payload

    forecasts = copy.deepcopy(FORECASTS)
    rows = forecasts["forecast_bic_walk_forward"]["windows"][1]["rows"]
    actuals = [(r["actual_log"], r["actual_usd"]) for r in rows]
    for r, (a, u) in zip(rows, actuals[1:] + actuals[-1:]):
        r["actual_log"], r["actual_usd"] = a, u
    assert validate_forecast(forecasts["forecast_bic_walk_forward"], "bic", "walk_forward") == []
    rebuilt = evaluation_payload(forecasts, FIT)
    assert validate_evaluation(rebuilt) == []
    problems = validate_forecast_evaluation(rebuilt, forecasts)
    assert problems == ["forecast_bic_walk_forward: window 'oos' differs from forecast_aic_static's in its rows (date, actual_log, actual_usd): every forecast file describes the same days and actuals"]


def test_the_forecasts_must_be_the_rows_of_prices():
    # A prices payload made from the fixtures' own rows agrees; one close moved does not.
    rows = []
    for w in STATIC["windows"]:
        origin = w["origin"]
        if not rows or rows[-1]["date"] != origin["date"]:
            rows.append({"date": origin["date"], "log_close": origin["log_close"], "close_usd": origin["close_usd"], "segment": "train"})
        rows += [{"date": r["date"], "log_close": r["actual_log"], "close_usd": r["actual_usd"], "segment": w["id"]} for r in w["rows"]]
    rows[-1 - len(STATIC["windows"][1]["rows"])]["segment"] = "test"  # the last test day is the oos origin
    prices = {"rows": rows, "splits": _prices_of_the_fixtures()["splits"]}
    assert payloads.validate_forecast_prices(prices, FORECASTS) == []
    moved = copy.deepcopy(prices)
    moved["rows"][-1]["close_usd"] += 0.01
    problems = payloads.validate_forecast_prices(moved, FORECASTS)
    assert len(problems) == 7 and all("window 'oos' does not match prices.json in its rows" in p for p in problems), problems


@pytest.mark.parametrize("case", ["a mean_log of -800 with sd_log 40", "an actual of exp(-800) = 0 dollars"])
def test_the_cross_file_check_reports_instead_of_raising(case):
    from arima_forecasting.forecasting import forecast_rows

    forecasts = copy.deepcopy(FORECASTS)
    for name, data in forecasts.items():
        w = data["windows"][1]
        r = w["rows"][4]
        if case.startswith("a mean_log"):
            mean, var, a_log, a_usd = -800.0, 1600.0, r["actual_log"], r["actual_usd"]
        else:
            mean, var, a_log, a_usd = r["mean_log"], r["sd_log"] ** 2, -800.0, 0.0
        (new,) = forecast_rows([r["date"]], np.array([a_log]), np.array([a_usd]), np.array([mean]), np.array([var]), data["intervals"])
        w["rows"][4] = new
        if data["kind"] == "multi_step" and case.startswith("a mean_log"):
            continue
        assert validate_forecast(data, data["model_id"], data["method"]) == [], (name, validate_forecast(data, data["model_id"], data["method"])[:2])
    problems = validate_forecast_evaluation(EVALUATION, forecasts)  # must not raise
    assert problems and all(isinstance(p, str) for p in problems)


@pytest.mark.parametrize(("name", "path", "value"), [
    ("forecast_aic_walk_forward", ["windows", 0], "test"),  # raised AttributeError
    ("forecast_aic_static", ["intervals", "normal_z"], [1.2815515655446004]),  # raised IndexError
    ("forecast_bic_walk_forward", ["windows", 1, "rows", 0], 7),
])
def test_a_forecast_file_invalid_alone_is_named_and_left_out_of_the_checks_across_files(name, path, value):
    forecasts = copy.deepcopy(FORECASTS)
    forecasts[name] = edited(forecasts[name], path, value)
    problems = validate_forecast_evaluation(EVALUATION, forecasts)  # must not raise
    assert f"{name}: not valid on its own (validate_forecast), so the checks across files leave it out" in problems
    assert not any(p.startswith(f"{name}: window") for p in problems), problems


def test_an_evaluation_invalid_alone_is_named_and_not_checked_against_the_rows():
    data = edited(EVALUATION, ["metrics", 0, "log"], [1.0])  # `.get` on a list raised AttributeError
    assert validate_forecast_evaluation(data, FORECASTS) == ["evaluation: not valid on its own (validate_evaluation), so it is not checked against the forecast rows"]


def test_the_checks_across_files_never_raise_on_a_malformed_file():
    # Every node down to depth 5 (the first three items of each list) of each forecast file and the
    # evaluation, replaced in turn by a value of another type: no input may raise.
    def paths(node, prefix=(), depth=0):
        if depth > 5:
            return
        items = node.items() if isinstance(node, dict) else enumerate(node[:3]) if isinstance(node, list) else []
        for key, child in items:
            yield (*prefix, key)
            yield from paths(child, (*prefix, key), depth + 1)

    tried = 0
    for name in [*FORECASTS, "evaluation"]:
        base = EVALUATION if name == "evaluation" else FORECASTS[name]
        for path in paths(base):
            for value in ("x", 7, None, [1], {"a": 1}):
                data = edited(base, list(path), value)
                forecasts = FORECASTS if name == "evaluation" else {**FORECASTS, name: data}
                validate_forecast_evaluation(data if name == "evaluation" else EVALUATION, forecasts)
                validate_forecast_fit(FIT, RESIDUALS, forecasts)
                payloads.validate_forecast_prices(_prices_of_the_fixtures(), forecasts)
                tried += 1
    assert tried > 5000


def test_a_dm_df_past_the_row_bound_is_not_given_to_the_t_tail(monkeypatch):
    # n and df are tied to the window's n only when the windows are valid; with them refused, a DM row
    # may state any n. The t tail is not evaluated past MAX_ROWS - 1 df, where it is not accurate, and
    # the file is refused by its windows alone.
    seen = []
    original = payloads._t_sf
    monkeypatch.setattr(payloads, "_t_sf", lambda x, df: seen.append(df) or original(x, df))
    data = copy.deepcopy(EVALUATION)
    data["windows"] = 0
    mean_diff = data["dm"][0]["mean_diff"]
    for n in (payloads.MAX_ROWS + 1, 2**53 - 1):
        data["dm"][0].update(n=n, df=n - 1, hln_factor=math.sqrt((n - 1) / n))
        _dm(data, 0, var_diff=4 * n * mean_diff * mean_diff)  # DM 0.5: the base's verdict, no_difference
        data["dm"][0]["p_value"] = 0.5  # not the tail, and not looked at
        seen.clear()
        assert validate_evaluation(data) == ["data.windows: expected an array, got int"]
        assert seen and max(seen) < payloads.MAX_ROWS  # the other rows' tails are still evaluated
    # At the bound the tail is evaluated and the p-value checked.
    n = payloads.MAX_ROWS
    data["dm"][0].update(n=n, df=n - 1, hln_factor=math.sqrt((n - 1) / n))
    _dm(data, 0, var_diff=4 * n * mean_diff * mean_diff)
    seen.clear()
    assert validate_evaluation(data) == ["data.windows: expected an array, got int"]
    assert n - 1 in seen
    data["dm"][0]["p_value"] = 0.5
    assert any(p.startswith("data.dm[0].p_value: is 0.5, but 2 P(T > |statistic_hln|)") for p in validate_evaluation(data))


def test_a_warnings_list_is_bounded_before_it_is_walked():
    warning = {"category": "W", "message": "m"}
    assert validate_forecast(edited(REFIT, ["refits", 0, "warnings"], [warning] * payloads.MAX_WARNINGS), "aic", "refit") == []
    problems = validate_forecast(edited(REFIT, ["refits", 0, "warnings"], [warning] * (payloads.MAX_WARNINGS + 1)), "aic", "refit")
    assert problems == [f"data.refits[0].warnings: has {payloads.MAX_WARNINGS + 1} warnings, more than the {payloads.MAX_WARNINGS} a reader takes"]
    t0 = time.perf_counter()
    problems = validate_forecast(edited(REFIT, ["refits", 0, "warnings"], [{}] * 3_000_000), "aic", "refit")
    assert time.perf_counter() - t0 < 1.0 and len(problems) == 1


def test_the_t_tail_of_a_degenerate_df_is_nan_not_an_error():
    assert math.isnan(_t_sf(1.0, 5e-324)) and math.isnan(_t_sf(1.0, 0.0))


def test_a_dm_p_value_equal_to_alpha_is_not_a_rejection():
    # DM* at the t's 97.5% quantile on 4 df gives p = 0.05 (to 1e-15): at alpha, not below it.
    base = EVALUATION["dm"][0]
    corrected = float(stats.t.isf(0.025, 4))
    statistic = corrected / base["hln_factor"]
    var_diff = 1e-8
    row = {**base, "mean_diff": -statistic * math.sqrt(var_diff / 5), "var_diff": var_diff, "statistic": -statistic, "statistic_hln": -corrected, "p_value": 0.05}
    assert validate_evaluation(edited(EVALUATION, DM, {**row, "verdict": "no_difference"})) == []
    assert any("give 'no_difference'" in p for p in validate_evaluation(edited(EVALUATION, DM, {**row, "verdict": "beats_rw"})))


def test_a_coverage_p_value_equal_to_alpha_is_consistent(monkeypatch):
    # No integer count gives Kupiec's p of exactly 0.05, so the LR is taken as given here, to test the
    # verdict's boundary alone: p = alpha is "consistent", whichever side of the level the rate is on.
    lr = float(stats.chi2.isf(0.05, 1))
    row = {**EVALUATION["coverage"][12], "lr": lr, "p_value": 0.05}
    original = payloads.kupiec_lr
    monkeypatch.setattr(payloads, "kupiec_lr", lambda n, inside, level: lr if (n, inside, level) == (row["n"], row["inside"], row["level"]) else original(n, inside, level))
    assert validate_evaluation(edited(EVALUATION, ["coverage", 12], {**row, "verdict": "consistent"})) == []
    assert any("give 'consistent'" in p for p in validate_evaluation(edited(EVALUATION, ["coverage", 12], {**row, "verdict": "too_wide"})))


def test_each_refit_is_fitted_on_21_more_days_than_the_one_before():
    # A refit file with three refits (simulated: 250 training days, 30 test, 50 oos).
    from arima_forecasting.forecasting import Spec, forecast_payload

    from test_forecasting import fit_entry, simulated, table_for

    spec = Spec((0, 1, 1), "n", __import__("numpy").array([-0.08, 0.00035]))
    data = forecast_payload(table_for(simulated(330), 250, 30), {**fit_entry("aic", spec)}, 4.5, "refit")
    assert [r["n_obs"] for r in data["refits"]] == [271, 292, 313] and validate_forecast(data, "aic", "refit") == []
    problems = validate_forecast(edited(data, ["refits", 1, "n_obs"], 293), "aic", "refit")
    assert any("refits[1].n_obs: is 293, but the entry before was fitted on 271 observations and each refit adds 21" in p for p in problems), problems


# --- the re-review's holes, each pinned --------------------------------------------------------------------------


def test_the_model_labels_are_pinned_per_model_id():
    # The Model picker's text: pinned in both readers like the method labels, so a file cannot swap two
    # models' names (the re-review's labels.mjs: the swap passed both readers per file).
    from arima_forecasting import fitting

    assert payloads.MODEL_LABELS == fitting.LABELS
    data = copy.deepcopy(EVALUATION)
    data["models"][0]["label"], data["models"][1]["label"] = data["models"][1]["label"], data["models"][0]["label"]
    assert validate_evaluation(data) == [
        "data.models[0].label: is 'BIC choice', but this reader labels model 'aic' 'AIC choice (ADR-0002)'",
        "data.models[1].label: is 'AIC choice (ADR-0002)', but this reader labels model 'bic' 'BIC choice'",
    ]
    assert validate_evaluation(edited(EVALUATION, ["models", 2, "label"], "Course refit ")) == ["data.models[2].label: is 'Course refit ', but this reader labels model 'course' 'Course refit'"]
    assert validate_forecast(edited(STATIC, ["label"], "BIC choice"), "aic", "static") == ["data.label: is 'BIC choice', but this reader labels model 'aic' 'AIC choice (ADR-0002)'"]


def test_each_model_label_in_the_evaluation_is_its_forecast_files():
    # Each file is checked alone first, so a label off its pin is named there and the evaluation is left
    # out of the checks against the rows (the tie across files stays for a reader without the pin).
    data = copy.deepcopy(EVALUATION)
    data["models"][0]["label"], data["models"][1]["label"] = data["models"][1]["label"], data["models"][0]["label"]
    assert validate_forecast_evaluation(data, FORECASTS) == ["evaluation: not valid on its own (validate_evaluation), so it is not checked against the forecast rows"]


def _moved(data: dict, window: int, rows: slice, by: float, var_times: float = 1.0) -> dict:
    """`data` with mean_log moved by `by` and sd_log^2 times `var_times` on the given rows of one window,
    every dollar value recomputed (the producer's forecast_rows), so the file stays valid on its own."""
    from arima_forecasting.forecasting import forecast_rows

    data = copy.deepcopy(data)
    w = data["windows"][window]
    for i in range(*rows.indices(len(w["rows"]))):
        r = w["rows"][i]
        (w["rows"][i],) = forecast_rows([r["date"]], np.array([r["actual_log"]]), np.array([r["actual_usd"]]), np.array([r["mean_log"] + by]), np.array([r["sd_log"] ** 2 * var_times]), data["intervals"])
    return data


@pytest.mark.parametrize(("name", "window", "rows", "message"), [
    ("forecast_aic_static", 1, slice(None), "forecast_aic_static: window 'oos' row 0 mean_log"),
    ("forecast_bic_static", 0, slice(None), "forecast_bic_static: window 'test' row 0 mean_log"),
    ("forecast_aic_refit", 0, slice(0, 5), "forecast_aic_refit: window 'test' row 0 mean_log"),
])
def test_forecasts_from_the_same_state_must_be_the_same_numbers(name, window, rows, message):
    # Each file stays valid alone and the evaluation is rebuilt from the moved rows, so only the tie to
    # the walk-forward's first day (static) or first block (refit) sees it.
    from arima_forecasting.evaluation import evaluation_payload

    forecasts = copy.deepcopy(FORECASTS)
    forecasts[name] = _moved(forecasts[name], window, rows, -0.05)
    _, model, method = name.split("_", 2)
    assert validate_forecast(forecasts[name], model, method) == []
    rebuilt = evaluation_payload(forecasts, FIT)
    problems = validate_forecast_evaluation(rebuilt, forecasts)
    assert any(message in p for p in problems), problems


@pytest.mark.parametrize(("name", "window", "rows", "message"), [
    # The family the review built: bic's one-step sd_log times 1.5 after the first row (which the static
    # tie sees), the dollars and the evaluation rebuilt; every other check passed it.
    ("forecast_bic_walk_forward", 0, slice(1, None), "forecast_bic_walk_forward: window 'test' row 1 sd_log^2"),
    ("forecast_course_walk_forward", 1, slice(None), "forecast_course_walk_forward: window 'oos' row 0 sd_log^2"),
    # The refit's rows after its first 21 are tied to that refit's own sigma2.
    ("forecast_aic_refit", 1, slice(16, None), "forecast_aic_refit: window 'oos' row 16 sd_log^2"),
])
def test_a_one_step_variance_must_be_its_parameters_sigma2(name, window, rows, message):
    assert validate_forecast_fit(FIT, RESIDUALS, FORECASTS) == []
    forecasts = copy.deepcopy(FORECASTS)
    forecasts[name] = _moved(forecasts[name], window, rows, 0.0, var_times=1.5 * 1.5)
    _, model, method = name.split("_", 2)
    assert validate_forecast(forecasts[name], model, method) == []
    problems = validate_forecast_fit(FIT, RESIDUALS, forecasts)
    assert [p for p in problems if p.startswith(message)] == problems and len(problems) == 1, problems
    assert "from the sigma2" in problems[0] and ("refits[0]" in problems[0]) == (name == "forecast_aic_refit")


def test_the_refit_files_first_block_is_tied_to_the_training_fits_sigma2():
    # The block whose origin is the end of training (the first REFIT_EVERY rows) has no refits entry: its
    # parameters are fit.json's, so its one-step variance must be fit.json's aic sigma2. (refits[0] is
    # fitted REFIT_EVERY days later, on n_train + 21 observations, and serves the next block.) Later blocks
    # are tied only to their own refit's sigma2: a refit sigma2 and its block rescaled together pass every
    # reader, and only --check and tests/test_committed_artifacts.py, which refit, see it (contract.md 3.10).
    forecasts = copy.deepcopy(FORECASTS)
    forecasts["forecast_aic_refit"] = _moved(forecasts["forecast_aic_refit"], 0, slice(None), 0.0, var_times=1.5 * 1.5)
    assert validate_forecast(forecasts["forecast_aic_refit"], "aic", "refit") == []
    problems = validate_forecast_fit(FIT, RESIDUALS, forecasts)
    assert len(problems) == 1 and problems[0].startswith("forecast_aic_refit: window 'test' row 0 sd_log^2 is ") and "relative from the sigma2 0.0003594876328532193 of fit.json" in problems[0], problems


def test_a_one_step_variance_is_compared_at_sigma2_rel():
    # bic's fixture rows are 1.6e-9 above its sigma2: at SIGMA2_REL / 2 more they pass, at 1.5 SIGMA2_REL more they do not.
    for times, ok in ((1 + SIGMA2_REL / 2, True), (1 + 1.5 * SIGMA2_REL, False), (1 - 1.5 * SIGMA2_REL, False)):
        forecasts = {**FORECASTS, "forecast_bic_walk_forward": _moved(FORECASTS["forecast_bic_walk_forward"], 1, slice(None), 0.0, var_times=times)}
        problems = validate_forecast_fit(FIT, RESIDUALS, forecasts)
        assert (problems == []) if ok else (len(problems) == 1 and "forecast_bic_walk_forward: window 'oos' row 0 sd_log^2" in problems[0]), (times, problems)


def test_a_refit_sigma2_moves_its_blocks_variance_tie():
    # The refit's own sigma2 times 1.5 (the file stays valid alone): its block's rows no longer match it.
    forecasts = {**FORECASTS, "forecast_aic_refit": edited(REFIT, ["refits", 0, "params", 3, "value"], lambda v: v * 1.5)}
    assert validate_forecast(forecasts["forecast_aic_refit"], "aic", "refit") == []
    problems = validate_forecast_fit(FIT, RESIDUALS, forecasts)
    assert len(problems) == 1 and problems[0].startswith("forecast_aic_refit: window 'oos' row 16 sd_log^2 is ") and "-0.333 relative from the sigma2" in problems[0] and "of refits[0]" in problems[0], problems


def test_the_same_state_tie_is_compared_at_rel():
    # The aic static oos path moved by 2 _REL and by _REL / 2 of its first mean_log, the evaluation
    # rebuilt: only the tie to the walk-forward's first oos day can see it, and only the first.
    from arima_forecasting.evaluation import evaluation_payload

    first = STATIC["windows"][1]["rows"][0]["mean_log"]
    for rel, ok in ((REL / 2, True), (2 * REL, False)):
        forecasts = {**FORECASTS, "forecast_aic_static": _moved(STATIC, 1, slice(None), first * rel)}
        assert validate_forecast(forecasts["forecast_aic_static"], "aic", "static") == []
        problems = validate_forecast_evaluation(evaluation_payload(forecasts, FIT), forecasts)
        assert (problems == []) if ok else (len(problems) == 1 and problems[0].startswith("forecast_aic_static: window 'oos' row 0 mean_log")), problems


def test_the_origin_is_tied_across_files_and_to_prices():
    forecasts = copy.deepcopy(FORECASTS)
    forecasts["forecast_course_walk_forward"]["windows"][1]["origin"]["close_usd"] += 0.01
    forecasts["forecast_course_walk_forward"]["windows"][1]["origin"]["log_close"] = math.log(forecasts["forecast_course_walk_forward"]["windows"][1]["origin"]["close_usd"])
    assert validate_forecast(forecasts["forecast_course_walk_forward"], "course", "walk_forward") == []
    assert any("forecast_course_walk_forward: window 'oos' differs from forecast_aic_static's in its origin" in p for p in validate_forecast_evaluation(EVALUATION, forecasts))
    prices = _prices_of_the_fixtures()
    assert payloads.validate_forecast_prices(prices, FORECASTS) == []
    assert any("forecast_course_walk_forward: window 'oos' does not match prices.json in its origin" in p for p in payloads.validate_forecast_prices(prices, forecasts))
    missing = {k: v for k, v in FORECASTS.items() if k != "forecast_bic_static"}
    assert "forecast_bic_static: missing" in payloads.validate_forecast_prices(prices, missing)


def _prices_of_the_fixtures() -> dict:
    """A prices payload made of the fixtures' own rows (one training day, the origin), with its splits."""
    rows = []
    for w in STATIC["windows"]:
        origin = w["origin"]
        if not rows or rows[-1]["date"] != origin["date"]:
            rows.append({"date": origin["date"], "log_close": origin["log_close"], "close_usd": origin["close_usd"], "segment": "train"})
        rows += [{"date": r["date"], "log_close": r["actual_log"], "close_usd": r["actual_usd"], "segment": w["id"]} for r in w["rows"]]
    rows[-1 - len(STATIC["windows"][1]["rows"])]["segment"] = "test"
    splits = {}
    for segment in ("train", "test", "oos"):
        days = [r["date"] for r in rows if r["segment"] == segment]
        splits[segment] = {"start": days[0], "end": days[-1], "n": len(days)}
    return {"rows": rows, "splits": {"train_fraction": 0.9, **splits}}


@pytest.mark.parametrize(("segment", "field", "value", "message"), [
    ("oos", "end", "2021-07-22", "window 'oos' end is '2021-07-23', but prices.json's splits say '2021-07-22'"),
    ("test", "n", 4, "window 'test' n is 5, but prices.json's splits say 4"),
    ("test", "start", "2021-06-22", "window 'test' start is '2021-06-21', but prices.json's splits say '2021-06-22'"),
    # The origin is the last day of the segment before: train's for test, test's for oos.
    ("train", "end", "2021-06-17", "window 'test' origin date is '2021-06-18', but prices.json's splits say '2021-06-17'"),
    ("test", "end", "2021-06-24", "window 'test' end is '2021-06-25', but prices.json's splits say '2021-06-24'"),
])
def test_the_forecast_windows_are_prices_splits(segment, field, value, message):
    # The rows still match: only the tie to the splits sees the change (validate_prices ties the splits
    # to the rows and to the pinned out-of-sample window, so each file stays consistent with both).
    prices = _prices_of_the_fixtures()
    assert payloads.validate_forecast_prices(prices, FORECASTS) == []
    prices["splits"][segment][field] = value
    problems = payloads.validate_forecast_prices(prices, FORECASTS)
    expected = [f"forecast_{m}_{k}: {message}" for m, k in payloads.FORECASTS]
    if (segment, field) == ("test", "end"):  # also the oos window's origin date
        expected = [p for m, k in payloads.FORECASTS for p in (f"forecast_{m}_{k}: {message}", f"forecast_{m}_{k}: window 'oos' origin date is '2021-06-25', but prices.json's splits say '2021-06-24'")]
    assert problems == expected, problems
