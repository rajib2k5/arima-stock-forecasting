"""The block-resampled inference (src/arima_forecasting/block_inference.py): the sample ACF, the plan's
block-length rule and floor, the circular block bootstrap of the mean, the Newey-West t, Holm and the
minimum detectable effect (docs/validation/m5-preregistration.md), the Politis-White block length and the
EWC t test (docs/validation/m5-preregistration-v2.md).

Made-up numbers only. Every expected value is worked by hand in the comments, from the textbook
definitions, never from block_inference.py itself. The two normal tail areas were read from scipy
once and written down. The Politis-White block length is checked against arch's
`optimal_block_length` outside this suite (arch is not a project dependency); here it is worked by hand.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from arima_forecasting.block_inference import (
    acf_band,
    acf_lags,
    below_floor,
    block_count,
    block_length,
    block_length_from_acf,
    block_starts,
    bootstrap_p,
    c2_block,
    c2_block_length,
    circular_block_means,
    ewc_dof,
    ewc_test,
    ewc_weights,
    flat_top,
    holm,
    minimum_detectable_effect,
    newey_west_t,
    politis_white_block_length,
    pw_block_from_acv,
    pw_kn,
    pw_m_hat,
    pw_max_block,
    sample_acf,
)

# --- sample ACF -----------------------------------------------------------------------------------------


def test_the_sample_acf_by_hand():
    # x = 1, 2, 3, 4: mean 2.5, deviations -1.5, -0.5, 0.5, 1.5, sum of squares 5.
    # lag 1: (-1.5)(-0.5) + (-0.5)(0.5) + (0.5)(1.5) = 1.25 -> 0.25
    # lag 2: (-1.5)(0.5) + (-0.5)(1.5) = -1.5 -> -0.3
    # lag 3: (-1.5)(1.5) = -2.25 -> -0.45
    assert sample_acf([1.0, 2.0, 3.0, 4.0], 3) == pytest.approx([0.25, -0.3, -0.45], abs=1e-15)
    # Alternating +-1, n = 6: mean 0, sum of squares 6; lag 1 has five products of -1, lag 2 four of +1.
    assert sample_acf([1.0, -1.0] * 3, 2) == pytest.approx([-5 / 6, 4 / 6], abs=1e-15)


def test_a_constant_series_has_no_acf_and_the_lags_are_bounded():
    assert np.isnan(sample_acf([3.0] * 6, 4)).all()
    assert len(sample_acf([1.0, 2.0, 4.0], 0)) == 0
    with pytest.raises(ValueError, match="max_lag"):
        sample_acf([1.0, 2.0, 4.0], 3)  # a lag of n has no pairs


def test_the_lag_count_and_the_band():
    # L = min(floor(n / 4), 100): the plan's two windows give 56 and 100.
    assert [acf_lags(n) for n in (227, 689, 399, 400, 403, 7)] == [56, 100, 99, 100, 100, 1]
    assert acf_band(100) == pytest.approx(0.196, rel=1e-15)
    assert acf_band(40) == pytest.approx(0.3099032106965012, rel=1e-15)  # 1.96 / sqrt(40)


# --- the block-length rule ------------------------------------------------------------------------------

BAND = 0.1


@pytest.mark.parametrize(
    ("rho", "expected"),
    [
        ([0.0] * 10, 1),  # lags 1, 2, 3 inside: b = 1
        ([0.5] + [0.0] * 9, 2),  # lag 1 outside, 2, 3, 4 inside
        ([-0.5] + [0.0] * 9, 2),  # the absolute value is compared
        ([0.5, 0.5, 0.5] + [0.0] * 7, 4),
        ([0.1] + [0.0] * 9, 2),  # exactly on the band is not below it
        ([0.5, 0.0, 0.0, 0.5] + [0.0] * 6, 5),  # 2 and 3 are inside but 4 is not: three in a row first at 5
        ([0.5] * 7 + [0.0] * 3, 8),  # L = 10: the last l allowed is L - 2 = 8
    ],
)
def test_the_block_rule_on_constructed_acf_patterns(rho, expected):
    assert block_length_from_acf(rho, BAND) == expected


def test_the_block_rule_gives_l_plus_1_when_no_lag_qualifies():
    # L = 10 in each. Every lag outside; only lags 9 and 10 inside (l = 9 would need lag 11, which is
    # not computed); and NaN, the ACF of a constant series, which is not below the band.
    assert block_length_from_acf([0.5] * 10, BAND) == 11
    assert block_length_from_acf([0.5] * 8 + [0.0] * 2, BAND) == 11
    assert block_length_from_acf([math.nan] * 10, BAND) == 11
    assert block_length_from_acf([0.0, 0.0], BAND) == 3  # L = 2 < 3 lags: no l fits at all


def test_the_block_length_reads_the_series_own_acf():
    # n = 40: L = 10, band 1.96 / sqrt(40) = 0.310. Each series has mean 0.
    zeros = [0.0] * 36
    # 1, -1, 0, ...: sum of squares 2, lag 1 product -1 -> -0.5 (outside), every later lag 0: b = 2.
    assert block_length([1.0, -1.0, *zeros, 0.0, 0.0]) == 2
    # 1, 0, ..., 0, -1: the only product is at lag 39, past L, so lags 1-3 are 0: b = 1.
    assert block_length([1.0, *zeros, 0.0, 0.0, -1.0]) == 1
    # 1, 1, -1, -1, 0, ...: sum of squares 4; lag 1: 1 - 1 + 1 = 1 -> 0.25 (inside); lag 2: -1 - 1 = -2
    # -> -0.5 (outside); lag 3: -1 -> -0.25; lags 4+ 0. Three inside in a row first at l = 3.
    assert block_length([1.0, 1.0, -1.0, -1.0, *zeros]) == 3
    # A constant series: no ACF, so no l, so L + 1 = 11.
    assert block_length([2.5] * 40) == 11


# --- the floor ------------------------------------------------------------------------------------------


def test_the_block_count_floor():
    # The plan's floor is 8 whole blocks: 227 // 28 = 8 passes, 227 // 29 = 7 does not; 689 // 86 = 8, 689 // 87 = 7.
    assert block_count(227, 28) == 8 and not below_floor(227, 28)
    assert block_count(227, 29) == 7 and below_floor(227, 29)
    assert not below_floor(689, 86) and below_floor(689, 87)
    assert not below_floor(8, 1) and below_floor(7, 1)


# --- the circular block bootstrap -----------------------------------------------------------------------

X = [1.0, 2.0, 4.0, 8.0, 16.0]  # n = 5; every sum of a subset is distinct


def test_the_circular_block_means_by_hand():
    # b = 2: k = ceil(5 / 2) = 3 blocks, the last one cut to 5 - 2 * 2 = 1 value.
    # starts (4, 0, 2): [16, 1] (wraps), [1, 2], [4]     -> 24 / 5 = 4.8
    # starts (3, 4, 4): [8, 16], [16, 1], [16]           -> 57 / 5 = 11.4
    # starts (0, 2, 0): [1, 2], [4, 8], [1]              -> 16 / 5 = 3.2
    means = circular_block_means(X, 2, [[4, 0, 2], [3, 4, 4], [0, 2, 0]])
    assert means == pytest.approx([4.8, 11.4, 3.2], rel=1e-15)
    # b = n: one block, a rotation of the whole circle, so the mean of the series (31 / 5) from any start.
    assert circular_block_means(X, 5, [[3], [0]]) == pytest.approx([6.2, 6.2], rel=1e-15)
    # b = 1: five single values, (16 * 4 + 1) / 5 = 13.
    assert circular_block_means(X, 1, [[4, 4, 4, 4, 0]]) == pytest.approx([13.0], rel=1e-15)
    with pytest.raises(ValueError, match="shape"):
        circular_block_means(X, 2, [[0, 1]])  # 2 starts, 3 needed
    with pytest.raises(ValueError, match="0 to 4"):
        circular_block_means(X, 2, [[0, 1, 5]])


def test_the_block_starts_are_k_per_replicate_and_inside_the_circle():
    starts = block_starts(10, 3, 500, np.random.default_rng(1))
    assert starts.shape == (500, 4)  # ceil(10 / 3) = 4
    assert starts.min() == 0 and starts.max() == 9  # 2,000 draws on 0 ... 9 reach both ends
    with pytest.raises(ValueError, match="b <= n"):
        block_starts(10, 11, 5, np.random.default_rng(1))


def test_the_bootstrap_p_is_in_0_1_and_a_multiple_of_1_over_b_plus_1():
    d = np.random.default_rng(7).normal(0.1, 1.0, 120)  # made-up
    for b in (1, 3, 10):
        p, means = bootstrap_p(d, b, 199, np.random.default_rng(b))
        assert 0 < p <= 1
        assert p * 200 == pytest.approx(round(p * 200), abs=1e-9)
        assert len(means) == 199


def test_a_zero_differential_gives_p_1():
    # d = 0: its mean is 0 and every replicate's mean is 0, and |0| >= |0| for all B: p = (1 + B) / (B + 1).
    p, means = bootstrap_p(np.zeros(50), 3, 99, np.random.default_rng(0))
    assert p == 1.0
    assert not means.any()


def test_a_gross_shift_gives_p_1_over_b_plus_1():
    # Mean 10, spread 0.01: the centred replicates' means stay near 0, never 10 away. p = (1 + 0) / 200.
    d = 10.0 + np.random.default_rng(3).normal(0.0, 0.01, 80)  # made-up
    p, means = bootstrap_p(d, 4, 199, np.random.default_rng(0))
    assert p == 1 / 200
    assert np.abs(means).max() < 0.01  # the series is centred before resampling
    p_neg, _ = bootstrap_p(-d, 4, 199, np.random.default_rng(0))  # two-sided
    assert p_neg == 1 / 200


# --- Newey-West -----------------------------------------------------------------------------------------

D = [1.0, 2.0, 3.0, 4.0, 5.0]  # mean 3, deviations -2, -1, 0, 1, 2


def test_the_newey_west_t_at_lag_0_is_the_plain_t_with_the_n_divisor():
    # gamma_0 = (4 + 1 + 0 + 1 + 4) / 5 = 2; t = 3 / sqrt(2 / 5) = 4.743416490252569.
    # Two-sided normal p = 2 (1 - Phi(4.7434)) = 2.1014359560124373e-06.
    t, p = newey_west_t(D, 0)
    assert t == pytest.approx(4.743416490252569, rel=1e-14)
    assert p == pytest.approx(2.1014359560124373e-06, rel=1e-9)


def test_the_newey_west_t_at_lag_1_by_hand():
    # gamma_1 = ((-2)(-1) + (-1)(0) + (0)(1) + (1)(2)) / 5 = 0.8, Bartlett weight 1 - 1/2 = 0.5:
    # LRV = 2 + 2 (0.5)(0.8) = 2.8; t = 3 / sqrt(2.8 / 5) = 4.0089186286863665; p = 6.099742889649497e-05.
    t, p = newey_west_t(D, 1)
    assert t == pytest.approx(4.0089186286863665, rel=1e-14)
    assert p == pytest.approx(6.099742889649497e-05, rel=1e-9)
    t_neg, p_neg = newey_west_t([-v for v in D], 1)
    assert t_neg == pytest.approx(-4.0089186286863665, rel=1e-14) and p_neg == pytest.approx(p, rel=1e-12)
    with pytest.raises(ValueError, match="long-run variance is 0"):
        newey_west_t([0.5] * 5, 1)


# --- Holm and the MDE -----------------------------------------------------------------------------------


def test_holm_by_hand():
    # Sorted 0.005, 0.01, 0.03, 0.04 times 4, 3, 2, 1 = 0.02, 0.03, 0.06, 0.04; running maximum
    # 0.02, 0.03, 0.06, 0.06; back in the given order:
    assert holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02], rel=1e-15)
    # 0.5 x 2 = 1.0, 0.6 x 1 = 0.6 -> running max 1.0, 1.0. 0.7 x 2 = 1.4 is capped at 1.
    assert holm([0.5, 0.6]) == pytest.approx([1.0, 1.0], rel=1e-15)
    assert holm([0.7, 0.9]) == pytest.approx([1.0, 1.0], rel=1e-15)
    assert holm([0.01, 0.01]) == pytest.approx([0.02, 0.02], rel=1e-15)  # a tie: both 2 x 0.01
    assert holm([0.2]) == pytest.approx([0.2], rel=1e-15)  # k = 1: unchanged
    with pytest.raises(ValueError, match="in \\[0, 1\\]"):
        holm([0.5, 1.5])


def test_the_minimum_detectable_effect_by_hand():
    # (1.96 + 0.84) = 2.8 times the standard deviation (divisor B): of -1, 1 it is 1; of 0, 0, 0, 4 it
    # is sqrt((1 + 1 + 1 + 9) / 4) = sqrt(3).
    assert minimum_detectable_effect([-1.0, 1.0]) == pytest.approx(2.8, rel=1e-15)
    assert minimum_detectable_effect([0.0, 0.0, 0.0, 4.0]) == pytest.approx(4.849742261192856, rel=1e-15)


# --- the Politis-White block length -------------------------------------------------------------------


def test_the_flat_top_window():
    # 1 up to |s| = 1/2, then a straight line 2 (1 - |s|) down to 0 at |s| = 1, and 0 past it; symmetric.
    assert [flat_top(s) for s in (0.0, 0.25, 0.5, 0.75, 0.9, 1.0, 1.2)] == pytest.approx([1.0, 1.0, 1.0, 0.5, 0.2, 0.0, 0.0], abs=1e-15)
    assert flat_top(-0.75) == flat_top(0.75)


def test_the_politis_white_run_length_and_cap():
    # K_n = max(5, ceil(sqrt(log10 n))): 5 for any n below 10^25; sqrt(log10 10^36) = 6.
    assert [pw_kn(n) for n in (64, 227, 689, 10**36)] == [5, 5, 5, 6]
    # ceil(min(3 sqrt(n), n / 3)): 64 -> min(24, 21.3) -> 22; 227 -> min(45.2, 75.7) -> 46;
    # 689 -> min(78.7, 229.7) -> 79; 9 -> min(9, 3) -> 3.
    assert [pw_max_block(n) for n in (64, 227, 689, 9)] == [22, 46, 79, 3]


@pytest.mark.parametrize(
    ("rho", "expected"),
    [
        ([0.0] * 12, 1),  # lags 1-5 inside: m = 1
        ([0.5] + [0.0] * 11, 2),  # lag 1 outside: the first run of five starts at lag 2
        ([-0.5, 0.0, 0.0, 0.5] + [0.0] * 8, 5),  # runs from lags 2, 3 and 4 include lag 4: m = 5
        ([0.1] + [0.0] * 11, 2),  # exactly on the band is not below it
        ([0.5] * 7 + [0.0] * 5, 8),  # 12 lags: the last run that fits is lags 8-12
        ([0.5] * 8 + [0.0] * 4, None),  # only four small lags at the end: no run of five
        ([math.nan] * 12, None),
    ],
)
def test_the_politis_white_correlogram_rule_on_constructed_patterns(rho, expected):
    assert pw_m_hat(rho, 0.1, 5) == expected


def test_the_politis_white_block_from_autocovariances_by_hand():
    # n = 1000, so n^(1/3) = 10. M = 2, R = 1, 0.5, 0.25: lambda(1/2) = 1, lambda(1) = 0.
    # g(0) = 1 + 2 (0.5) = 2; G = 2 (1)(1)(0.5) = 1; b = (2 / ((4/3) 4))^(1/3) 10 = 0.375^(1/3) 10 = 7.211247851537042.
    assert pw_block_from_acv([1.0, 0.5, 0.25], 1000) == pytest.approx(7.211247851537042, rel=1e-12)
    # M = 4, R = 1, 0.5, 0.25, 0.125, 0.0625: lambda = 1, 1, 0.5, 0 at k = 1 ... 4.
    # g(0) = 1 + 2 (0.5 + 0.25 + 0.0625) = 2.625; G = 2 (0.5 + 2 (0.25) + 3 (0.5)(0.125)) = 2.375;
    # b = (1.5 (2.375 / 2.625)^2)^(1/3) 10 = (1.5 (19/21)^2)^(1/3) 10 = 10.708285882438052.
    assert pw_block_from_acv([1.0, 0.5, 0.25, 0.125, 0.0625], 1000) == pytest.approx(10.708285882438052, rel=1e-12)
    with pytest.raises(ValueError, match="g\\(0\\) is 0"):
        pw_block_from_acv([1.0, -0.5, 0.0], 1000)  # 1 + 2 (-0.5) = 0


def test_the_politis_white_block_length_of_a_series_by_hand():
    # x = 3, -1, -1, -1, then 60 zeros (n = 64, mean 0, n^(1/3) = 4). R(0) = 12/64; R(1) = (-3 + 1 + 1)/64
    # = -1/64; R(2) = (-3 + 1)/64 = -2/64; R(3) = -3/64; later lags 0. rho = -1/12, -1/6, -1/4, 0, ...
    # The band 2 sqrt(log10(64) / 64) = 0.336 holds lags 1-5: m = 1, so M = 2 (lambda(1/2) = 1, lambda(1) = 0).
    # g(0) = (12 - 2)/64 = 10/64; G = 2 (-1/64) = -2/64; b = (2 (2/64)^2 / ((4/3)(10/64)^2))^(1/3) 4
    # = (8 / (400 / 3))^(1/3) 4 = 0.06^(1/3) 4 = 1.5659470564675455.
    assert politis_white_block_length([3.0, -1.0, -1.0, -1.0, *[0.0] * 60]) == pytest.approx(1.5659470564675455, rel=1e-12)


def test_the_politis_white_block_is_capped_and_refuses_what_it_cannot_measure():
    # A first difference of white noise has a long-run variance of 0, so g(0) is near 0 and the
    # estimate runs past the cap ceil(min(3 sqrt(64), 64 / 3)) = 22. Made-up noise.
    over_differenced = np.diff(np.random.default_rng(0).normal(size=65))
    assert politis_white_block_length(over_differenced) == 22.0
    with pytest.raises(ValueError, match="constant series"):
        politis_white_block_length([0.0] * 64)
    with pytest.raises(ValueError, match="too short"):
        politis_white_block_length(np.arange(8.0))  # reads ceil(sqrt(8)) + 5 = 8 lags of 8 values



# --- rule C2 --------------------------------------------------------------------------------------------


def test_the_c2_block_by_hand():
    # max(b_v1, ceil(1.5 b_PW)): 1.5 (1.5659470564675455) = 2.3489 rounds up to 3; 1.5 (2) = 3 exactly stays 3.
    assert c2_block(2, 1.5659470564675455) == 3
    assert c2_block(4, 1.5659470564675455) == 4
    assert c2_block(1, 2.0) == 3
    assert c2_block(1, 0.4) == 1


def test_the_c2_block_of_a_series_and_of_a_constant_one():
    # The Politis-White hand series above: rho = -1/12, -1/6, -1/4, then 0; the v1 band 1.96 / 8 = 0.245 holds
    # lags 1, 2, not 3, then 4, 5, 6, so b_v1 = 4. b_PW = 1.5659470564675455 gives ceil(2.3489) = 3, so b = 4.
    b, b_v1, b_pw = c2_block_length([3.0, -1.0, -1.0, -1.0, *[0.0] * 60])
    assert (b, b_v1) == (4, 4)
    assert b_pw == pytest.approx(1.5659470564675455, rel=1e-12)
    # A constant series has no ACF; the plan sets b = 1 (the v1 rule alone would give L + 1 = 17).
    assert c2_block_length([0.25] * 64) == (1, None, None)


# --- EWC t test -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("n", "expected"), [(227, 14), (689, 31), (1000, 40), (6, 1), (4, 1), (3, 0)])
def test_the_ewc_degrees_of_freedom(n, expected):
    # nu = floor(0.4 n^(2/3)) is the largest nu with 125 nu^3 <= 8 n^2.
    # 227: 8 (227^2) = 412232, and 125 (14^3) = 343000 <= 412232 < 125 (15^3) = 421875.
    # 689: 8 (689^2) = 3797768, and 125 (31^3) = 3723875 <= 3797768 < 125 (32^3) = 4096000.
    # 1000: 0.4 (1000^(2/3)) = 40 exactly (125 (40^3) = 8 (10^6)), where floating point gives 39.99999999999999.
    # 6: 125 <= 288 < 1000. 4: 125 <= 128. 3: 72 < 125, so no weight.
    assert ewc_dof(n) == expected


def test_the_ewc_cosine_weights_by_hand():
    # n = 3, d = 1, 2, 4. j = 1: cos(pi/6), cos(pi/2), cos(5 pi/6) = sqrt(3)/2, 0, -sqrt(3)/2, so the sum is
    # (sqrt(3)/2)(1 - 4) = -3 sqrt(3)/2 and Lambda_1 = sqrt(2/3)(-3 sqrt(3)/2) = -3 sqrt(2)/2 = -2.121320343559643.
    # j = 2: cos(pi/3), cos(pi), cos(5 pi/3) = 1/2, -1, 1/2, so the sum is 1/2 - 2 + 2 = 1/2 and
    # Lambda_2 = sqrt(2/3)/2 = 0.408248290463863.
    assert ewc_weights([1.0, 2.0, 4.0], 2) == pytest.approx([-2.121320343559643, 0.408248290463863], rel=1e-12)
    with pytest.raises(ValueError, match="nu must be"):
        ewc_weights([1.0, 2.0, 4.0], 3)


def test_the_ewc_t_and_p_by_hand():
    # n = 6, d = 1, 1, 0, 0, 0, 0: nu = 1 and the mean is 1/3. Lambda_1 = sqrt(1/3)(cos(pi/12) + cos(pi/4))
    # = sqrt(1/3)(2 cos(pi/6) cos(pi/12)) = cos(pi/12) = (sqrt(6) + sqrt(2))/4, so Omega = cos^2(pi/12)
    # = (2 + sqrt(3))/4 = 0.9330127018922193. t = sqrt(6)(1/3) / cos(pi/12) = 4 sqrt(6) / (3 (sqrt(6) + sqrt(2)))
    # = (6 - 2 sqrt(3))/3 = 2 - 2/sqrt(3) = 0.8452994616207483.
    # Student's t on 1 df is the Cauchy distribution: p = 1 - (2/pi) arctan(t) = 0.5532464586440644.
    result = ewc_test([1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    assert result["nu"] == 1
    assert result["omega"] == pytest.approx(0.9330127018922193, rel=1e-12)
    assert result["t"] == pytest.approx(0.8452994616207483, rel=1e-12)
    assert result["p"] == pytest.approx(0.5532464586440644, rel=1e-12)
    assert result["unresolved"] is False


def test_the_ewc_p_is_read_from_student_t_on_nu_degrees_of_freedom():
    # n = 227 gives nu = 14. Made-up noise with a shift, chosen so that t is near 2, where the t on 14 df, the
    # normal and the t on n - 1 df give p-values that differ in the second decimal.
    result = ewc_test(np.random.default_rng(1).normal(0.15, 1.0, size=227))
    assert result["nu"] == 14
    assert result["p"] == pytest.approx(2.0 * stats.t.sf(abs(result["t"]), 14), rel=1e-12)
    assert result["p"] - 2.0 * stats.norm.sf(abs(result["t"])) > 0.01


def test_a_zero_differential_gives_ewc_p_1():
    # Every Lambda_j is 0 and the mean is 0: Omega = 0, and the plan's rule gives p = 1 with no t.
    result = ewc_test([0.0] * 227)
    assert result["p"] == 1.0
    assert result["unresolved"] is False
    assert result["omega"] == 0.0
    assert result["t"] is None


def test_a_constant_differential_that_is_not_zero_is_unresolved_under_ewc():
    # Each cosine sums to 0 over t, so every Lambda_j of a constant series is 0 and Omega = 0, while the mean is
    # 0.1: the plan's rule is UNRESOLVED, with no p. (In floating point the weights come out near 1e-17, Omega
    # near 1e-33 and the p near 0, which is the case this test guards.)
    assert np.array_equal(ewc_weights([0.1] * 227, 14), np.zeros(14))
    result = ewc_test([0.1] * 227)
    assert result["unresolved"] is True
    assert result["p"] is None
    assert result["mde"] is None


def test_the_ewc_minimum_detectable_effect_by_hand():
    # The n = 6 series of the t test: nu = 1, so the quantiles are the Cauchy's, tan(pi (q - 1/2)):
    # t_{1, 0.975} = tan(0.475 pi) = 12.706204736174696 and t_{1, 0.80} = tan(0.3 pi) = 1.3763819204711734.
    # sqrt(Omega / n) = cos(pi/12) / sqrt(6) = 0.3943375672974065.
    # MDE = (12.706204736174696 + 1.3763819204711734)(0.3943375672974065) = 5.553292963436649.
    assert ewc_test([1.0, 1.0, 0.0, 0.0, 0.0, 0.0])["mde"] == pytest.approx(5.553292963436649, rel=1e-12)
    assert ewc_test([0.0] * 6)["mde"] == 0.0
