"""Unit-root tests and the rule that picks d (src/arima_forecasting/stationarity.py).

Every series here is simulated with a fixed seed; no market data is used. A random walk has a unit
root by construction and white noise is stationary by construction, so each test knows the right
answer before it runs.
"""

from __future__ import annotations

import sys
import warnings

import numpy as np
import pytest
from statsmodels.tsa.stattools import adfuller

from arima_forecasting import stationarity as st
from arima_forecasting.payloads import validate_stationarity


def random_walk(n: int = 1200, seed: int = 7, drift: float = 0.0008, sd: float = 0.017) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.log(30.0) + np.cumsum(drift + sd * rng.standard_normal(n))


def white_noise(n: int = 1200, seed: int = 8) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


# --- differencing and the ADF lag range -------------------------------------------------------

def test_difference_of_order_0_1_and_2_by_hand():
    x = [1.0, 4.0, 9.0, 16.0, 25.0]
    assert st.difference(x, 0).tolist() == x
    assert st.difference(x, 1).tolist() == [3.0, 5.0, 7.0, 9.0]
    assert st.difference(x, 2).tolist() == [2.0, 2.0, 2.0]


def test_difference_refuses_nan_and_a_negative_order():
    with pytest.raises(ValueError):
        st.difference([1.0, float("nan")], 1)
    with pytest.raises(ValueError):
        st.difference([1.0, 2.0], -1)


@pytest.mark.parametrize(
    "n, regression, expected",
    [
        (2037, "c", 26),  # 12 * 20.37 ** 0.25 = 12 * 2.12447 = 25.49, rounded up
        (1200, "c", 23),  # 12 * 12 ** 0.25 = 12 * 1.86121 = 22.33, rounded up
        (100, "c", 12),  # 12 * 1 exactly
        (20, "c", 8),  # 12 * 0.2 ** 0.25 = 8.02 -> 9, capped at 20 // 2 - 1 - 1 = 8
        (20, "ct", 7),  # two deterministic terms: 20 // 2 - 2 - 1 = 7
    ],
)
def test_adf_maxlag_is_statsmodels_default_rule(n, regression, expected):
    assert st.adf_maxlag(n, regression) == expected


def test_passing_maxlag_explicitly_gives_the_same_adf_as_statsmodels_default():
    x = random_walk()
    ours = st.adf_test(x)
    default = adfuller(x, regression="c", autolag="AIC", result_object=True)
    assert (ours["statistic"], ours["p_value"], ours["used_lag"], ours["nobs"]) == (
        default.statistic,
        default.pvalue,
        default.lags,
        default.nobs,
    )
    assert ours["maxlag"] == 23
    # nobs is n minus the chosen lag minus one (the first difference): the final regression uses
    # every observation it can, not the common sample of the lag search.
    assert ours["nobs"] == 1200 - ours["used_lag"] - 1


# --- ADF and KPSS on series whose answer is known ---------------------------------------------

def test_adf_does_not_reject_on_a_random_walk_and_rejects_on_white_noise():
    walk, noise = st.adf_test(random_walk()), st.adf_test(white_noise())
    assert walk["reject_unit_root"] is False and walk["p_value"] > 0.05
    assert noise["reject_unit_root"] is True and noise["p_value"] < 1e-10
    assert walk["regression"] == "c" and walk["autolag"] == "AIC"
    assert set(walk["critical_values"]) == {"1%", "5%", "10%"}


def test_kpss_rejects_on_a_random_walk_and_not_on_white_noise_with_the_clipped_p_values():
    walk, noise = st.kpss_test(random_walk()), st.kpss_test(white_noise())
    # statsmodels clips the KPSS p-value to its table, 0.01 to 0.10: "0.01" means "0.01 or less".
    assert (walk["p_value"], walk["p_value_bound"], walk["reject_stationarity"]) == (0.01, "smaller", True)
    assert (noise["p_value"], noise["p_value_bound"], noise["reject_stationarity"]) == (0.1, "greater", False)
    assert walk["nlags_method"] == "auto" and set(walk["critical_values"]) == {"10%", "5%", "2.5%", "1%"}


@pytest.mark.parametrize("p, expected", [(0.01, "smaller"), (0.1, "greater"), (0.05, None), (0.0100001, None)])
def test_kpss_bound_reads_only_the_two_table_edges(p, expected):
    assert st.kpss_bound(p) == expected


def test_kpss_refuses_a_clipped_p_value_that_statsmodels_did_not_warn_about(monkeypatch):
    # The guard: if a future statsmodels clipped without warning (or warned without clipping), our
    # p_value_bound would be wrong, so the export stops instead.
    class Fake:
        statistic, pvalue, lags = 9.0, 0.01, 3
        critical_values = {"10%": 0.347, "5%": 0.463, "2.5%": 0.574, "1%": 0.739}

    monkeypatch.setattr(st, "kpss", lambda *args, **kwargs: Fake())
    with pytest.raises(RuntimeError, match="disagree"):
        st.kpss_test(white_noise())


def test_kpss_passes_on_warnings_other_than_the_interpolation_warning(monkeypatch):
    real = st.kpss

    def noisy(*args, **kwargs):
        warnings.warn("something else", UserWarning, stacklevel=1)
        return real(*args, **kwargs)

    monkeypatch.setattr(st, "kpss", noisy)
    with pytest.warns(UserWarning, match="something else"):
        st.kpss_test(white_noise())


@pytest.mark.parametrize(
    "adf, kpss, expected",
    [(True, False, "stationary"), (False, True, "unit_root"), (True, True, "conflict"), (False, False, "inconclusive")],
)
def test_the_two_by_two_table(adf, kpss, expected):
    assert st.verdict(adf, kpss) == expected


def _t(d: int, adf: bool, kpss: bool) -> dict:
    return {"d": d, "adf": {"reject_unit_root": adf}, "kpss": {"reject_stationarity": kpss}}


@pytest.mark.parametrize(
    "transforms, expected",
    [
        ([_t(0, False, True), _t(1, True, False), _t(2, True, False)], (1, False)),  # the usual price
        ([_t(0, True, False), _t(1, True, False), _t(2, True, False)], (0, False)),  # already stationary
        ([_t(2, True, False), _t(0, False, True), _t(1, True, False)], (1, False)),  # order of the list
        ([_t(0, True, True), _t(1, False, False), _t(2, True, True)], (1, True)),  # no d passes: KPSS decides
        ([_t(0, False, True), _t(1, True, True), _t(2, True, True)], (2, True)),  # KPSS rejects everywhere
    ],
)
def test_decide_d_follows_adr_0002(transforms, expected):
    assert st.decide_d(transforms) == expected


# --- the payload ------------------------------------------------------------------------------

def test_a_random_walk_with_drift_gets_d_1_and_a_valid_payload():
    payload = st.stationarity_payload(random_walk())
    assert validate_stationarity(payload) == []
    assert [(t["id"], t["d"], t["n"]) for t in payload["transforms"]] == [("log", 0, 1200), ("diff1", 1, 1199), ("diff2", 2, 1198)]
    log, diff1 = payload["transforms"][0], payload["transforms"][1]
    assert (log["verdict"], diff1["verdict"]) == ("unit_root", "stationary")
    assert payload["decision"]["d_selected"] == 1 and payload["decision"]["tests_conflict"] is False
    # The second run of each test has a trend, and the rule never reads it.
    assert log["with_trend"]["adf"]["regression"] == "ct" and log["with_trend"]["kpss"]["regression"] == "ct"
    assert log["adf"]["regression"] == "c"
    assert payload["n_train"] == 1200 and payload["sample"] == "train"


def test_white_noise_gets_d_0():
    payload = st.stationarity_payload(white_noise())
    assert payload["decision"]["d_selected"] == 0
    assert payload["transforms"][0]["verdict"] == "stationary"


def test_the_payload_holds_test_statistics_and_never_the_series():
    # The owner gate: a d = 0 "series" would be the training log prices themselves.
    x = random_walk(300)
    text = repr(st.stationarity_payload(x))
    assert repr(float(x[0])) not in text and repr(float(x[-1])) not in text
    assert "rows" not in text


def test_pmdarima_ndiffs_agrees_on_a_random_walk():
    found = st.pmdarima_ndiffs(random_walk(), d_selected=1)
    assert (found["status"], found["kpss"], found["adf"], found["pp"], found["agrees"]) == ("ok", 1, 1, 1, True)
    assert found["reason"] is None and found["version"] == "2.1.1"


def test_a_missing_pmdarima_makes_the_cross_check_unavailable_not_the_export_fail(monkeypatch):
    monkeypatch.setitem(sys.modules, "pmdarima", None)  # `import pmdarima` now raises ImportError
    payload = st.stationarity_payload(random_walk(400))
    found = payload["decision"]["pmdarima_ndiffs"]
    assert found["status"] == "unavailable" and found["reason"].startswith("ModuleNotFoundError: import of pmdarima halted")
    assert (found["kpss"], found["adf"], found["pp"], found["agrees"]) == (None, None, None, None)
    assert validate_stationarity(payload) == []
