# 06 · ACF, PACF and their bands

Background [§5](00-background.md#5-arimap-d-q) defines the ACF and the PACF and the textbook
signatures of AR and MA models. This note covers what the shaded band on the course's plots is,
where its formula comes from, why the ACF band widens and the PACF band does not, and why the band
is too narrow for stock returns.

## First principles

The **autocorrelation** at lag $k$ is the correlation between a series and itself $k$ steps earlier.
It runs from −1 to 1. At lag 0 it is 1 by definition. The **ACF** is the list of autocorrelations
at lags 0, 1, 2 and so on.

The **partial autocorrelation** at lag $k$ is the correlation at lag $k$ after removing what the
lags in between already explain. It equals the last coefficient of an AR($k$) model fitted to the
series. The **PACF** is the list of them.

Both are **estimates** from one finite sample. Even pure noise, which has no autocorrelation at all,
gives sample autocorrelations that are not exactly zero. The **band** answers one question: how far
from zero can a sample autocorrelation fall by chance alone? A bar inside the band is consistent
with zero. A bar outside it is a candidate signal, or one of the chance crossings that a 95% band
allows: about 1 lag in 20.

The band is drawn **around zero**, not around the bar. It is the range a bar would fall in if the
true value at that lag were zero, given what the earlier lags show.

## The maths

**The estimates.** With sample mean $\bar x$ and $n$ observations,

$$
r_k = \frac{\sum_{t=k+1}^{n} (x_t - \bar x)(x_{t-k} - \bar x)}{\sum_{t=1}^{n} (x_t - \bar x)^2} .
$$

The denominator does not shrink with $k$. That is the **unadjusted** estimate (`adjusted=False`),
which `plot_acf` uses by default.

The PACF uses the Yule–Walker equations: the AR($k$) coefficients that match $r_1 \dots r_k$, solved
for each $k$. `plot_pacf` uses `method='ywm'`, the version built on the same unadjusted $r_k$. That
choice guarantees a valid stationary AR fit, so every partial autocorrelation lies strictly between
−1 and 1. The `pacf` function's own default, `'ywadjusted'`, divides by $n - k$ instead. On short or
odd series it can reach −1 or beyond: on the eight-point series in `tests/test_identification.py`,
`'ywm'` gives −0.75 at lag 2 and `'ywadjusted'` gives −1.00 with a singular-matrix warning.

**The ACF band (Bartlett's formula).** If the true autocorrelations are zero beyond lag $k - 1$,
the variance of $r_k$ is approximately

$$
\operatorname{Var}(r_k) \approx \frac{1}{n}\left(1 + 2\sum_{j=1}^{k-1} r_j^2\right) .
$$

The 95% band is $\pm z \sqrt{\operatorname{Var}(r_k)}$ with $z = 1.959964$, the 97.5% point of the
normal distribution. At lag 1 the sum is empty, so the band is $z / \sqrt n$. Each later lag adds the
squares of the lags before it, so **the ACF band only widens**. On the training first difference the
widening is small, because the earlier autocorrelations are small: 0.0434 at lag 1, 0.0450 at lag 10
and 0.0465 at lag 50. On the level it is large: 0.0434 at lag 1, 0.188 at lag 10 and 0.420 at lag 50.

**The PACF band.** Under the same null, each partial autocorrelation has variance about $1/n$. So the
band is $\pm z / \sqrt n$ at every lag. For the training first difference, $n = 2036$:
$1.959964 / \sqrt{2036} = 1.959964 / 45.122 = 0.04344$. The artifact stores 0.0434369…, the value
`plot_pacf` draws.

**A worked ACF band.** On the eight-point series $2, 4, 6, 4, 2, 4, 6, 4$ (worked by hand in
`tests/test_identification.py`): $r_1 = 0$, $r_2 = -0.75$, $r_3 = 0$. The bands are
$z\sqrt{1/8} = 0.6930$ at lags 1 and 2 (the lag-1 term is zero), and
$z\sqrt{(1 + 2 \times 0.5625)/8} = 1.959964 \times 0.515388 = 1.0101$ at lag 3.

**How the artifact stores the band.** statsmodels returns a confidence interval around each bar.
`plot_acf` draws `upper − value` as the band around zero (statsmodels/graphics/tsaplots.py:146).
The artifact stores exactly that half-width, so the app draws the same band as `plot_acf`, from the
file, without computing it.

## What the plots show on the training segment

| Series | Lag-1 ACF | ACF bars past the band, lags 1–50 | PACF bars past the band |
|---|---|---|---|
| Log price, d = 0 | 0.9987 | 50 of 50 | 1 of 50 |
| First difference, d = 1 | −0.0805 | 11 of 50 | 7 of 50 |
| Second difference, d = 2 | −0.5360 | 15 of 50 | 20 of 50 |

The counts come from `acf_pacf.json` (notebook 02 prints the ACF ones); the commands are in the
milestone-2 walkthrough.

- **The level** decays from 0.9987 so slowly that every lag is past the band. That is the picture of
  a unit root: shocks do not die out.
- **The second difference** has a lag-1 autocorrelation of −0.536, close to the −0.5 that
  differencing white noise gives (background §3). That is the over-differencing signature the
  unit-root tests do not show (concept note 05).
- **The first difference** has small autocorrelations, but 11 of 50 ACF bars cross a band that
  should be crossed about 2.5 times by chance. The largest are at lag 1 (−0.0805) and at lags 7 to 9
  (+0.092, −0.087, +0.099), alternating in sign.

## Why the band is too narrow for returns

Bartlett's formula assumes the series is a linear process driven by independent shocks with a
constant variance. Daily returns break the last part: calm and stormy periods alternate
(**volatility clustering**). Then the variance of $\sqrt n\, r_k$ is
$\mathbb{E}[\varepsilon_t^2 \varepsilon_{t-k}^2] / \sigma^4$, which is above 1, so the true band is
wider than the drawn one. Background §5 measured this on simulated GARCH(1,1) paths: the lag-1 band
was crossed 12.1% of the time instead of 5%.

The training segment shows the same thing. We measured the first difference three other ways (the
script is in the walkthrough):

| Sample | Lag-1 ACF | Lags 7, 8, 9 |
|---|---|---|
| All training days | −0.081 | +0.092, −0.087, +0.099 |
| 2015 to 2019 only (1,257 returns; band ±0.055) | +0.008 | +0.093, −0.029, +0.046 |
| 2020 to the end of training (779 returns; band ±0.070) | −0.146 | +0.091, −0.131, +0.139 |
| Each return divided by the trailing 21-day standard deviation (2,015 returns; band ±0.044) | +0.002 | +0.049, −0.029, +0.041 |

The lag-1 dip and most of the alternating pattern sit in 2020 onwards, the period that contains the
March 2020 crash, when large returns of opposite sign followed each other. Scaled by recent
volatility, the lag-1 autocorrelation all but vanishes. So most bars past the band are the crash
speaking, not a stable pattern a linear model can forecast. This matters again for the AIC
landscape (concept note 07).

## Assumptions

- The series is stationary. On the level (d = 0) the ACF has no stable meaning, which is the point
  of drawing it: its slow decay is the evidence.
- The band assumes independent shocks with a constant variance, and a normal sampling distribution.
- The ACF band at lag $k$ assumes the true autocorrelations beyond lag $k - 1$ are zero.

## Where it breaks

- **Volatility clustering** makes the bands too narrow, as measured above.
- **Many lags, one band each.** With 50 lags, about 2.5 crossings are expected by chance. A single
  crossing at a high lag is weak evidence.
- **Mixed models.** An ARMA(p, q) with both parts has a decaying ACF and a decaying PACF. Neither
  cuts off, so the plots cannot pin down p and q. That is why the project ranks every (p, q) by AIC
  instead of reading orders off the plots.

## In this project

- `src/arima_forecasting/identification.py:42` computes both correlograms with `plot_acf`'s and
  `plot_pacf`'s settings, stores each band as `upper − value`, and flags each bar past its band
  (`outside`, `:63`: |value| > band, never at lag 0).
- `src/arima_forecasting/identification.py:68` builds the payload for d = 0, 1 and 2, with `z` and
  the counts of flagged bars. The app draws the flags and counts; it never compares a value with its
  band itself.
- `tests/test_identification.py` works the ACF, the PACF and both bands out by hand, and checks that
  the settings are the plots' own defaults.
- The app's Stationarity page draws the bars and the band (`app/src/lib/CorrelogramPlot.tsx`) from
  `acf_pacf.json`.
