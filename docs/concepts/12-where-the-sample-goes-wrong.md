# 12 · Where the sample goes wrong: selection on the test set, the drift, the burn-in, and two crashes

The milestone-5 walkthrough measures what each mistake of the sample course costs on AAPL. This note
covers the ideas underneath: why choosing a model on data it is later scored on is a flaw even when it
changes nothing, why a drift matters 227 days ahead and not one day ahead, how two libraries write the
same drift as different numbers and how one default drops it, why the first residual of a d = 1 model
is a price level, and the two library behaviours that stop the course's code. The static path's shape
and the scores are in concept note 10; the median and the mean in concept note 11.

## First principles

**A test set is data the model never influenced.** Every choice made while building a model (the
order, the trend, the differencing) is a function of the data it was made on. If the test rows are in
that data, the score on them measures the whole procedure, choices included, on data it has already
seen. The bias is towards looking good: a choice made with the test rows in view tends to suit them.
It can be zero on a given series (the choice comes out the same either way) and still be a flaw,
because nothing in the procedure stops it from being large on the next one.

**A drift is a slope in the log price.** At d = 1 the model describes the daily change. A constant in
that change, the drift μ, adds μ to every day: after h days, μh. Shocks add up too, but their sum
grows like √h, not like h. So the drift is invisible one day ahead and dominant far ahead.

**A model's parameters are only as named as the library that holds them.** "ARIMA(0, 1, 1) with an
intercept" is a model; how its constant is written, and whether a call includes it at all, is a
library's choice. Moving an order from one library to another without its trend changes the model.

**A filter must start somewhere.** A state-space model forecasts each day from the days before it.
For the first day of a d = 1 model there is no day before, and the level is unknown. The filter starts
it at 0 with a huge variance (an approximately diffuse prior), so the first forecast is 0 and the first
"error" is the first observation itself. That residual says nothing about the model's shocks.

**Labels, not positions.** pandas lines up two objects by their labels before it does arithmetic.
That is what makes `a - b` safe when the rows are in different orders, and what makes it silently wrong
when the labels of one are not the labels of the other.

## The maths

**The drift in two parameterisations.** statsmodels' `ARIMA` puts the trend on the level and the ARMA
part on what is left: with trend `"t"` (a linear time trend, `x1` in the parameter list),

$$
y_t = \beta t + \eta_t, \qquad \phi(L)(1 - L)\eta_t = \theta(L)\varepsilon_t
\quad\Rightarrow\quad \Delta y_t = \beta + \Delta\eta_t ,
$$

so β is the mean daily change, the drift. pmdarima fits through statsmodels' `SARIMAX`, which puts a
constant c inside the differenced equation, φ(L)Δy_t = c + θ(L)ε_t; the mean daily change is then
c / φ(1), where φ(1) = 1 − φ₁ − … − φ_p. For a model with no AR term (φ(1) = 1) the two are the same
number. For the course's ARIMA(0, 1, 1) pmdarima's intercept is the drift: 0.0009097 a day on the full
series, against statsmodels' 0.0008993 for the same order on the training rows.

**The default that drops it.** In statsmodels 0.15, `ARIMA(y, order=(p, d, q))` with no `trend`
argument gets trend `"c"` when the model is not integrated and `"n"` (none) when it is
(`statsmodels/tsa/arima/model.py:156-160`). At d = 1 a constant on the level would be differenced away,
so `"c"` is not allowed there; the only way to keep a drift is to ask for `"t"`. The course asks for
nothing, so its refit has no drift, and no warning says so.

**Is the drift there?** On the 2,037 training days the drift is 0.0008993 with an OPG standard error
of 0.0003885: z = 2.31, p = 0.0206. The AIC is 3.546 lower with it. AIC = −2 llf + 2k, so with one
parameter more the likelihood-ratio statistic is the AIC gap plus 2, 5.546, and its χ²(1) p-value is
0.0185. Two tests of the same question, close to each other: the drift is supported at 5%, not
overwhelmingly.

**Why it matters far ahead and not one day ahead.** For ARIMA(0, 1, 1) with a drift, the forecast
error after h days has variance σ²(1 + (h − 1)(1 + θ)²) (concept note 10; the filter's own variance
converges to it, and on the course's 2,037 training days it is within 2.4e-7, relative), and the drift moves the
forecast by μh. With the course order's estimates with the drift (μ = 0.0008993, θ = −0.0816,
σ² = 0.00035308), the ratio of the drift's move to the error's standard deviation is

| h (days) | μh (log points) | standard deviation | ratio |
|---|---|---|---|
| 1 | 0.0009 | 0.0188 | 0.048 |
| 21 | 0.0189 | 0.0794 | 0.238 |
| 227 | 0.2041 | 0.2601 | 0.785 |
| 689 | 0.6196 | 0.4530 | 1.368 |

One day ahead the drift is 5% of the noise: dropping it cannot be seen in a one-step score (the
walkthrough measures $2.096 with it and $2.102 without, against the random walk's $2.087). At the end of
the test window it is 78% of the noise, and at the end of the out-of-sample window more than the noise:
a static path with the wrong drift, or none, is wrong by more than its own band suggests.

**One point and the sample's moments.** Add one value A to n − 1 values with standard deviation s and
kurtosis κ. When A² / n is large against s², A sets both moments:

$$
\text{kurtosis} \approx \frac{A^4 / n}{\left(A^2/n + s^2\right)^2} \;\to\; n \text{ as } A \to \infty .
$$

The course's first residual is A = 3.1852 among n = 2,037 with s = 0.01879: A² / n = 0.00498 against
s² = 0.000353, so the one point carries 93.3% of the sample variance and 99.998% of the fourth moment,
and the kurtosis is 1,774.27 (the formula gives 1,776 with these rounded inputs), against 7.76 without
it: 228.5 times as large. Read without the burn-in, the shocks look far heavier-tailed than they are.

**The diffuse start, in numbers.** statsmodels' ARIMA starts the level with mean 0 and variance 10⁶.
The first one-step forecast is 0 and its variance is 10⁶ + σ²(1 + θ²): the level's 10⁶ plus the MA part's
own variance, because only the level gets the diffuse prior and the MA part starts from its stationary
distribution (1,000,000.00036 for the course's refit; 10⁶ + σ² alone is 2.2e-6 short),
so the first residual is y₁ = 3.18518 and its standardised value is 3.18518 / 1000 = 0.0032. statsmodels
marks it with `loglikelihood_burn` = 1 (the likelihood leaves it out) and drops it from its own
diagnostic plots, by max(`loglikelihood_burn`, `nobs_diffuse`).

**Alignment by label.** For a Series s with index I and a one-column DataFrame f with index I and
column "AAPL", `s - f` broadcasts s across f's rows, matching s's labels (dates) to f's column labels.
The result has the union of the two label sets as columns, every date and "AAPL", and no pair of labels
matches, so every cell is NaN. Its mean is NaN. Nothing raises.

**A date index with no frequency.** To forecast h days past the sample, statsmodels must name h new
dates. A DatetimeIndex of trading days has no frequency (holidays break any regular step), so it cannot.
In statsmodels 0.15, `get_forecast` on such a model raises a `ValueError` whose message starts "No
supported index is available" (`statsmodels/tsa/base/tsa_model.py:445`).

## Assumptions

- **The leak argument** assumes the choice could depend on the test rows. On AAPL it did not: both
  searches chose the same order. The claim is about the procedure, not this outcome.
- **The drift arithmetic** assumes the drift is constant: the training rate continues. On AAPL the
  realised mean daily log return was 1.11 times the training drift on the test window and 0.90 times it
  out of sample, so the assumption happened to hold.
- **The moment formula** assumes one point far larger than the rest; with several outliers the same
  logic holds for their sum.
- **The diffuse start** is statsmodels' default for `ARIMA` with d ≥ 1 (an approximately diffuse prior
  on the level, variance 10⁶; the ARMA part starts from its stationary distribution). Another start (an exact diffuse initialisation, or fitting the differenced series,
  which loses the first d observations) changes how the first residual looks, not the fact that it
  carries no information about the shocks.

## Where it breaks

**A drift is a bet on the trend.** The drift that cut the course model's static test RMSE from $25.99
to $10.55 would have added to it had the price turned: a static path with a drift is right only while
the past rate continues. A random walk with the same drift scores almost the same ($10.364 against
$10.547 on the test window), so the gain says nothing about the ARMA part, and nothing in the training
data promised the rate would hold.

**A harmless leak is not evidence of a harmless procedure.** One series where the full-series and
training-only searches agree shows the leak cost nothing there. It does not bound the cost on another
series, and the study does not try to.

**The mean is a normal-theory number.** exp(μ + s²/2) is the mean of the price only if the log price is
normal. Under a Student-t log price the mean of the price does not exist (the t's moment-generating
function is infinite), however many degrees of freedom; the median exp(μ) does. The residuals here have
fat tails (concept note 8), so the dollar mean is a statement about the normal model, not about the
data.

**One test at a time.** The DM verdicts the walkthrough quotes are DM-HLN, per test, uncorrected: 16
tests at 5% each. With every null true, about 0.8 rejections are expected by chance (concept note 10).
A correction for the number of tests, and a variance that allows for clustered volatility, can change
which of the five "worse" verdicts stand; that re-analysis is pre-registered separately and is not
part of this note.

**Library versions move.** The two crashes are statements about statsmodels 0.15, pandas 3.1 and
yfinance 1.7.0. Another version may warn instead of raising, or return a Series instead of a frame;
the tests that reproduce them would then fail and say so.

## In this project

- `src/arima_forecasting/fitting.py:245` `course_track`: the course's search on the full series, its
  refit (`:215` `course_refit`, statsmodels' defaults) and the same order with a drift, written to
  `fit.json`'s `course_track` (`same_order`, `drift_dropped`).
- `src/arima_forecasting/selection.py:773` `pmdarima_trend`: pmdarima's intercept read as a mean at
  d = 0 and a drift at d = 1.
- `src/arima_forecasting/diagnostics.py:63` `burn_in`, statsmodels' rule; `:166` the burned rows,
  exported so the Fit page can show what the course plots.
- `src/arima_forecasting/forecasting.py:106` every model built on a numpy array, so no date index
  reaches statsmodels; `src/arima_forecasting/evaluation.py:86` `_vector`, which refuses a frame.
- `tests/test_fitting.py:173` (the refit has trend `"n"`), `tests/test_diagnostics.py:43` (the first
  residual is the level), `tests/test_forecasting.py:288` (module 9's error), `tests/test_evaluation.py:52`
  (module 10's NaN).
- Every number above is printed by the walkthrough's probe (items 1 to 8, item 8 for this note's own arithmetic) from the committed files, except the two checks of statsmodels' formulas (2.2e-6 and 2.4e-7), which come from `docs/validation/m5-egv-ledger.md`; notebook 05 runs items 1 to 6.
