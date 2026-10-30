# ADR-0002: How the ARIMA order (p, d, q) and its trend term are chosen

**Status:** Accepted (milestone 0); implemented in milestone 2 (selection) and milestone 3 (the fit). Milestone 2's measurements are in the section "Measured in milestone 2".
**Date:** 2026-10-28
**Deciders:** the learner, with the milestone-0 architect session

---

## Context

An ARIMA(p, d, q) model of a log price has three dials:

- **d**: how many times we difference the series before modelling it. For a stock price, d = 1
  means "model the daily log returns".
- **p**: how many past values of the (differenced) series feed the prediction (the AR part).
- **q**: how many past forecast errors feed the prediction (the MA part).

There is a fourth dial that is easy to miss: the **deterministic trend term**. For d = 1 it is
a *drift*, the average daily log return. Over the roughly 226-day test segment, a drift of about
0.0009 per day adds about 0.2 to the log price, so the drifting dollar forecast ends roughly 22%
above a flat one (e^0.2 − 1; measured against the drifting forecast, the flat one is 18% lower). For a
stock that rose for most of the sample, this one parameter can matter more than p and q put
together.

### What the course does

The course: (1) runs `pm.auto_arima(df_log, test='adf', max_p=5, max_q=5, seasonal=False,
stepwise=True)` on the **full** 2015–2023 series, also passing `start_p=1, start_q=1` (pmdarima's
defaults are 2 and 2), `error_action='ignore'`, `suppress_warnings=True` and arguments that do
not change the search here (`m=1`, `d=None`, `start_P=0`, `D=0`, and `trace=True`, which only
prints); (2) splits 90/10 by position; (3) refits `statsmodels` `ARIMA(train, order=auto.order)`;
(4) makes one static multi-step forecast.

Checking that recipe against the installed libraries turned up three problems. Each is
measured below on a simulated log-price random walk with drift (2,000 days, drift 0.0008,
daily standard deviation 0.017, seed 20261028; no market data was downloaded).

**Simulation setup, enough to reproduce every number in this ADR:**

- `rng = numpy.random.default_rng(20261028)`, then
  `y = numpy.log(30.0) + numpy.cumsum(0.0008 + 0.017 * rng.standard_normal(2000))`: the log
  price starts from ln 30 (a price of 30) and takes 2,000 daily steps.
- **"The training part"** is the first 1,800 values, `y[:1800]` (90%, split by position). The
  forecast table in problem 2, the stepwise search in problem 3, the ADF comparison in §2, the
  training-part figures in §3, the (1,1,1) intercept and drift in §4, the failure injection and
  starved-fit warnings in §5 and the AIC cross-check in §7 use it. The 200-step forecasts start
  after day 1,800, and "actual" is the last value, `y[1999]`.
- **"The simulated series"** is all 2,000 values. The log-likelihood table and the cross-d AIC
  comparison in §3, and the `trend='t'` estimate in §4, use it.
- **"The course's arguments"** means the full list above. Leaving out `m`, `d`, `start_P` and
  `D` gives the same five fits (measured). Dropping `start_p=1, start_q=1` as well changes the
  search (problem 3) but not the choice or the forecast in problem 2 (measured). Versions are
  listed at the end of this ADR. A runnable script for the forecast table
  and the likelihood identity is in [`docs/milestones/00-scaffold.md`](../milestones/00-scaffold.md)
  (Results, Q5 and Q6).

1. **Leakage.** Choosing the order on the full series lets the test period influence the model
   that is then "tested" on it. The test score is no longer an honest out-of-sample number.
2. **The refit silently drops the drift.** With d = 1, `auto_arima`'s default
   `with_intercept='auto'` *starts* the search with an intercept (`pmdarima/arima/auto.py:623-624`:
   the starting value is `True` when `d + D` is 0 or 1). The stepwise search then also tries
   models without it (`pmdarima/arima/_auto_solvers.py:312-314, 440-445`), so the final model
   may or may not have one. Here it does, and pmdarima passes it as `trend='c'` to a statsmodels
   `SARIMAX` (`pmdarima/arima/arima.py:488-499`). In SARIMAX the constant sits in the
   *differenced* equation, so it is a drift. But statsmodels `ARIMA` defaults to **no trend**
   whenever d ≥ 1 (`statsmodels/tsa/arima/model.py:156-160`), and the course passes only the
   order. So step (3) fits a different model from the one step (1) selected. Measured, 200-step
   forecast of the final log price:

   | Model | Forecast | Note |
   |---|---|---|
   | pmdarima, as selected: (0,1,0) + intercept | 5.0529 | drifts upward |
   | course refit: statsmodels `ARIMA(train, order=(0,1,0))` | 4.8874 | flat, equal to the last training value |
   | actual (simulated) | 5.1442 | |

   A gap of 0.1655 in log price, caused by a default nobody chose, is about 18% in dollars when
   measured against the flat forecast: pmdarima's forecast is e^0.1655 − 1 = 18.0% above it.
   Measured against pmdarima's forecast, the flat one is 1 − e^−0.1655 = 15.3% below. (Background
   §10 quotes its own example on the second base: there the flat forecast is 37% below.)
3. **The 3D AIC landscape needs cells the stepwise search never visits.** The stepwise
   algorithm (`pmdarima/arima/_auto_solvers.py:276-466`) walks from a starting order to
   neighbouring orders and stops when no neighbour improves the AIC. Measured on the training
   part of the simulated series, with the course's arguments: **5 fits of 4 distinct orders**
   out of the 36 (p, q) cells for that d. They are (1,1,1), (0,1,0), (1,1,0) and (0,1,1), each
   with an intercept, then (0,1,0) again without one. With pmdarima's default start
   (`start_p=2, start_q=2`) it made 6 fits of 5 distinct orders, starting at (2,1,2).

The course also forward-fills with `fillna(method='ffill')`. In pandas 3.1.0 that keyword no
longer exists (`pandas/core/generic.py:7230-7237`), and the call raises
`TypeError: NDFrame.fillna() got an unexpected keyword argument 'method'` (measured). The port
uses `.ffill()`. This belongs to milestone 1, but it is recorded here because it is the same
kind of finding: course code that no longer means what it says.

## Decision

### 1. Selection uses the training split only

Every step that *chooses* something (unit-root tests for d, the AIC grid for p, q and trend,
the pmdarima cross-check) runs on the first 90% of the course window, split by position. The
last 10% (the test segment) and the 2024-01-01 → 2026-10-01 out-of-sample window are never
seen by any selection step.

Differencing and rolling statistics may be *displayed* over the whole series because they are
pointwise (the value at day t uses only days t and t−1, or a trailing window), so they leak
nothing. Anything *estimated* (test statistics, fitted parameters, AIC) uses train only.

### 2. d comes from unit-root tests, decided before any AIC is compared

On the training log price, at levels (d = 0), first differences (d = 1) and second differences
(d = 2), run both:

- **ADF** (`statsmodels.tsa.stattools.adfuller`, defaults `regression='c'`, `autolag='AIC'`;
  `statsmodels/tsa/stattools/_stattools.py:233-242`). Null hypothesis: *there is a unit root*.
  Rejecting it is evidence for stationarity.
- **KPSS** (`statsmodels.tsa.stattools.kpss`, defaults `regression='c'`, `nlags='auto'`;
  `_stattools.py:3051-3055`). Null hypothesis: *the series is stationary*. Rejecting it is
  evidence against stationarity.

The two tests have opposite nulls, which is why we run both: each guards against the other's
blind spot.

**Rule:** d is the smallest value in {0, 1, 2} at which ADF rejects *and* KPSS does not reject,
at the 5% level. If no d satisfies both, take the smallest d at which KPSS does not reject (the
same test pmdarima uses by default; 2 if KPSS rejects at every d) and set `tests_conflict: true` in the artifact so the app
and the write-up say so.

Two details matter when reading the numbers:

- **KPSS p-values are clipped.** statsmodels interpolates the KPSS p-value from a table that
  covers only 0.01 to 0.10. Outside that range it returns the boundary and issues an
  `InterpolationWarning` (`_stattools.py:3205-3235`). A reported "0.01" means "0.01 or
  smaller". The contract carries this as `p_value_bound`.
- **statsmodels 0.15.0 warns about the return type.** `adfuller` and `kpss` now issue a
  `FutureWarning` unless `result_object=` is passed (`_stattools.py:279-291, 465-475`). Pass
  `result_object=True` explicitly so the code does not change meaning in 0.16.

**Cross-check with pmdarima.** pmdarima picks d with `ndiffs` before its search, using
`test='kpss'` by default (`pmdarima/arima/auto.py:351, 545-553`; `pmdarima/arima/utils.py:128`),
whereas the course passes `test='adf'`. pmdarima's ADF and KPSS are its **own**
implementations, not statsmodels' (`pmdarima/arima/stationarity.py:104, 215`). Its ADF regresses
on a constant, a trend and a fixed ⌊(n−1)^(1/3)⌋ lagged differences. The code computes
`k = trunc((n−1)^(1/3)) + 1` (`stationarity.py:326-335`), but that k is the embedding width:
the regression takes `z[:, 1:k]` (`:289`), which is k − 1 lags. It therefore equals statsmodels'
`adfuller(regression='ct', maxlag=⌊(n−1)^(1/3)⌋, autolag=None)`: on the training part
(n = 1,800, so 12 lags) both give τ = −0.642439, and 13 lags would give −0.719864 (measured).
statsmodels' default `adfuller` instead uses a constant only and chooses the lag by AIC. So the
two libraries can disagree on borderline series. We record pmdarima's `ndiffs` for `kpss`, `adf`
and `pp` next to our own verdict. A disagreement is reported, not hidden. (On the simulated
series all three gave d = 1.)

### 3. AIC is compared only within one d, never across different d

This is the subtle part, and the 3D landscape is built around it.

statsmodels' `ARIMA` handles d *inside* the state-space model: it never passes
`simple_differencing` to its `SARIMAX` parent (`statsmodels/tsa/arima/model.py:199-211`), so
the SARIMAX default `simple_differencing=False` applies (`statsmodels/tsa/statespace/sarimax.py:344`).
The d "integration" states get an approximate diffuse prior (a huge variance, meaning "we have
no idea where the level starts"), and the first d observations are **burned**: excluded from
the log-likelihood (`sarimax.py:669-683`, `loglikelihood_burn = k_states − k_order = d`).

Measured on the simulated series:

| Order | `loglikelihood_burn` | `nobs_effective` | llf |
|---|---|---|---|
| ARIMA(1,0,0) | 0 | 2000 | 5330.48 |
| ARIMA(0,1,0) | 1 | 1999 | 5331.60 |
| ARIMA(1,1,0) | 1 | 1999 | 5331.63 |
| ARIMA(0,2,1) | 2 | 1998 | 5328.30 |

And the clincher: ARIMA(1,1,0) fitted to the log *levels* has llf **5331.629**; an ARMA(1,0)
without a constant fitted to the log *differences* also has llf **5331.629**. The d = 1
likelihood *is* the likelihood of the differenced series.

The two likelihoods are on the same scale: one is a joint density and the other a conditional
one. Differencing maps (y₁, y₂, …, yₙ) to (y₁, Δy₂, …, Δyₙ) with Jacobian 1, so densities carry
over unchanged. For d = 1, with the diffuse start and the burn, statsmodels' log-likelihood is
log p(Δy₂ … Δyₙ) = log p(y₂ … yₙ | y₁): a conditional density of n − 1 observations. For d = 0
it is the joint log p(y₁ … yₙ) = log p(y₁) + log p(y₂ … yₙ | y₁). So the d = 0 number contains
one extra term, log p(y₁) under the stationary prior, and conditions on less. Measured on the
simulated series: d = 0 ARIMA(1,0,0) + const has AIC −10654.96 and d = 1 ARIMA(0,1,0) + drift
has AIC −10664.60, a gap of 9.64. The extra term is log p(y₁) = −1.166 nats; removing it (at the
d = 0 fitted parameters) leaves a gap of 7.31 on the common sample y₂ … yₙ. On the training
part the same numbers are −1.074, and a gap of 8.50 before and 6.35 after.

That correction does not make the comparison valid, which is the real reason for this rule. A
d = 1 model is a d = 0 model with one AR root fixed at z = 1, so "d = 0 or d = 1?" is a test for
a unit root. AIC's 2k penalty comes from asymptotics for regular models (true parameter inside
the parameter space, estimates asymptotically normal at rate √T). At a unit root neither holds:
φ = 1 is on the boundary of the stationary region the d = 0 model is fitted in, and φ̂
converges faster than √T (at rate T for a driftless random walk, with the Dickey–Fuller limit).
So the penalty is not calibrated for choosing d. Unit-root tests have critical values derived
for exactly this case, so they choose d, and AIC compares models only within that d. This is
the practitioners' convention too (FPP3 §9.6: information criteria guide p and q, not d); the
boundary problem is the reason the convention holds even after the log p(y₁) term is
removed.

**Consequences for the design:**

- d is fixed by the unit-root tests (step 2) before any AIC is looked at.
- The landscape is drawn **one d at a time**, each with its own AIC axis. The app must never
  overlay surfaces for different d on a shared AIC scale.
- Within one d, every fit must score exactly the same observations. That requires
  `enforce_stationarity=True` (the default). With `enforce_stationarity=False`, statsmodels
  treats *all* states as diffuse and the burn grows with p (`sarimax.py:679-683`). Measured:
  burn = 2 for ARIMA(0,1,0) and burn = 3 for ARIMA(2,1,0), which would make AIC incomparable
  even within d = 1. The grid also keeps `simple_differencing=False`, `concentrate_scale=False`
  and the same training sample for every cell.

**Rejected alternative: compare across d on a common footing.** Putting the likelihoods on a
common footing *is* possible: differencing is a linear map with Jacobian 1 (a unit
lower-triangular matrix), so if every fit, d = 0 included, burned the same first observations
(`loglikelihood_burn = 2` for all), the likelihoods would be of the same data. We do not do
this. It removes the log p(y₁) term but not the boundary problem above, so the AIC gap would
still not be a calibrated choice of d. It is also non-standard (pmdarima, which ports R's
`auto.arima`, fixes d with a test first and compares AIC only within that d,
`auto.py:545-553`), hard to verify, and it would make our AIC numbers disagree with every
textbook and library a reader might check them against. **It would win if** the unit-root
tests were inconclusive for this series and we wanted a likelihood-based tie-break for d,
reported as a tie-break and not as a test.

### 4. The trend term is part of the model, chosen explicitly

statsmodels `ARIMA` puts trends in the *levels* equation, as "regression with ARIMA errors"
(docstring, `statsmodels/tsa/arima/model.py:104-118`). A constant cannot survive differencing,
so it **rejects** `trend='c'` when d ≥ 1 with a `ValueError` (`model.py:178-190`; measured).
The way to get a drift with d = 1 is `trend='t'` (a linear time trend in levels, which
differences into a constant). Measured: ARIMA(0,1,0) with `trend='t'` estimates 0.000868, and
the mean of the log differences is 0.000873.

| d | Trend variants fitted | Why |
|---|---|---|
| 0 | `'c'` | A stationary log price needs a mean. `'c'` is statsmodels' default for d = 0 (`model.py:157-158`). |
| 1 | `'n'` (no drift) **and** `'t'` (drift) | The question that matters most for the static forecast. Both variants score the same data with the same burn (measured: burn = 1 for both, AIC = −2·llf + 2k exactly), so AIC can choose between them. |
| 2 | `'n'` | A drift in d = 2 would be a quadratic trend in log price. Not plausible for a stock, and d = 2 is in the grid only to show what over-differencing looks like. |

**pmdarima's intercept is not the same number as statsmodels' drift.** In SARIMAX, the
constant c enters as φ(L)·Δyₜ = c + θ(L)·εₜ (`sarimax.py:234-235`), so the implied drift is
c / (1 − φ₁ − … − φₚ). Measured for (1,1,1): pmdarima's intercept is 0.000146, implying a drift
of 0.000804; statsmodels' `trend='t'` coefficient is 0.000823. The parameter is reported as
`drift` in the contract, with the library's own name kept alongside.

### 5. The grid, and how failures are recorded

- **Orders:** p, q ∈ {0, …, 5} (pmdarima's `max_p`/`max_q` defaults and the course's values,
  `auto.py:336-338`); d ∈ {0, 1, 2} (pmdarima's `max_d=2`, `auto.py:337`). With the trend
  variants above: 36 + 72 + 36 = **144 fits**.
- **Fitter:** statsmodels `ARIMA(train, order, trend).fit()`. Its default estimation method is
  `'statespace'` (`model.py:325-335`), which uses L-BFGS with `maxiter=50` by default
  (`statsmodels/tsa/statespace/mlemodel.py:532-541`). The grid uses one fixed `maxiter` for every
  cell, recorded in the artifact (proposed: 200; the exact value is a milestone-2 setting), so
  all cells are treated the same. No cell gets a retry with different settings. (Revised in the
  milestone-2 fix round: every cell is fitted from several starts with those same settings; see
  "Revised in the milestone-2 fix round" below.)
- **Per cell we record:** AIC, AICc, BIC, llf, number of parameters, `nobs_effective`,
  `mle_retvals['converged']`, every warning raised during the fit (captured with
  `warnings.catch_warnings(record=True)`), the largest inverse AR and MA root moduli, and a
  `status`:

  | status | Meaning | Eligible for selection? | Drawn in the landscape? |
  |---|---|---|---|
  | `ok` | converged, roots safely inside the unit circle | yes | yes |
  | `not_converged` | optimiser stopped at `maxiter`; statsmodels raised `ConvergenceWarning` (`statsmodels/base/model.py:656-665`) | no | yes, hollow marker |
  | `near_unit_root` | an inverse AR root or an inverse MA root has modulus > 0.99 (the threshold pmdarima uses, `_auto_solvers.py:42`; the grid checks AR and MA separately, unlike pmdarima, see below) | no | yes, flagged |
  | `failed` | the fit raised; AIC is `null` and `error` holds the message | no | yes, as a gap |

  Nothing is dropped. pmdarima does the opposite:
  - **Failed fits are dropped.** A fit that raises `LinAlgError` or `ValueError` gets IC = ∞
    and is filtered out (`_auto_solvers.py:507-532, 564-566`); any other exception aborts the
    whole search. Whether the drop is *silent* depends on `error_action`. With the default
    `'trace'` (`auto.py:362`), each failure emits a `ModelFitWarning` that includes the
    traceback (`_auto_solvers.py:515-524`). Only `error_action='ignore'`, the course's setting,
    makes it silent. Measured with a `ValueError` injected into the (1,1,1) fit on the training
    part: (1,1,1) was dropped both times, with one `ModelFitWarning` under the default and none
    under `'ignore'`.
  - **Near-unit-root fits get IC = ∞** (`_auto_solvers.py:42-43`), but pmdarima's root test
    has a quirk. `_root_test` sets `max_invroot` from the AR roots and then, when q > 0,
    **overwrites** it with the MA roots instead of taking the larger of the two
    (`_auto_solvers.py:37-40`). So whenever q > 0, an AR root near the unit circle is ignored.
    Measured with stub models: an ARMA(1,1) with an inverse AR root of 0.999 and an inverse MA
    root of 0.2 kept its IC of 10.0; an AR(1) with the same AR root got ∞.
  - **Warnings inside a fit are hidden** when `suppress_warnings=True`, `auto_arima`'s default
    (`auto.py:361`; `arima.py:528-530`). Measured: a deliberately starved fit (ARIMA(5,1,5),
    `maxiter=3`) raised three warnings through plain statsmodels and through `pmdarima.ARIMA`
    with its default `suppress_warnings=False`: two `EstimationWarning`s (non-stationary
    starting AR parameters and non-invertible starting MA parameters, each replaced by zeros)
    and one `ConvergenceWarning`. With `suppress_warnings=True` it raised **none**.
- **No timings** in the artifact. Fit times change on every run and would break byte-identical
  exports.

### 6. Selection rule

Among cells with `status == "ok"` and `d == d_selected`, pick the (p, q, trend) with the lowest
AIC. Ties are broken by fewer parameters, then smaller p + q. Also report every cell within
2 AIC units of the best (a common rule of thumb for "about equally supported"), so the write-up
can say honestly when the choice is a near tie. BIC is recorded for every cell; where BIC
prefers a smaller model the write-up says so. (AICc is recorded too, but with about 2,000
training days its correction is tiny.)

### 7. pmdarima stays, as the course-faithful selector and a cross-check

Run `auto_arima` on the **training split** twice: once with the course's arguments (the full
list under "What the course does", including `start_p=1, start_q=1` and
`error_action='ignore'`) and once with pmdarima's defaults plus `seasonal=False`. Record the
chosen order, `with_intercept`, AIC, and every fit the search kept (`return_valid_fits=True`,
which leaves out failed fits and fits whose IC the root test set to ∞). Then compare with the
grid:

- **d should agree.** If not, the reason is one of the test differences in step 2.
- **(p, q) may differ.** Stepwise is a local search, it uses `maxiter=50` (`auto.py:358`), and
  its root test discards some models the grid keeps as `near_unit_root` (and, because of the
  overwrite quirk in §5, keeps some ARMA models whose AR root the grid flags). A difference is
  reported with its reason, not treated as an error.
- **The same order should give nearly the same AIC.** Measured on the same training data:
  (0,1,0) + drift, pmdarima −9597.077 and statsmodels −9597.077; (1,1,1) + drift, pmdarima
  −9593.682 and statsmodels −9593.199. The 0.48 gap does not come from nearby stopping points.
  pmdarima stopped at φ̂ = 0.818, θ̂ = −0.828 and statsmodels at φ̂ = 0.004, θ̂ = 0.004. Both lie
  on the ridge φ ≈ −θ, where the AR and MA factors nearly cancel and the model is close to white
  noise (Background §5), but at opposite ends of it. The likelihood is so flat along the ridge
  that the two ends differ by only 0.24 in log-likelihood. The cross-check uses a tolerance of
  1 AIC unit, not equality, and records the parameters so that a gap like this can be
  explained.

**Why not let pmdarima build the landscape?** It could come close: `stepwise=False` takes the
exhaustive path (`auto.py:626-651`), but its default `max_order=5` keeps only cells with
p + q ≤ 5 (`_auto_solvers.py:88-95`), which is 21 of 36. Even with `max_order=None`, it searches
one d only, drops failed fits (silently under the course's `error_action='ignore'`), hides
warnings inside each fit by default (`suppress_warnings=True`), and parameterises the trend
differently from the statsmodels `ARIMA` that every later milestone uses. A short grid loop of
our own over statsmodels avoids all four problems. So the grid is a *choice*, not something forced on us. It would lose
to pmdarima's exhaustive mode if we stopped needing failed cells, warnings and per-d surfaces.

### 8. Fallback if pmdarima breaks

pmdarima 2.1.1 installs from an official `cp312 manylinux_2_17_aarch64` wheel and imports
cleanly with numpy 2.5.4 (checked in a separate session). It is a compiled package that has
lagged numpy releases before, so the design does not depend on it for any number used later:

- the unit-root tests, the grid, the fit, the forecasts and the metrics are pure statsmodels;
- pmdarima appears only in the `pmdarima_check` block of the `aic_grid` artifact and in the
  `ndiffs` cross-check of `stationarity`, both of which can be
  `{"status": "unavailable", "reason": "<import error>"}`;
- the code imports pmdarima inside the cross-check function, not at module top level, so a
  missing pmdarima breaks one block, not the package.

If a future environment cannot install it, remove it from `pyproject.toml`; the pipeline then
runs as a pure statsmodels grid and the app shows "cross-check unavailable".

## Options considered

| Option | Verdict | Why |
|---|---|---|
| Course recipe: `auto_arima` on the full series, refit with defaults | Rejected | Leakage, plus the silent drift drop (measured above). Kept as a *comparison track* so the write-up can show its effect. |
| `auto_arima` on train only, use its model directly | Rejected as primary | No full landscape, failed fits dropped, SARIMAX trend parameterisation differs from the downstream `ARIMA`. Kept as cross-check. |
| statsmodels grid on train, d by unit-root tests, trend explicit (chosen) | **Accepted** | Full landscape, every failure visible, one library from selection to forecast. |
| Choose d by AIC across d | Rejected | The d = 0 likelihood also scores y₁, and even on a common sample the comparison is a unit-root test, for which AIC's penalty is not calibrated (section 3). |
| Choose by out-of-sample error (time-series cross-validation on train) | Rejected for now | Arguably better for forecasting, but it is a different lesson. AIC is what the course teaches and what the landscape shows. **Would win if** the project's question became "which order forecasts best" rather than "which order fits best". |
| BIC instead of AIC | Rejected as the rule, recorded per cell | AIC matches the course and pmdarima's default (`information_criterion='aic'`, `auto.py:349`). |

## Consequences

- **Easier:** every claim about the choice of order can be checked cell by cell; the course's
  silent drift drop becomes a visible, explainable lesson; pmdarima can break without breaking
  the project.
- **Harder:** 144 fits instead of about 6, so the export takes longer (still minutes at most;
  to be measured in M2). Three surfaces instead of one, and the app must enforce the
  "one d at a time" rule.
- **To revisit:** the `maxiter` value once real AAPL fits show how many cells fail to converge;
  whether d = 0 should also try `'ct'` (trend-stationary log price) if KPSS with
  `regression='ct'` ever suggests it.

## Measured in milestone 2 (2026-10-29)

The design held. These measurements settle the items left open above. The commands and dates are in
the [milestone-2 walkthrough](../milestones/02-stationarity-and-identification.md#measured-results).

- **d.** On the training log price ADF does not reject (τ = −0.407, p = 0.909) and KPSS rejects
  (η = 6.8235, p ≤ 0.01): a unit root. On the first difference ADF rejects and KPSS does not: d = 1,
  no conflict. pmdarima's `ndiffs` gives 1 with KPSS, ADF and PP.
- **`'ct'` at d = 0** (the "to revisit" item). KPSS with a trend still rejects on the log price
  (η = 0.7538 against a 1% critical value of 0.216), so a trend-stationary d = 0 model is not
  suggested. Both regressions are reported in `stationarity.with_trend`.
- **`maxiter`** (the "to revisit" item). 200 is kept. In the first export 47 of the 144 cells needed
  50 or more iterations; after the fix round 72 kept runs did (the most 184). The cells that did not
  converge stopped after 0 or 1 iterations with scipy's `warnflag` 2, a failed line search, not the
  limit. So §5's description of `not_converged` ("stopped at `maxiter`") is too narrow: the status
  means "the optimiser reported no convergence", for either reason, and the artifact records which.
- **pmdarima's cross-check** (§7). With the course's arguments it chose (0, 1, 1) with an intercept,
  0.0001 AIC from our cell. With its defaults it chose (2, 1, 2) without one, and that fit stopped at
  its `maxiter=50` without converging; statsmodels reproduces its AIC bit for bit at 50 iterations and
  converges 7.56 lower at 62. The ±1 tolerance of §7 holds only when both fits reach the same
  optimum (corrected in the fix round; it first said "for converged fits only"): pmdarima's default
  run also fitted (2, 1, 2) with an intercept, the same model as our (2, 1, 2) with a drift, and that
  fit converged (41 iterations) at AIC −10402.059, 34.806 above ours. The artifact records
  `converged` and `iterations` for each run.
- **The choice** (§6), as corrected in two fix rounds. ARIMA(3, 1, 4) with a drift, AIC −10440.245:
  the best the documented search found, not a proven optimum. The search found seven other cells
  within 2, all with a drift, a lower bound: (2, 1, 4) +0.036, (4, 1, 3), (4, 1, 2), (2, 1, 5),
  (3, 1, 5), (5, 1, 2) and (5, 1, 3); a gap of a few hundredths of AIC means nothing. (The first
  export said ARIMA(3, 1, 5) with no other cell within 2, and the first fix round ARIMA(2, 1, 4); both
  rested on local optima, below.) BIC prefers ARIMA(2, 1, 2) without a drift. The low cells share
  near-cancelling complex AR and MA roots (a 2.3-day cycle), and about three quarters of the chosen
  model's gain over ARIMA(0, 1, 1) with a drift, at the grid's recorded parameters, comes from 72
  trading days, 2020-02-15 to 2020-05-31. With
  near-cancelling roots AIC's penalty is unreliable and over-selection is expected, and a gain that
  concentrated may not generalise; milestone 4's out-of-sample test is the arbiter. The rule is not
  changed after seeing the result.
- **Export time** (Consequences). The 144 single-start fits took 84 s with one BLAS thread and
  352 s with OpenBLAS's default thread pool on this 20-core machine, with bit-identical results; the
  exporter sets one thread. That export took 60.7 s. With several starts per cell, perturbed padded
  starts and the polish stage (two fix rounds) the grid makes 3,890 runs on 16 worker processes, and
  the whole export took 6 min 50.2 s on a machine shared with other jobs (load average about 21 on 20 cores): about seven times longer.
- **Two refinements of the planned contract.** The PACF uses `method='ywm'`, `plot_pacf`'s default and
  so the course's picture, not `pacf`'s `'ywadjusted'`. The stationarity artifact carries no series
  rows: for three transforms they would add 1,680,767 bytes, past the 1 MB budget, and the d = 0
  series is already in `prices.json`.

## Revised in the milestone-2 fix round (2026-10-29)

The review of milestone 2 found that one optimiser run per cell, from statsmodels' default start,
had left many cells at local optima: 94 pairs of `ok` cells at d = 1 in which a model scored a lower
log-likelihood than a smaller model it nests, by up to 21.8. That is impossible at the maxima, so the
landscape, many `delta_aic` values and the near ties rested on where the optimiser happened to stop.
§5's "no retry" is replaced by the following. Every run still uses the settings of §5.

- **Starts.** Each cell is fitted from statsmodels' default start; from each fitted model of the grid
  one step smaller (the next smaller p, the next smaller q, or no trend), its estimates padded with
  zeros, which is exactly that model and so starts the optimiser at its likelihood; and, when p and q
  are both at least 1, from 24 random starts (AR and MA coefficients drawn N(0, 1) in the
  optimiser's unconstrained space, so every start is stationary and invertible, seeded by the cell).
  Cells are fitted after the cells they nest, so the padded starts exist.
- **Which run is kept.** The highest log-likelihood. A converged run is kept instead of a higher
  unconverged one only when it is at most 1e-4 lower (about ten times L-BFGS's own stopping
  resolution here, 1.1e-5). If the kept run did not converge it is restarted once from its own
  estimates (", polished"). The cell records the winning start (`start`) and its number of runs
  (`starts_tried`); `refit_cell` reproduces a committed cell from that start alone.
- **The nesting rule.** No fitted cell may score more than 2e-3 of log-likelihood below a model it
  nests (11 grid steps times 1e-4, rounded up; 0.004 of AIC). The fitting guarantees it, and both
  readers refuse a file that breaks it (contract §3.6).
- **Deterministic.** The random starts are seeded per cell, the runs go to a pool of worker processes,
  and neither the pool size nor the finishing order changes a result: a serial fit of the whole grid
  and a pooled one gave identical cells.
- **Round 2: stalls and the polish stage.** A second review found that a zero-padded start can sit
  exactly at the smaller model's optimum, where L-BFGS cannot move, and still be reported converged:
  seven cells tied a nested model's likelihood, and the then choice, ARIMA(2, 1, 4), was 0.037 AIC
  above an ARIMA(3, 1, 4) point the search had missed. Each padded start now also has two perturbed
  copies (the new AR or MA coefficients set to small seeded values of both signs, in the optimiser's
  unconstrained space), and a polish stage refits every `ok` cell within 4 AIC of the best of its d,
  and every cell tied with a model it nests, from every such cell's estimates by Nelder-Mead and then
  L-BFGS, followed by a repair of any nesting break. No cell now ties a model it nests. The kept run's
  estimates are recorded per cell (`params`), and the readers pin the nesting tolerance at 2e-3
  instead of reading it from the file.
- **What it does not do.** It does not prove any cell is at its global maximum. With the round-1
  L-BFGS starts alone the choice was the same with 2, 6, 12 and 24 random starts while the near ties
  were not (3, 5, 4 and 6 others); Nelder-Mead from other cells' estimates then moved the choice
  itself. So the choice is the best this search found, and the near-tie list is a lower bound. The
  milestone-2 walkthrough has the measurements.

## Measured in milestone 3 (2026-10-29)

Milestone 3 fitted the §6 choice, BIC's choice and the course's own model, and tested their
residuals. The rules above are unchanged. The commands and every value are in the
[milestone-3 walkthrough](../milestones/03-fit-and-diagnostics.md#measured-results).

- **The course's recipe on AAPL** ("What the course does"). Problem 1, the leak: `auto_arima` with the
  course's arguments ran on 2,264 rows, 227 of them from the test period, and chose (0, 1, 1) with an
  intercept; the same search on the 2,037 training rows (§7's `"course"` run) chose the same. So the
  leak is real in the procedure and changed nothing measurable in the order here. Problem 2, the
  dropped drift, holds on real data: the course's refit `ARIMA(train, order=(0, 1, 1)).fit()` has no
  trend; with a drift the same order estimates 0.000899 log points per day (p 0.021 with OPG errors),
  and its AIC is 3.546 lower.
- **The §6 choice's residuals.** ARIMA(3, 1, 4) with a drift, refitted from the grid's recorded
  estimates (llf within 5.0e-10 of the grid's). Ljung–Box with p + q = 7 degrees of freedom removed
  cannot test lag 5; at lags 10 and 20 it finds no autocorrelation (p 0.185 and 0.489). Jarque–Bera
  rejects normality (kurtosis 7.03), and ARCH-LM finds volatility clustering (p 2.4e-50 at 5 lags,
  2.6e-53 at 10; 29 of 50 squared-residual ACF bars past the band). The course's model leaves clear
  autocorrelation at lags 10 and 20 (p 6.6e-8 and 1.5e-8). BIC's choice is rejected at lags 5 and 10
  (p 0.018 and 0.039), but only by the rule the project states, any applied lag below 0.05 with no
  adjustment for testing three lags: Holm's adjustment across its three lags gives 0.0545 at the
  smallest, and a Box–Pierce statistic made robust to volatility clustering gives p 0.117, 0.384
  and 0.566 (it still rejects the course's model, p 0.0048 at lag 10). In-sample, the AIC choice
  passes Ljung–Box, the course's model fails it, and BIC's choice fails it only narrowly; all three
  fail the other two tests.
- **The near-cancelling roots** (§7's ridge, in more dimensions). The choice's complex AR pair
  −0.842 ± 0.398i lies 0.0625 from its MA pair −0.782 ± 0.414i; its real AR root −0.465 and MA root
  −0.683 are 0.218 apart. Its AR and MA coefficients come out large, opposite in sign and imprecise
  (`ar.L1` −2.150 with OPG error 0.166, against 0.024 for BIC's choice, whose pair is 0.037 apart but
  nearer the unit circle). The project flags pairs within 0.1 as a display rule (contract §3.7); it
  is not a test and does not change the selection.
- **What it settles.** Nothing in §6 changes after seeing these results. Milestone 4's out-of-sample
  test remains the arbiter between the AIC choice and its simpler rivals.

## Verified library behaviour (versions pinned in `pyproject.toml`)

Paths are relative to the virtual environment's `site-packages`. "Measured" values come from
offline probes on simulated data (statsmodels 0.15.0, pmdarima 2.1.1, pandas 3.1.0,
numpy 2.5.4, Python 3.12, aarch64).

| Claim | Source |
|---|---|
| `ARIMA` default trend is `'c'` without integration, `'n'` with it | `statsmodels/tsa/arima/model.py:156-160` |
| `ARIMA` rejects trend terms of lower order than d | `statsmodels/tsa/arima/model.py:178-190` |
| `ARIMA` does not pass `simple_differencing`, so SARIMAX's default `False` applies | `statsmodels/tsa/arima/model.py:199-211`, `statsmodels/tsa/statespace/sarimax.py:344` |
| Diffuse states and `loglikelihood_burn` | `statsmodels/tsa/statespace/sarimax.py:669-683` |
| `ARIMA.fit` defaults to `method='statespace'` | `statsmodels/tsa/arima/model.py:325-335` |
| MLE fit defaults: L-BFGS, `maxiter=50` | `statsmodels/tsa/statespace/mlemodel.py:532-541` |
| `ConvergenceWarning` when `converged` is False | `statsmodels/base/model.py:656-665` |
| SARIMAX trend enters the differenced equation | `statsmodels/tsa/statespace/sarimax.py:234-235` |
| `adfuller` defaults; `FutureWarning` without `result_object` | `statsmodels/tsa/stattools/_stattools.py:233-242, 465-475` |
| `kpss` defaults; p-value clipped to [0.01, 0.10] with `InterpolationWarning` | `_stattools.py:3051-3055, 3205-3235` |
| `auto_arima` defaults: `test='kpss'`, `max_p=5`, `max_q=5`, `max_d=2`, `maxiter=50`, `suppress_warnings=True`, `with_intercept='auto'` | `pmdarima/arima/auto.py:330-374` |
| d fixed by `ndiffs` before the search | `pmdarima/arima/auto.py:545-553` |
| `with_intercept='auto'` sets the *starting* value (intercept when d + D ∈ {0, 1}); the stepwise search also fits without it and toggles it | `pmdarima/arima/auto.py:623-624`; `pmdarima/arima/_auto_solvers.py:312-314, 440-445` |
| pmdarima builds `SARIMAX(trend='c')` when it has an intercept | `pmdarima/arima/arima.py:488-499` |
| Warnings silenced when `suppress_warnings=True` | `pmdarima/arima/arima.py:528-530` |
| Failed fits (`LinAlgError`, `ValueError`) get IC = ∞ and are filtered; a `ModelFitWarning` unless `error_action='ignore'` | `pmdarima/arima/_auto_solvers.py:507-532, 564-566`; `pmdarima/arima/auto.py:362` |
| Near-unit-root fits get IC = ∞ (threshold 0.99); the MA roots overwrite the AR result when q > 0 | `pmdarima/arima/_auto_solvers.py:25-51` (overwrite at `:37-40`) |
| Exhaustive mode keeps p + q ≤ `max_order` | `pmdarima/arima/_auto_solvers.py:88-95` |
| pmdarima's own ADF/KPSS; ADF uses ⌊(n−1)^(1/3)⌋ lagged differences | `pmdarima/arima/stationarity.py:104, 215, 289, 326-335` |
| `fillna` has no `method` keyword in pandas 3.1.0 | `pandas/core/generic.py:7230-7237` |
