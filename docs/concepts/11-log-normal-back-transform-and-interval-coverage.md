# 11 · The log-normal back-transform, and interval coverage under fat tails

The models forecast the logarithm of the price. This note covers what exponentiating that forecast
gives (the median of the price, not its mean: the PR/FAQ's mistake 4), how far apart the two are,
what an interval's coverage is and how it is tested, and what changes when the shocks have fat tails
and when their volatility clusters. Concept note 10 covers the point forecasts and their scores.

## First principles

A model of the log price gives, for each forecast day, a **normal distribution** with mean μ and
variance s². The price is the exponential of the log price, so it has a **log-normal**
distribution. The exponential bends the scale: it stretches the upper side and squeezes the lower
side. Three summaries of the price then differ:

- the **median**, the value with half the probability on each side. exp is increasing, so the median
  of exp(X) is exp of the median of X: **exp(μ)**. This is what the course calls the forecast.
- the **mean**, the probability-weighted average: **exp(μ + s²/2)**, above the median, because the
  stretched upper side pulls it up.
- the mode, exp(μ − s²), below both; nobody reports it.

Which one to report depends on the loss: the mean minimises expected squared error, the median
expected absolute error (concept note 10). Reporting exp(μ) "as the expected price" is the mistake;
reporting it as the median is fine.

An **interval** at level L is a range the model gives probability L. Its **coverage** over a window
is the share of days whose actual value fell inside. If the model's distribution is right, the
coverage is close to L, and each day is inside or not independently of the others with probability L.

## The maths

**The mean of a log-normal.** If X ~ N(μ, s²), the moment generating function of a normal gives
E[e^X] = e^(μ + s²/2). So

$$
\frac{\text{mean}}{\text{median}} = e^{s^2/2}, \qquad \text{gap} = e^{s^2/2} - 1 \approx s^2 / 2 .
$$

Worked: one day ahead the AIC model's s is about 0.0185 log points (√σ² with σ² = 0.000344,
`fit.json`), so the gap is e^(0.000172) − 1 = 0.0172%. On the static path s² grows with the
horizon; 227 days ahead the AIC model's s is 0.2557, and the gap is e^(0.2557²/2) − 1 = 3.32%. At
the end of the 689-day static path from the last test day, s is 0.4452 and the gap 10.42%
(milestone-4 walkthrough, Measured results).

**Intervals.** The normal interval is μ ∓ z s on the log scale, with z the normal quantile at
(1 + L)/2: 1.2816 at 80% and 1.9600 at 95%. The dollar bounds are exp of the log bounds: exp is
increasing, so the probability carries over exactly, and the dollar interval is not symmetric about
the median.

**A Student-t of the same variance.** The milestone-3 residuals have fat tails: a t fitted to the
AIC model's standardised residuals has ν = 3.41 degrees of freedom. A t on ν > 2 has variance
ν / (ν − 2), so the t scaled by √((ν − 2)/ν) has variance 1, the same as the normal. Its interval
is μ ∓ k s with k = t_ν⁻¹((1 + L)/2) × √((ν − 2)/ν). With ν = 3.407: k = 1.019 at 80% and 1.914 at
95%, both **below** the normal's 1.282 and 1.960. With the variance fixed, the fat-tailed shape puts
more of its probability near the centre and in the far tails and less in the shoulders, so its
central intervals are narrower. From about the 95.7% level up the t interval is the wider one: the
two are equal at 95.68% (AIC model), 95.73% (BIC) and 95.95% (course), and at 99% the t's half-width
is 3.34 standard deviations against the normal's 2.58 (milestone-4 walkthrough, `t_crossover.py`;
`tests/test_forecasting.py` checks the t is wider at 99.9%).

**Only the df is milestone 3's.** The milestone-3 fit is a location-scale t: for the AIC model's
standardised residuals, location 0.029 and scale 0.6817 on 3.407 df. A t on 3.407 df scaled to
variance 1 has scale 0.6426, so the fitted t has variance 0.6817² × 3.407 / 1.407 = 1.125, not 1. The
intervals here take its df alone and build the variance-matched t on it, centred on μ.

**Kupiec's test of coverage.** If x of n days fell inside an interval of level L, and the days are
independent with probability L each, x is binomial. Kupiec (1995, "Techniques for verifying the
accuracy of risk measurement models", Journal of Derivatives 3(2), 73–84) compares the likelihood
at L with the likelihood at the observed rate x/n:

$$
\text{LR} = -2\left[x \ln L + (n - x)\ln(1 - L) - x \ln\tfrac{x}{n} - (n - x)\ln\left(1 - \tfrac{x}{n}\right)\right] ,
$$

about χ² on 1 degree of freedom. Worked (`tests/test_evaluation.py`): 10 of 10 inside an 80%
interval gives LR = −20 ln 0.8 = 4.463 and p = 0.035: too wide at 5%. So does 5 of 10, from the
other side: too narrow.

## Assumptions

- **The log price is normal given the past**, with the variance the model states. The interval
  inherits both: the shape (normal or t) and the scale (s).
- **The model's variance is right for the window.** An ARIMA has one σ², estimated on the training
  data. Its forecast variance depends on the horizon, never on how volatile the market is now.
- **Kupiec's test needs independent days.** That holds for one-step forecasts if the model is right.
  A static path's days share one origin and one accumulated error, so they are far from independent:
  its coverage is shown and not tested.
- **The forecast variance leaves out the parameters' uncertainty.** statsmodels' forecast variance
  treats the estimates as the truth, so every interval is a little too narrow.
- **The mean needs the normal.** exp(μ + s²/2) is the mean of exp(X) for a normal X. For a Student-t
  X, of any degrees of freedom, E[exp(X)] is infinite: the t's tails fall like a power, slower than
  exp grows, so the integral diverges. The variance-matched t intervals are fine (they use quantiles,
  which exp carries over), but under the t the price has no finite mean, and `mean_usd` is the
  log-normal's. The page's mean line is that, not a t-model's mean.

## Where it breaks

**Two causes of wrong coverage, and how to tell them apart.** An interval can miss for its **scale**
(s is too small or too large for the days scored) or for its **shape** (the standardised error is
not distributed as the interval assumes). Volatility clustering feeds both: a calm year puts the
scale too high, and a window that mixes calm and stormy days has standardised errors with fat tails
even if each day's shock were normal. They look alike in a coverage table. The milestone-4
walkthrough separates what it can on AAPL: it divides each one-step error by its sd_log, and
measures the root mean square of the result in each window (1 if the scale is right) and the
coverage after rescaling to that window's realised scale (what is left is the shape), then rescales
by a trailing average of past squared errors to remove the clustering it can follow. For the AIC
model: in the test window the errors are 0.66 times the stated sd (2023 was calm: the daily return's
sd was 0.0122, against 0.0189 in training), so every interval is too wide, and rescaled the normal's
coverage is 0.824 at 80% and 0.956 at 95%: the scale was the cause. In the out-of-sample window the
scale over the whole window is close (0.95), and the standardised errors have a kurtosis of 10.7.
Part of that kurtosis is volatility clustering inside the window, not the shape of each shock:
dividing each error instead by a trailing average of the squared errors before it (an exponentially
weighted one, λ = 0.94) lowers it to 6.8. The normal 80% interval's over-coverage survives both
rescalings (0.864 after the window's scale, 0.853 after the trailing one), so what remains after the
clustering this probe removes is a shape with more errors near the centre than a normal has; the
variance-matched t covers 0.810. A trailing average removes only the clustering it can follow, so
"shape" here means what is left, not fat tails proved.

**Long horizons.** The error of an h-step forecast is a weighted sum of h future shocks. By the
central limit theorem a sum of many fat-tailed shocks is closer to normal than any one of them, so a
t with the one-step ν overstates the tails of a long static path. The t intervals are meant for the
one-step forecasts; on the static paths they are shown for comparison.

**A long upper tail on a dollar axis.** (Every dollar figure in milestone 4 is a dividend-adjusted
close, `prices.json`'s `price_basis` `adjusted_close`; the log errors do not depend on it.) A static
path's 95% band 689 days out spans dollar values
that differ by a factor of about e^(2 × 1.96 × 0.445) ≈ 5.7 for the AIC model, so on a linear dollar
axis the band dwarfs the price. The page offers a log price axis, on which the band is symmetric.

## In this project

- `src/arima_forecasting/forecasting.py:227` `forecast_rows`: median, mean and the eight dollar
  bounds from `mean_log` and `sd_log`; `:123` `t_multipliers`, the variance-matched t.
- `src/arima_forecasting/evaluation.py:195` `coverage` (the bounds count as inside), `:171`
  `kupiec`, `:187` `coverage_verdict`.
- `src/arima_forecasting/payloads.py`: the reader recomputes every dollar value from `mean_log` and
  `sd_log`, checks each t quantile by evaluating the t's CDF at it, and recomputes each coverage
  count from the rows.
- `tests/test_forecasting.py`: the hand-worked row, a million log-normal draws whose mean is
  exp(μ + s²/2) and whose median is exp(μ), the t's variance and quantiles.
