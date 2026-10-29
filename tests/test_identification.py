"""ACF, PACF and their bands (src/arima_forecasting/identification.py).

The expected values are worked out by hand on an eight-point series, with the arithmetic in the
comments; the code under test is never used to make them.
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tools.sm_exceptions import SingularMatrixWarning
from statsmodels.tsa.stattools import pacf

from arima_forecasting import identification as ident
from arima_forecasting.payloads import validate_acf_pacf

Z = 1.959963984540054  # the 97.5% normal quantile

# x = 2, 4, 6, 4, 2, 4, 6, 4. Mean 4, so the deviations are -2, 0, 2, 0, -2, 0, 2, 0 and their
# squares add up to 16. r_k = sum over t of dev_t * dev_(t-k), divided by 16:
#   r_1 = 0 (every product has a zero in it)
#   r_2 = (2*-2 + 0 + -2*2 + 0 + 2*-2 + 0) / 16 = -12 / 16 = -0.75
#   r_3 = 0
SERIES = np.array([2.0, 4.0, 6.0, 4.0, 2.0, 4.0, 6.0, 4.0])


def test_acf_by_hand():
    rows = ident.correlogram(SERIES, nlags=3)
    assert [r["lag"] for r in rows] == [0, 1, 2, 3]
    assert [r["acf"] for r in rows] == pytest.approx([1.0, 0.0, -0.75, 0.0], abs=1e-12)


def test_pacf_by_hand_with_yule_walker_mle():
    # Durbin-Levinson on r = (0, -0.75, 0): phi_11 = r_1 = 0; phi_22 = (r_2 - r_1^2) / (1 - r_1^2) =
    # -0.75; phi_21 = phi_11 - phi_22 * phi_11 = 0; phi_33 = (r_3 - phi_21 r_2 - phi_22 r_1) /
    # (1 - phi_21 r_1 - phi_22 r_2) = 0 / (1 - 0.5625) = 0.
    rows = ident.correlogram(SERIES, nlags=3)
    assert [r["pacf"] for r in rows] == pytest.approx([1.0, 0.0, -0.75, 0.0], abs=1e-12)


def test_the_bands_by_hand():
    rows = ident.correlogram(SERIES, nlags=3)
    # ACF, Bartlett: z * sqrt((1 + 2 * (r_1^2 + ... + r_(k-1)^2)) / n), n = 8.
    #   lag 1: z * sqrt(1 / 8)                 = 1.959964 * 0.353553 = 0.692952
    #   lag 2: z * sqrt((1 + 2 * 0) / 8)       = 0.692952 (r_1 is 0, so no wider)
    #   lag 3: z * sqrt((1 + 2 * 0.5625) / 8)  = 1.959964 * sqrt(0.265625) = 1.959964 * 0.515388 = 1.010142
    assert [r["acf_band"] for r in rows] == pytest.approx([0.0, Z / math.sqrt(8), Z / math.sqrt(8), Z * math.sqrt(2.125 / 8)], abs=1e-12)
    assert rows[3]["acf_band"] == pytest.approx(1.010142, abs=1e-6)
    # PACF: z / sqrt(n) at every lag from 1 on.
    assert [r["pacf_band"] for r in rows] == pytest.approx([0.0, 0.692952, 0.692952, 0.692952], abs=1e-6)


def test_the_course_draws_with_ywm_and_the_adjusted_method_would_give_another_pacf():
    # pacf()'s own default, "ywadjusted", divides r_2 by n - k instead of n: r_2 becomes
    # (-12 / 6) / (16 / 8) = -1, so phi_22 = -1, at the edge of what a PACF can be; the next
    # Yule-Walker system is singular, and statsmodels says so.
    with pytest.warns(SingularMatrixWarning):
        assert pacf(SERIES, nlags=3, method="ywadjusted")[2] == pytest.approx(-1.0, abs=1e-12)
    assert ident.correlogram(SERIES, nlags=3)[2]["pacf"] == pytest.approx(-0.75, abs=1e-12)


def test_the_settings_are_the_defaults_of_the_plots_the_course_calls():
    # The course calls plot_acf(x, lags=50) and plot_pacf(x, lags=50). If statsmodels changes these
    # defaults, the course's pictures change, and this test says so.
    acf_defaults = inspect.signature(plot_acf).parameters
    pacf_defaults = inspect.signature(plot_pacf).parameters
    assert acf_defaults["fft"].default is ident.ACF_FFT is False
    assert acf_defaults["adjusted"].default is ident.ACF_ADJUSTED is False
    assert acf_defaults["bartlett_confint"].default is ident.BARTLETT is True
    assert acf_defaults["alpha"].default == ident.ALPHA == 0.05
    assert pacf_defaults["method"].default == ident.PACF_METHOD == "ywm"
    assert ident.NLAGS == 50


def test_over_differenced_white_noise_has_a_lag_one_acf_near_minus_a_half():
    # Background section 3: the difference of white noise is an MA(1) with theta = -1, whose lag-1
    # autocorrelation is -1/2.
    noise = np.random.default_rng(11).standard_normal(4000)
    rows = ident.correlogram(np.diff(noise), nlags=5)
    assert rows[1]["acf"] == pytest.approx(-0.5, abs=0.03)
    assert abs(rows[2]["acf"]) < 0.05


@pytest.mark.parametrize("nlags", [0, 4])
def test_nlags_must_be_between_1_and_half_the_sample(nlags):
    with pytest.raises(ValueError, match="nlags"):
        ident.correlogram(SERIES, nlags=nlags)


def test_the_payload_on_a_random_walk_is_valid_and_its_acf_band_widens_with_the_lag():
    rng = np.random.default_rng(5)
    walk = np.cumsum(0.001 + 0.02 * rng.standard_normal(600))
    payload = ident.acf_pacf_payload(walk)
    assert validate_acf_pacf(payload) == []
    assert [(s["transform"], s["d"], s["n"]) for s in payload["series"]] == [("log", 0, 600), ("diff1", 1, 599), ("diff2", 2, 598)]
    assert payload["z"] == Z and payload["pacf_method"] == "ywm"
    for s in payload["series"]:
        assert len(s["rows"]) == 51
        bands = [r["acf_band"] for r in s["rows"]]
        assert all(b2 >= b1 - 1e-15 for b1, b2 in zip(bands[1:], bands[2:]))  # Bartlett only widens
    # The level of a random walk is a long memory: its lag-1 ACF is close to 1.
    assert payload["series"][0]["rows"][1]["acf"] > 0.95


@pytest.mark.parametrize(
    "lag, value, band, past",
    [
        (1, -0.12, 0.098, True),
        (1, 0.098, 0.098, False),  # on the band is not past it
        (1, -0.098, 0.098, False),
        (1, math.nextafter(0.098, 1.0), 0.098, True),  # one double past it is
        (0, 1.0, 0.0, False),  # lag 0 never counts
        (3, 0.03, 0.1, False),
    ],
)
def test_a_bar_is_past_its_band_only_when_strictly_beyond_it(lag, value, band, past):
    assert ident.outside(lag, value, band) is past


def test_the_payload_flags_each_bar_and_counts_the_flags():
    rng = np.random.default_rng(11)
    payload = ident.acf_pacf_payload(np.cumsum(0.01 * rng.standard_normal(400)), nlags=10)
    for s in payload["series"]:
        for name in ("acf", "pacf"):
            flags = [row[f"{name}_outside"] for row in s["rows"]]
            assert flags == [row["lag"] >= 1 and abs(row[name]) > row[f"{name}_band"] for row in s["rows"]]
            assert s[f"{name}_outside_count"] == sum(flags)
    assert payload["series"][0]["acf_outside_count"] == 10  # the level of a walk: every ACF bar is far past its band
