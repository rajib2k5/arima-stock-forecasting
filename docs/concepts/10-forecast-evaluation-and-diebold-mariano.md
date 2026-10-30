# 10 · Forecast evaluation: static and walk-forward, the random walk, RMSE, MAE and MAPE, and Diebold–Mariano

Course modules 9 and 10 make one forecast of the whole test period and print three error numbers.
This note covers what a forecast is scored against, the two ways of making forecasts over a window,
what each error metric rewards and where it misleads, and the test milestone 4 uses to ask whether a
model's forecasts are better than the random walk's: Diebold and Mariano's, with Harvey, Leybourne
and Newbold's small-sample correction. Concept note 11 covers the dollar back-transform and the
intervals.

## First principles

A **forecast** is a statement made on one day, the **origin**, about a later day. The number of days
between them is the **horizon** h. A forecast may use only what was known on its origin. Anything
later that leaks into it is **look-ahead**, and it makes a forecast look better than any real one.

Two ways to forecast a window of n days:

- **Static multi-step** (the course's). One origin, the day before the window, and one path of
  forecasts for horizons 1, 2, …, n. Nothing that happens inside the window is used. For an ARIMA
  model of the log price the path soon becomes a straight line: the effect of the last few shocks
  dies out, and what is left is the last value plus h times the drift (or the last value, with no
  drift). That is the "almost flat line" of the PR/FAQ's mistake 2. It answers "where will the price
  be in h days?", for one origin.
- **Walk-forward one-step**. A new origin every day: the forecast of day t is made on day t − 1 with
  every observation up to t − 1. It answers "how good is the model at tomorrow?", n times. Here the
  parameters stay at the training estimates and only the model's state (its memory of recent values
  and shocks) moves with each new day. A **refit** variant also re-estimates the parameters, here
  every 21 trading days on all the data before the block.

A score means nothing alone. The **random walk** is the baseline every price forecast must beat:
tomorrow's log price is today's. If prices are a martingale (no predictable change, the weak form of
market efficiency), it is the best forecast there is under squared error, and a model that cannot
beat it has learned nothing usable. One step ahead it is yesterday's value; static, it is the
origin's value on every day of the window, a flat line. It needs no estimate at all.

## The maths

**The static path of the course model.** ARIMA(0, 1, 1) without a drift says the daily change is
r_t = ε_t + θ ε_(t−1). Its forecast from origin T is

$$
\hat y_{T+1} = y_T + \theta \hat\varepsilon_T, \qquad \hat y_{T+h} = \hat y_{T+1} \text{ for } h \ge 2 ,
$$

a flat line after one day, with variance σ²(1 + (h − 1)(1 + θ)²). With the course model's θ =
−0.0788 and σ² = 0.000354 (`fit.json`), 227 days ahead that is 0.000354 × (1 + 226 × 0.8486) =
0.0683, a standard deviation of 0.2612 log points, which is the exported `sd_log` of the course
model's last static test day (milestone-4 walkthrough, Measured results).

**The metrics.** With actual values a_t, forecasts f_t and errors e_t = a_t − f_t over n days:

$$
\text{RMSE} = \sqrt{\tfrac{1}{n}\textstyle\sum e_t^2}, \qquad
\text{MAE} = \tfrac{1}{n}\textstyle\sum |e_t|, \qquad
\text{MAPE} = \tfrac{100}{n}\textstyle\sum |e_t| / |a_t| .
$$

Worked: actuals 100, 110, 90 against forecasts 105, 100, 90 give errors −5, 10, 0, so RMSE =
√(125 / 3) = 6.455, MAE = 5 and MAPE = 100 × (0.05 + 0.0909 + 0) / 3 = 4.697%
(`tests/test_evaluation.py`).

What each rewards: the forecast that minimises expected squared error is the **mean** of the
forecast distribution, and the one that minimises expected absolute error is its **median**. So
RMSE prefers the mean, MAE the median (concept note 11: for a price the two differ). RMSE weighs a
few large errors heavily; MAE does not.

**Diebold–Mariano.** Two forecasts of the same days, with losses L(e) (squared or absolute), give
the **loss differential** d_t = L(e_model,t) − L(e_rw,t). The null hypothesis is that its expected
value is 0: the two forecasts are equally accurate in expectation. Diebold and Mariano (1995,
"Comparing predictive accuracy", Journal of Business & Economic Statistics 13(3), 253–263) use

$$
\text{DM} = \frac{\bar d}{\sqrt{\hat V / n}}, \qquad
\hat V = \hat\gamma_0 + 2 \sum_{k=1}^{h-1} \hat\gamma_k ,
$$

with γ̂_k the sample autocovariance of d at lag k (divisor n). For an h-step forecast the errors of
nearby days overlap, so d is autocorrelated up to lag h − 1; for h = 1 only γ̂₀ is kept. DM is
asymptotically N(0, 1). Harvey, Leybourne and Newbold (1997, "Testing the equality of prediction
mean squared errors", International Journal of Forecasting 13(2), 281–291) found it rejects too often
in small samples and proposed

$$
\text{DM}^* = \text{DM}\,\sqrt{\frac{n + 1 - 2h + h(h-1)/n}{n}} ,
$$

compared with a Student t on n − 1 degrees of freedom. At h = 1 the factor is √((n − 1)/n), and
DM* becomes exactly the one-sample t statistic of d against 0: γ̂₀ uses the divisor n, the sample
variance s² the divisor n − 1, so √((n − 1)/n) / √(γ̂₀ / n) = 1 / √(s² / n). `tests/test_evaluation.py`
checks this against scipy's `ttest_1samp`, an implementation independent of ours.

Worked, on five made-up errors (`tests/test_evaluation.py`): model errors 0.01, −0.02, 0.03, 0,
−0.01 and random-walk errors 0.02, −0.01, 0.01, 0.02, −0.03. Squared loss gives d = −0.0003,
0.0003, 0.0008, −0.0004, −0.0008: mean −8 × 10⁻⁵, γ̂₀ = 1.588 × 10⁻⁶ / 5 = 3.176 × 10⁻⁷, DM =
−8 × 10⁻⁵ / √(3.176 × 10⁻⁷ / 5) = −0.3174, DM* = −0.3174 × √0.8 = −0.2839 on 4 degrees of
freedom: no difference at any usual level.

## Assumptions

- **d is covariance stationary**, with a finite variance: the test is about its mean over the
  window. A change in volatility regime inside the window bends this.
- **For h = 1, d is serially uncorrelated**, so γ̂₀ is its long-run variance. That holds when both
  forecasts are made from day t − 1's information and the loss differential has no predictable part
  left. **On AAPL it is not established either way** (milestone-4 walkthrough, DM assumptions). In
  the test window Ljung–Box at lag 10 finds no autocorrelation in d (p 0.25 to 0.87). In the
  out-of-sample window it does for the squared loss of every model (p below 0.001; lag-1
  autocorrelation 0.16 to 0.26) and for the absolute loss of BIC's and the course's (p 0.001); but
  Ljung–Box assumes equally variable terms, and d's variance clusters and its tails are heavy. A
  regression of d_t on its own five lags with White's (HC0) standard errors "finds" the lags for the
  squared loss of BIC (p 0.0008) and the course model (p 0.0056), yet that test is itself fooled by
  these series: under a sign-flip null that keeps every |d_t − mean| where it is and has no
  autocorrelation at all, it rejects at nominal 5% in 38% (BIC) and 49% (course) of draws, and
  calibrated against that null its p-values are 0.15 and 0.34. So the evidence of autocorrelation
  goes no further than what heavy tails and clustering produce on their own.
- **The γ̂₀ test is correctly sized here; the squared-loss verdicts are fragile anyway.** Under the
  same sign-flip null the HLN statistic against t(n − 1) rejects at 5% in 4.0% to 5.7% of draws, for
  every model, window and loss. What makes the out-of-sample squared-loss verdicts borderline is
  how few days carry them: five days hold 60% to 74% of the sum of (d_t − mean)², and a circular
  block bootstrap of the mean of d gives p-values that move across 5% with the block length (BIC:
  0.116, 0.048 and 0.014 with blocks of 5, 10 and 20 days; the AIC model 0.083, 0.028 and 0.018).
  A Newey–West variance moves them too: at 9 lags BIC's, the AIC model's and the AIC refit's
  squared-loss p-values are 0.043, 0.023 and 0.039, against 0.048, 0.080 and 0.109 with γ̂₀, so it is
  not only BIC's verdict that depends on the variance. The absolute-loss "worse than the random walk"
  verdicts are robust: every p is at most 0.024 with γ̂₀, with Newey–West at 6 and 9 lags, and with
  blocks of 5, 10 and 20 days. ADR-0003's condition to revisit the test (autocorrelation that a
  robust test confirms) is not met; γ̂₀ stays the exported variance (LEARNING_LOG, "Decisions and
  defaults").
- **The forecasts are given.** DM compares two series of forecasts, not two models in the abstract
  (Diebold 2015, "Comparing predictive accuracy, twenty years later", Journal of Business & Economic
  Statistics 33(1)). For the walk-forward rows the parameters were estimated once, on the training
  split, and held fixed; the four refit rows re-estimate them every 21 trading days on the data before
  each block. Either way the test is of those forecasts, not of the model with its estimation error.
- **Two-sided, at 5%.** A rejection says the expected losses differ over this window. "No
  difference" is not evidence that they are equal: the test may have had too little power.

## Where it breaks

**Volatility clustering, measured.** How often does DM* reject at 5% when the null is true? Simulated
(2,000 runs each, seed 20261029, the script in the milestone-4 walkthrough): a random-walk log price,
and two one-step forecasts on each side of the best one, y_(t−1) ± 0.001 × sign(r_(t−1)), so their
expected losses are equal by symmetry.

| Returns | n | Squared loss | Absolute loss |
|---|---|---|---|
| iid normal | 227 | 5.20% | 4.55% |
| iid normal | 689 | 4.20% | 5.10% |
| GARCH(1, 1), t(4) shocks | 227 | 4.45% | 4.65% |
| GARCH(1, 1), t(4) shocks | 689 | 4.75% | 4.50% |
| GARCH, two forecasts with their own clustered error parts | 227 | 12.55% | 14.20% |

With sampling error of about ±1 percentage point, the first four rows are at 5%: clustering and fat
tails do not break the test in this set-up, where both forecasts are made from the day before:
for squared loss the differential is (r − c)² − (r + c)² = −4 c_t r_t, with c_t known on day t − 1
and r_t unpredictable, so it has no predictable part and no autocorrelation, whatever its variance
does. The last row breaks it: when each forecast's error carries its own clustered part,
unknown on the day before, d inherits the clustering, its autocorrelation is not in γ̂₀, and the test
rejects 2.5 (squared) and 2.8 (absolute) times as often as it should. That is the case to watch for.

**Multi-step forecasts.** A static path's errors share one origin: the error at day h contains every
shock since the origin, so d is autocorrelated up to lag h − 1 and the window holds one path, not n
independent comparisons. DM is not run on the static paths here.

**Many tests.** Milestone 4 runs 16 DM tests (four one-step forecasts, two windows, two losses).
At 5% with every null true, 16 × 0.05 = 0.8 rejections are expected by chance, whether or not the
tests depend on each other. Dependence changes the spread instead: the rows share days and nearly
share forecasts, so false rejections would come in clusters (several at once, or none). A single
rejection among them is weak evidence; a pattern across losses and models is also weaker than it
looks, for the same reason.

**The metric traps.**

- **RMSE and MAE in dollars scale with the price.** (Every dollar figure in milestone 4 is a
  dividend-adjusted close, `prices.json`'s `price_basis` `adjusted_close`.) AAPL's mean close was $237.48 in the
  out-of-sample window against $173.57 in the test window (1.37 times), and the one-step random
  walk's RMSE goes from $2.09 to $4.04 (milestone-4 walkthrough); part of that is the price level and
  part the larger daily moves. Dollar metrics compare forecasts of the same days; across windows,
  compare log-point metrics or ratios to the random walk.
- **MAPE** divides by the actual: it is undefined at 0, and it treats an error of the same size as
  larger when the price is low.
- **The course's MAPE is NaN.** It subtracts a one-column DataFrame (yfinance 1.7.0's `Close`) from
  a Series, and pandas lines the Series' index up against the DataFrame's column labels, not its
  rows, so every cell is missing. `evaluation._vector` refuses anything but one-dimensional numbers
  (`tests/test_evaluation.py` reproduces the NaN on made-up numbers).
- **A static path scored against a flat random walk** rewards a drift: a model with a drift beats the
  flat line in a rising market whether or not anything else in it is right. The milestone-4
  walkthrough measures how much of the AIC model's static advantage is its drift.

## In this project

- `src/arima_forecasting/forecasting.py:134` `static_forecast`, `:142` `walk_forward` (one filter
  pass at fixed parameters), `:150` `walk_forward_loop` (the explicit append loop it is tested
  against), `:164` `refit_walk_forward` (every 21 days); `src/arima_forecasting/evaluation.py:217`
  `random_walk_forecasts`, the random walk built from each window's origin and actual rows.
- `src/arima_forecasting/evaluation.py:104` to `:114` RMSE, MAE and MAPE on one-dimensional arrays,
  `:129` the HLN factor, `:142` `dm_test`, `:134` `dm_verdict`.
- `src/arima_forecasting/payloads.py` `_t_sf`: Python's reader recomputes each p-value from DM* and
  its degrees of freedom with the regularised incomplete beta function, no scipy.
- `tests/test_evaluation.py`: the hand computation, the t-test identity, the boundary of each verdict.
