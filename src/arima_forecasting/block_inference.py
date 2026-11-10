"""Milestone 5: block-resampled inference on one loss-differential series (docs/validation/m5-preregistration.md).

Pure: numpy values in, plain numbers out. Nothing reads a file or draws a random number of its own;
the one random step (`block_starts`) takes the caller's generator. tools/comparison_inference.py runs
these on the 28 comparisons in the plan's order and with its settings.

**Sample ACF** (`sample_acf`). rho(l) = sum_{t=1..n-l} (x_t - mean)(x_{t+l} - mean) / sum_{t=1..n} (x_t - mean)^2:
demeaned, and biased (both sums are divided by n, so the n cancels). A constant series has a
denominator of 0 and no ACF: every lag is NaN.

**Block length** (`block_length`). The plan's rule, on lags 1 ... L with L = min(floor(n / 4), 100) and
the band c = 1.96 / sqrt(n): b is the smallest l >= 1 such that |rho(l)|, |rho(l + 1)| and |rho(l + 2)|
are all below c (strictly). If no l <= L - 2 has that, b = L + 1. A NaN is not below c, so a
constant series takes that branch.

**Block-count floor** (`below_floor`). With fewer than 8 whole blocks (floor(n / b) < 8) the plan calls the
comparison UNRESOLVED: there are too few independent pieces for a bootstrap.

**Circular block bootstrap of the mean** (Politis and Romano 1992, "A circular block-resampling
procedure for stationary data", in LePage and Billard (eds.), Exploring the Limits of Bootstrap,
Wiley, 263-270). The series is wrapped onto a circle, so a block that runs past the last value
continues at the first. One replicate is k = ceil(n / b) blocks of b consecutive values, each starting
at a position drawn uniformly from 0 ... n - 1, joined and cut to n values (the last block keeps its
first n - (k - 1) b values). Its statistic is the mean. `bootstrap_p` resamples the centred series
d - mean(d), so the replicates' means describe the mean's spread under E[d] = 0, and the two-sided p
is (1 + #{|mean*| >= |mean(d)|}) / (B + 1): never 0, and 1 when every replicate is at least as far
from 0 as the data (d constant at 0, for one).

**Newey-West t** (Newey and West 1987, "A simple, positive semi-definite, heteroskedasticity and
autocorrelation consistent covariance matrix", Econometrica 55(3), 703-708). The long-run variance
gamma_0 + 2 sum_{j=1..m} (1 - j / (m + 1)) gamma_j (Bartlett weights, gamma_j the autocovariance with
divisor n), t = mean / sqrt(LRV / n), and a two-sided normal p. At lag 0 it is the plain one-sample t
with the n divisor.

**Holm** (Holm 1979, "A simple sequentially rejective multiple test procedure", Scandinavian Journal of
Statistics 6(2), 65-70). Sorted ascending, the i-th smallest of k p-values (i from 1) is multiplied by
k - i + 1; the adjusted values are made non-decreasing by a running maximum and capped at 1. Rejecting
where the adjusted p is below alpha holds the family-wise error rate at alpha.

**Minimum detectable effect** (`minimum_detectable_effect`): (1.96 + 0.84) x the standard deviation of
the bootstrap means (numpy's default, divisor B). The smallest |E[d]| a per-test 5% two-sided test
finds with 80% power, when the mean is about normal with that standard deviation.

**Politis-White block length** (`politis_white_block_length`; Politis and White 2004, "Automatic
block-length selection for the dependent bootstrap", Econometric Reviews 23(1), 53-70, with the
correction of Patton, Politis and White 2009, Econometric Reviews 28(4), 372-375). An estimate of the
block that minimises the mean squared error of the circular bootstrap's variance of the mean:
b = (2 G^2 / D_CB)^(1/3) n^(1/3), with G = sum_{|k| <= M} lambda(k / M) |k| R(k), D_CB = (4/3) g(0)^2
(the 2009 correction) and g(0) = sum_{|k| <= M} lambda(k / M) R(k). R(k) is the autocovariance (divisor
n) and lambda the flat-top window: 1 for |s| <= 1/2, then 2 (1 - |s|) down to 0 at |s| = 1.
M = min(2 m, m_max), where m comes from the correlogram: the smallest m >= 1 such that |rho(m)|, ...,
|rho(m + K_n - 1)| are all below c sqrt(log10(n) / n), with c = 2, K_n = max(5, ceil(sqrt(log10 n)))
and lags read up to m_max = ceil(sqrt(n)) + K_n. With no such m, M = m_max. b is capped at
ceil(min(3 sqrt(n), n / 3)). Where the paper is silent or terse (m counted from the window's first
lag, the branch with no window, the cap), this follows the authors' reference code (Patton's Matlab),
which arch (`arch.bootstrap.optimal_block_length`) and R's np (`b.star`) port. rho is the biased sample
ACF above, as in np; arch divides each lag's cross product by its own partial sums of squares, which
can move a band decision and so M.

**Rule C2** (`c2_block_length`; the v2 plan's secondary bootstrap): b = max(b_v1, ceil(1.5 b_PW)), with
b_v1 the block from the plan-v1 rule above and b_PW the Politis-White block. A constant series has
neither, and the plan sets b = 1 for it.

**EWC fixed-smoothing t test** (`ewc_test`; Lazarus, Lewis, Stock and Watson 2018, "HAR inference:
recommendations for practice", Journal of Business & Economic Statistics 36(4), 541-559; the v2 plan,
docs/validation/m5-preregistration-v2.md). With nu = floor(0.4 n^(2/3)) cosine weights
Lambda_j = sqrt(2 / n) sum_{t=1..n} cos(pi j (t - 1/2) / n) d_t (j = 1 ... nu), the long-run variance
estimate is Omega = (1 / nu) sum_j Lambda_j^2, t = sqrt(n) mean(d) / sqrt(Omega), and the two-sided p is
read from Student's t on nu degrees of freedom (fixed-b asymptotics make that exact for this estimator).
Each cosine sums to 0 over t = 1 ... n, so the weights ignore the mean. For a constant series every
Lambda_j is 0 exactly; computed in floating point it would be about 1e-16 times the constant instead,
so a constant series is given its exact weights, 0. Omega = 0 then gives p = 1 when mean(d) = 0 and
UNRESOLVED otherwise (the plan's rule). nu is computed in integers (the largest nu with
125 nu^3 <= 8 n^2), because 0.4 n^(2/3) in floating point falls just short of an integer where it should
equal one (n = 1000 gives 39.99999999999999). The minimum detectable effect is
(t_{nu, 0.975} + t_{nu, 0.80}) sqrt(Omega / n).
"""

from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import stats

BAND_Z = 1.96  # the ACF band is BAND_Z / sqrt(n)
MAX_ACF_LAG = 100
RUN = 3  # consecutive lags inside the band that end the block
MIN_BLOCKS = 8
Z_TEST = 1.96  # two-sided 5%
Z_POWER = 0.84  # 80% power
PW_C = 2.0  # the Politis-White correlogram band is PW_C * sqrt(log10(n) / n)
PW_MIN_KN = 5
C2_MULTIPLIER = 1.5  # rule C2 scales the Politis-White block by this before rounding up


def _series(values: object, name: str = "series") -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) < 2:
        raise ValueError(f"{name} must be one-dimensional with at least two values, got shape {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} holds a value that is not finite")
    return array


def acf_lags(n: int) -> int:
    """L = min(floor(n / 4), 100): the lags the block rule reads."""
    return min(n // 4, MAX_ACF_LAG)


def acf_band(n: int) -> float:
    """c = 1.96 / sqrt(n)."""
    return BAND_Z / math.sqrt(n)


def sample_acf(values: object, max_lag: int) -> np.ndarray:
    """rho(1) ... rho(max_lag), demeaned and biased (module docstring); NaN at every lag for a constant series."""
    x = _series(values)
    if not 0 <= max_lag < len(x):
        raise ValueError(f"max_lag must be 0 to {len(x) - 1}, got {max_lag}")
    dev = x - x.mean()
    denominator = float(dev @ dev)
    if denominator == 0.0:
        return np.full(max_lag, np.nan)
    return np.array([float(dev[:-lag] @ dev[lag:]) / denominator for lag in range(1, max_lag + 1)])


def block_length_from_acf(rho: object, band: float) -> int:
    """The plan's rule on rho(1) ... rho(L): the smallest l with RUN consecutive lags from l strictly inside
    the band, or L + 1 if no l <= L - 2 has that. NaN counts as outside."""
    inside = np.abs(np.asarray(rho, dtype=float)) < band
    lags = len(inside)
    for lag in range(1, lags - RUN + 2):
        if inside[lag - 1 : lag - 1 + RUN].all():
            return lag
    return lags + 1


def block_length(values: object) -> int:
    """b for a series, from its own ACF (module docstring)."""
    x = _series(values)
    return block_length_from_acf(sample_acf(x, acf_lags(len(x))), acf_band(len(x)))


def block_count(n: int, b: int) -> int:
    return n // b


def below_floor(n: int, b: int) -> bool:
    """True when fewer than MIN_BLOCKS whole blocks of b fit in n: the comparison is UNRESOLVED."""
    return block_count(n, b) < MIN_BLOCKS


def block_starts(n: int, b: int, replicates: int, rng: np.random.Generator) -> np.ndarray:
    """Each replicate's ceil(n / b) block starts, uniform on 0 ... n - 1: rng.integers(0, n, (replicates, k))."""
    if not 1 <= b <= n or replicates < 1:
        raise ValueError(f"need 1 <= b <= n and at least one replicate, got b {b}, n {n}, {replicates} replicates")
    return rng.integers(0, n, size=(replicates, -(-n // b)))


def circular_block_means(values: object, b: int, starts: object) -> np.ndarray:
    """The mean of each circular-block replicate whose block starts are a row of `starts` (module docstring).

    The sum of the block of b from each position is computed once, on the series with its first b
    values appended (the wrap); a replicate's sum is then k - 1 of those plus one of the shorter last
    block's."""
    x = _series(values)
    n = len(x)
    if not 1 <= b <= n:
        raise ValueError(f"b must be 1 to {n}, got {b}")
    k = -(-n // b)
    starts = np.asarray(starts)
    if starts.ndim != 2 or starts.shape[1] != k or starts.size == 0:
        raise ValueError(f"starts must have shape (replicates, {k}), got {starts.shape}")
    if starts.min() < 0 or starts.max() >= n:
        raise ValueError(f"block starts must be 0 to {n - 1}")
    tail = n - (k - 1) * b  # the last block's length, 1 ... b
    ring = np.concatenate([x, x[:b]])
    full = sliding_window_view(ring, b)[:n].sum(axis=1)
    last = sliding_window_view(ring, tail)[:n].sum(axis=1)
    sums = full[starts[:, :-1]].sum(axis=1) + last[starts[:, -1]]
    return sums / n


def bootstrap_p(values: object, b: int, replicates: int, rng: np.random.Generator) -> tuple[float, np.ndarray]:
    """The two-sided p of E[d] = 0 from the circular block bootstrap of d - mean(d), and the replicates' means."""
    d = _series(values, "d")
    mean = float(d.mean())
    means = circular_block_means(d - mean, b, block_starts(len(d), b, replicates, rng))
    exceed = int(np.count_nonzero(np.abs(means) >= abs(mean)))
    return (1 + exceed) / (replicates + 1), means


def newey_west_t(values: object, lag: int) -> tuple[float, float]:
    """The Newey-West t of mean(d) = 0 with Bartlett weights up to `lag`, and its two-sided normal p.
    A long-run variance of 0 (a constant series) leaves t undefined: refused."""
    d = _series(values, "d")
    n = len(d)
    if not 0 <= lag < n:
        raise ValueError(f"lag must be 0 to {n - 1}, got {lag}")
    dev = d - d.mean()
    variance = float(dev @ dev) / n
    for j in range(1, lag + 1):
        variance += 2.0 * (1.0 - j / (lag + 1)) * float(dev[j:] @ dev[:-j]) / n
    if not variance > 0:
        raise ValueError("the long-run variance is 0, so the Newey-West t is undefined")
    t = float(d.mean()) / math.sqrt(variance / n)
    return t, float(2.0 * stats.norm.sf(abs(t)))


def holm(p_values: object) -> np.ndarray:
    """Holm's adjusted p-values, in the order given (module docstring)."""
    p = np.asarray(p_values, dtype=float)
    if p.ndim != 1 or len(p) == 0 or not np.all((p >= 0) & (p <= 1)):
        raise ValueError("p-values must be a non-empty one-dimensional array in [0, 1]")
    k = len(p)
    order = np.argsort(p, kind="stable")
    stepped = np.minimum(1.0, np.maximum.accumulate((k - np.arange(k)) * p[order]))
    adjusted = np.empty(k)
    adjusted[order] = stepped
    return adjusted


def minimum_detectable_effect(means: object) -> float:
    """(Z_TEST + Z_POWER) x the standard deviation of the bootstrap means."""
    return (Z_TEST + Z_POWER) * float(np.std(_series(means, "means")))


def pw_kn(n: int) -> int:
    """K_n = max(5, ceil(sqrt(log10 n))): how many small autocorrelations in a row end the correlogram."""
    return max(PW_MIN_KN, math.ceil(math.sqrt(math.log10(n))))


def pw_max_block(n: int) -> int:
    """The reference code's cap on the Politis-White block: ceil(min(3 sqrt(n), n / 3))."""
    return math.ceil(min(3.0 * math.sqrt(n), n / 3.0))


def flat_top(s: float) -> float:
    """The trapezoidal flat-top lag window: 1 for |s| <= 1/2, 2 (1 - |s|) for 1/2 < |s| <= 1, else 0."""
    s = abs(s)
    if s <= 0.5:
        return 1.0
    return 2.0 * (1.0 - s) if s <= 1.0 else 0.0


def pw_m_hat(rho: object, band: float, kn: int) -> int | None:
    """The smallest m >= 1 with |rho(m)| ... |rho(m + kn - 1)| all strictly below the band (rho[0] is lag 1),
    or None when no run of kn fits in the lags given. NaN counts as outside."""
    inside = np.abs(np.asarray(rho, dtype=float)) < band
    for m in range(1, len(inside) - kn + 2):
        if inside[m - 1 : m - 1 + kn].all():
            return m
    return None


def pw_block_from_acv(acv: object, n: int) -> float:
    """(2 G^2 / D_CB)^(1/3) n^(1/3) from the autocovariances R(0) ... R(M), M = len(acv) - 1 >= 1 (no cap).
    A flat-top long-run variance g(0) of 0 leaves it undefined: refused."""
    r = np.asarray(acv, dtype=float)
    lags = len(r) - 1
    if r.ndim != 1 or lags < 1:
        raise ValueError(f"need R(0) ... R(M) with M >= 1, got shape {r.shape}")
    k = np.arange(1, lags + 1)
    weights = np.array([flat_top(j / lags) for j in k])
    g0 = float(r[0] + 2.0 * (weights @ r[1:]))
    big_g = float(2.0 * ((weights * k) @ r[1:]))
    if g0 == 0.0:
        raise ValueError("the flat-top long-run variance g(0) is 0, so the Politis-White block is undefined")
    d_cb = 4.0 / 3.0 * g0 * g0
    return (2.0 * big_g * big_g / d_cb) ** (1.0 / 3.0) * n ** (1.0 / 3.0)


def politis_white_block_length(values: object) -> float:
    """The Politis-White (2004; Patton, Politis and White 2009) block length for the circular bootstrap
    (module docstring), a real number from 0 to the cap. A constant series has no ACF: refused."""
    x = _series(values)
    n = len(x)
    kn = pw_kn(n)
    m_max = math.ceil(math.sqrt(n)) + kn
    if m_max >= n:
        raise ValueError(f"n = {n} is too short for the Politis-White rule, which reads {m_max} lags")
    rho = sample_acf(x, m_max)
    if np.isnan(rho).any():
        raise ValueError("a constant series has no autocorrelation, so no Politis-White block length")
    m = pw_m_hat(rho, PW_C * math.sqrt(math.log10(n) / n), kn)
    lags = m_max if m is None else min(2 * m, m_max)
    dev = x - x.mean()
    acv = [float(dev[: n - k] @ dev[k:]) / n for k in range(lags + 1)]
    return min(pw_block_from_acv(acv, n), float(pw_max_block(n)))


def c2_block(b_v1: int, b_pw: float) -> int:
    """Rule C2: max(b_v1, ceil(1.5 b_PW))."""
    return max(int(b_v1), math.ceil(C2_MULTIPLIER * b_pw))


def c2_block_length(values: object) -> tuple[int, int | None, float | None]:
    """Rule C2 on a series: (b, b_v1, b_PW). A constant series gets b = 1 and no b_v1 or b_PW (module docstring)."""
    x = _series(values)
    if np.all(x == x[0]):
        return 1, None, None
    b_v1, b_pw = block_length(x), politis_white_block_length(x)
    return c2_block(b_v1, b_pw), b_v1, b_pw


def ewc_dof(n: int) -> int:
    """nu = floor(0.4 n^(2/3)), exactly: the largest integer nu with (nu / 0.4)^3 <= n^2, that is 125 nu^3 <= 8 n^2."""
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    nu = math.floor(0.4 * n ** (2.0 / 3.0))
    while 125 * (nu + 1) ** 3 <= 8 * n * n:
        nu += 1
    while nu > 0 and 125 * nu**3 > 8 * n * n:
        nu -= 1
    return nu


def ewc_weights(values: object, nu: int) -> np.ndarray:
    """Lambda_1 ... Lambda_nu = sqrt(2 / n) sum_t cos(pi j (t - 1/2) / n) d_t; exactly 0 for a constant series."""
    d = _series(values, "d")
    n = len(d)
    if not 1 <= nu < n:
        raise ValueError(f"nu must be 1 to {n - 1}, got {nu}")
    if np.all(d == d[0]):
        return np.zeros(nu)
    t = np.arange(1, n + 1) - 0.5
    j = np.arange(1, nu + 1)
    return math.sqrt(2.0 / n) * (np.cos(np.pi * np.outer(j, t) / n) @ d)


def ewc_test(values: object) -> dict[str, float | int | bool | None]:
    """The EWC t test of E[d] = 0 (module docstring): nu, Omega, t, the two-sided p and the minimum detectable
    effect. Omega = 0 with mean 0 gives p = 1 (t undefined); with a mean that is not 0, UNRESOLVED (no p)."""
    d = _series(values, "d")
    n = len(d)
    nu = ewc_dof(n)
    if nu < 1:
        raise ValueError(f"n = {n} gives nu = 0 cosine weights")
    lam = ewc_weights(d, nu)
    omega = float(lam @ lam) / nu
    mean = float(d.mean())
    critical = float(stats.t.ppf(0.975, nu) + stats.t.ppf(0.80, nu))
    if omega == 0.0:
        resolved = mean == 0.0
        return {"nu": nu, "omega": 0.0, "t": None, "p": 1.0 if resolved else None, "unresolved": not resolved, "mde": 0.0 if resolved else None}
    t = math.sqrt(n) * mean / math.sqrt(omega)
    return {"nu": nu, "omega": omega, "t": t, "p": float(2.0 * stats.t.sf(abs(t), nu)), "unresolved": False, "mde": critical * math.sqrt(omega / n)}
