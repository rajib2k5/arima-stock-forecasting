# 07 · AIC within one d, failed fits, and what the landscape shows

Background [§6](00-background.md#6-estimation-maximum-likelihood-through-the-kalman-filter) defines
AIC and explains why it is not used to choose d. ADR-0002 §3 to §7 turn that into rules. This note
explains the rules from the ground up, then reads the landscape the grid produced on AAPL's training
segment, including the parts that are surprising.

## First principles

A model with more parameters can always fit the training data at least as well. So "the best fit"
on its own picks the biggest model. An **information criterion** adds a penalty for each parameter.

**AIC** (Akaike's information criterion) is

$$
\text{AIC} = -2 \log L + 2k ,
$$

where $\log L$ is the maximised log-likelihood and $k$ the number of estimated parameters, the
innovation variance included. Lower is better. AIC estimates how well a model would predict new data
from the same process. **BIC** charges $\log n$ per parameter instead of 2. With $n = 2036$
observations that is $\ln 2036 = 7.62$, so BIC prefers smaller models.

**A difference of AIC means something only between models fitted to the same observations.** The
likelihood is a density of the data. Change the data and the number changes for reasons that have
nothing to do with the model.

For ARIMA, the order of differencing d changes the data the likelihood scores:

- at d = 0 the likelihood covers all $n$ log prices, including the first one;
- at d = 1 statsmodels leaves the first observation out (`loglikelihood_burn = 1`) and scores the
  $n - 1$ daily changes;
- at d = 2 it leaves two out.

So **AIC is compared only within one d**. Within one d, every cell must score exactly the same
observations. That holds here: every fit uses `enforce_stationarity=True`, so the burn is d for
every (p, q, trend), and the artifact checks `nobs_effective = n_train − d` in every cell.

Removing the extra first-day term does not rescue a comparison across d. Going from d = 0 to d = 1
fixes one AR root at exactly 1, a value on the edge of what the d = 0 model allows. AIC's penalty of
2 per parameter is derived for parameters inside their space, estimated at the usual $\sqrt n$ rate.
A unit root is neither. So d is chosen by tests built for that question (concept note 05), and AIC
ranks p, q and the trend within it. The same argument returns below, for the order AIC picks
("Over-fitting, stated plainly").

**The trend is part of the model.** At d = 1, statsmodels' `trend='t'` is a drift, the average daily
log return. `'n'` is no drift. Both score the same observations, so AIC can choose between them,
and the grid fits both. A constant (`'c'`) cannot be used at d = 1: differencing removes it, and
statsmodels refuses it with a `ValueError`.

## Several starts per cell

The ARMA likelihood can have several local maxima, and an optimiser run stops at whichever one it
reaches. The milestone-2 review found that one run per cell from statsmodels' default start had left
86 pairs of d = 1 cells in which a model scored a lower log-likelihood than a smaller model it nests.
That cannot happen at the true maxima: setting the bigger model's extra coefficients to zero gives the
smaller model exactly, so the bigger model's maximum is at least as high.

So each cell is now fitted from several starts (`selection.py`):

- statsmodels' default start;
- each model of the grid one step smaller (one fewer AR lag, one fewer MA lag, or no drift), its
  estimates padded with zeros. That start *is* the smaller model, so the optimiser begins exactly at
  its likelihood and L-BFGS never ends lower than it begins;
- two perturbed copies of each padded start, in which the coefficients the smaller model lacks get
  small seeded values, once positive and once negative: a padded start can sit exactly at the smaller
  model's optimum, where L-BFGS's line search cannot move (the second review found seven such cells,
  marked converged);
- for cells with both AR and MA lags, 24 random starts, seeded by the cell.

Then a **polish stage** refits the cells that matter: every `ok` cell within 4 AIC of the best of its
d, and every cell whose log-likelihood ties a model it nests. Each is restarted from every such cell's
estimates (padded or truncated by parameter name) with Nelder-Mead, which does not follow the gradient
and so can leave a stalled point, and then L-BFGS; two rounds, then a repair of any nesting break.

The run with the highest log-likelihood is kept. If it did not converge, it is restarted once from its
own estimates (a "polish"). A converged run is kept instead of a higher unconverged one only when it is
at most $10^{-4}$ lower, about ten times the optimiser's own stopping resolution here. The cell records
which start won (`start`) and how many runs it made (`starts_tried`).

**The nesting rule.** Because every cell starts from the cells it nests, no cell can end below them.
Both readers check it on every file: a fitted cell whose log-likelihood is more than $2 \times 10^{-3}$
below a model it nests is refused as a local optimum. The tolerance is 11 grid steps times
$10^{-4}$, rounded up; in AIC it is 0.004.

Several starts make the grid consistent; they do not prove that any cell sits at its global maximum.
"Where it breaks" shows how the results move with the number of random starts.

## Failed and flagged fits

A grid fit can go wrong in three ways. The project records each one and drops none.

- **failed**: the fit raised an error. The cell has no AIC and keeps the error text.
- **not_converged**: the run the cell kept stopped without meeting the optimiser's (L-BFGS)
  convergence test. statsmodels raises a `ConvergenceWarning`, which the cell keeps, with scipy's
  `warnflag`: 1 means it hit the iteration limit, 2 that it stopped for another reason, usually a line
  search that could not improve.
- **near_unit_root**: the fit converged, but an inverse AR root or an inverse MA root has a modulus
  above 0.99. An AR root there means the fitted series is barely stationary. An MA root there means
  it is barely invertible (the shocks cannot be recovered from the data in a stable way).

An **inverse root** is $1/z$ for each root $z$ of the AR polynomial $1 - \phi_1 z - \dots - \phi_p z^p$,
or of the MA polynomial $1 + \theta_1 z + \dots + \theta_q z^q$. The model is stationary (invertible)
when every inverse AR (MA) root lies strictly inside the unit circle. statsmodels enforces that, so a
fit can approach the circle but not reach it. 0.99 is pmdarima's own threshold. The grid checks AR
and MA roots separately; pmdarima's root test lets the MA result overwrite the AR one when q > 0
(ADR-0002 §5).

Only `ok` cells can be chosen. Every cell is drawn in the landscape, each status with its own marker.

## The maths: one worked comparison

At d = 1, the chosen cell is ARIMA(3, 1, 4) with a drift: $k = 3 + 4 + 1 + 1 = 9$ parameters and
AIC −10440.245. Its log-likelihood is therefore $(2k - \text{AIC})/2 = (18 + 10440.245)/2 = 5229.123$.
It is the best cell the documented search found, not a proven global optimum.

The search found seven other cells within 2 of it, all with a drift: ARIMA(2, 1, 4) (ΔAIC = 0.036),
(4, 1, 3) (0.128), (4, 1, 2) (0.400), (2, 1, 5) (0.593), (3, 1, 5) (0.629), (5, 1, 2) (1.567) and
(5, 1, 3) (1.859). That list is a lower bound: a harder search can only find more. The rule of thumb
reads ΔAIC ≤ 2 as "about equally supported", and a gap of a few hundredths, like the 0.036 between
the first two, carries no meaning at all. So AIC does not single out one order here: at least eight
models with 8 to 10 parameters are about equally supported, and the rule picks the lowest.

BIC for the chosen cell is $-2 \log L + k \ln n = -10458.245 + 9 \times 7.6187 = -10389.68$. ARIMA(2, 1,
2) without a drift ($k = 5$, AIC −10433.809) has BIC $-10443.809 + 5 \times 7.6187 = -10405.72$, lower.
So BIC would choose the smaller model. The artifact records it as `bic_choice`.

## What the landscape shows on AAPL

**At d = 0** (36 cells, trend 'c'): every cell with an AR part converges to an inverse AR root between
0.99966 and 0.99985. All 30 are `near_unit_root`. The model is trying to put a root at 1, which is the
unit root the tests found. The six MA-only cells cannot do that; their AIC falls from +4241 for (0, 0,
0) to −5098 for (0, 0, 5), a cliff of thousands of points above the AR cells. The d = 0 surface is a
picture of why the log price needs differencing.

**At d = 2** (36 cells, trend 'n'): 30 cells are `near_unit_root` and 6 `ok`, the 30 every one through an MA root
above 0.99 (one also has an AR root that close). Differencing a series that was already stationary
creates an MA root at 1 (background §3), and the fits find it. That is the over-differencing
signature again.

**At d = 1** (72 cells): 67 are `ok`, 2 `near_unit_root` and 3 `not_converged`. The two near unit
root cells, (3, 1, 3) and (5, 1, 3) without a drift, have an AR and an MA root both above 0.997: two
roots cancelling on the unit circle. The three that did not converge, (0, 1, 2) without a drift and
(4, 1, 4) and (5, 1, 4) with one, kept the highest likelihood they found at a point where the line
search stopped. ARIMA(4, 1, 4) with a drift would sit 1.806 above the chosen cell if it counted. The
rule excludes them: "converged" is what the optimiser reported, and the grid does not second-guess
it. No cell's log-likelihood equals that of a model it nests. The second re-review's own wider
search found a converged run for ARIMA(4, 1, 4) with a drift at +1.139, so a fuller search would
add it to the near ties: one more reason the list is a lower bound.

**The simple models sit close together, and the larger ones far below them.** (0, 1, 1) with a drift
is −10398.937, (1, 1, 0) with a drift −10398.718, (0, 1, 0) with a drift −10387.463. 28 of the 67 `ok`
cells sit more than 30 points below (0, 1, 1) with a drift, and the chosen cell 41.31 below it. 16 cells,
the chosen one included, are within 4 of it. (Before the fix rounds the grid showed nine cells 33 to 40 points
below and a flat surface between them; most of that flatness was optimiser stops, not the data.)

**Why those cells are so much lower.** Their AR and MA polynomials share a pair of complex roots that
almost cancel. For the chosen ARIMA(3, 1, 4) with a drift, two inverse AR roots have modulus 0.932 at
angles of ±154.7° (the third is real, −0.465), and two of the inverse MA roots modulus 0.885 at
±152.1° (the other two are real, −0.683 and 0.155). A root at about 154° is a cycle of
360 / 154 = 2.3 trading days: up, down, up. The model has found a short alternating pattern. ARIMA(2, 1, 2) with a drift has the same
structure at ±158.9° (AR) and ±160.3° (MA).

**Where the gain comes from.** statsmodels gives each day's contribution to the log-likelihood
(`llf_obs`). At the parameters the grid recorded, the chosen model's log-likelihood is 26.65 above
that of ARIMA(0, 1, 1) with a drift. Split by date:

| Days | Count | Share of the days | Gain | Share of the gain |
|---|---|---|---|---|
| 2015-01-05 to 2019-12-31 | 1,257 | 62% | 9.53 | about a third (35.8%) |
| 2020-01-02 to 2023-02-03 | 779 | 38% | 17.12 | about two thirds (64.2%) |
| of which 2020-02-15 to 2020-05-31 | 72 | 3.5% | 20.59 | about three quarters (77.2%) |

The third digit is not robust: other optima within 0.002 of log-likelihood move these shares by about
half a point.

So about three quarters of the gain comes from 72 trading days around the March 2020 crash, and the
rest of 2020 onwards gives a little back (−3.47). The five days that contribute most are all in March
and April 2020. The neighbours tell the same story: for (4, 1, 3) with a drift the 72 days give about
four fifths of its gain, for (2, 1, 2) with a drift about 85%. The Gaussian likelihood scores every
day as if the variance were constant, so a few huge days weigh heavily.

## Over-fitting, stated plainly

Two reasons to doubt that a 9-parameter model with cancelling roots will forecast better than
ARIMA(0, 1, 1):

1. **AIC's penalty is not reliable here.** When an AR and an MA root nearly cancel, the four
   coefficients that carry them are poorly identified: many different values give almost the same
   likelihood. AIC's 2 per parameter is derived for well-identified parameters inside their space, the
   same condition that a unit root breaks at d (above). With near-cancelling roots the penalty
   undercounts what the extra parameters buy in fitting noise, and AIC is known to over-select.
2. **The gain is concentrated.** About three quarters of it comes from 3.5% of the training days. A pattern
   that strong in one volatile spring, and weak elsewhere, may not generalise to the test period.

Neither reason changes the rule: ADR-0002 §6 fixed it in milestone 0, before any data was seen, and a
rule changed after seeing the result would be tuned to it. The arbiter is out of sample: milestone 4
compares the chosen model's walk-forward forecasts with a random walk and with the course's model on
the test segment. Milestone 3 checks the residuals first.

## The cross-check: pmdarima's stepwise search

pmdarima's `auto_arima` ran twice on the same training rows.

| Run | pmdarima chose | Its AIC | Converged? | Our cell of the same model | Gap |
|---|---|---|---|---|---|
| course (`test='adf'`, start (1, 1)) | ARIMA(0, 1, 1) with an intercept | −10398.937 | yes, 2 iterations | (0, 1, 1) with a drift: −10398.937 | +0.0003 |
| defaults | ARIMA(2, 1, 2) without an intercept | −10426.231 | **no, 50 iterations** | (2, 1, 2) without a drift: −10433.809 | +7.578 |

Both agree on d = 1. Neither picks (3, 1, 4). Three reasons, each measured:

1. **The stepwise search is local.** It starts at one order and moves to neighbours while the AIC
   improves. The course's run started at (1, 1, 1) and stopped at (0, 1, 1) after keeping 8 fits. The
   default run, starting at (2, 1, 2), kept 22.
2. **pmdarima stops each fit after 50 iterations** and, with `suppress_warnings=True` (its default and
   the course's setting), does not say so. Its (2, 1, 2) fit stopped at iteration 50 without
   converging. statsmodels with `maxiter=50` reproduces its AIC exactly (−10426.230863341112, bit for
   bit); with `maxiter=200` the same fit, from the same default start, converges at iteration 62, 7.562
   points lower. The grid's cell is 0.016 lower still (−10433.809), from one of its random starts. So
   7.562 of the 7.578 is the iteration limit.
3. **Its intercept is not our drift,** but for the same order and d it is the same model. In SARIMAX
   the intercept $c$ enters the differenced equation, so the drift is $c / (1 - \phi_1 - \dots)$; for
   (0, 1, 1) that is $c$ itself, which is why the first row's gap is only +0.0003.

ADR-0002 §7 expected a gap within ±1 for the same model. That holds only when both fits reach the
same optimum, and converging is not enough. The second row is outside it because pmdarima's fit
stopped early (`converged: false`, `iterations: 50`). But pmdarima's default run also fitted (2, 1, 2)
with an intercept, the same model as our (2, 1, 2) with a drift (its implied drift, $c/(1 - \phi_1 -
\phi_2)$ = 0.0008984, against our 0.0008982): that fit converged, in 41 iterations, at AIC −10402.059,
34.806 above our −10436.865. Two converged fits of one model, at two optima.

## Assumptions

- Gaussian innovations with a constant variance. Returns have fat tails and volatility clustering, so
  the likelihood, and the AIC built on it, is an approximation.
- Each cell's kept fit is the best of its starts, not a proven global maximum. With near-cancelling
  roots the likelihood has several local maxima, and a cell's AIC is only as good as the optimum
  found. The nesting rule guarantees that nested cells are consistent, not that either is optimal.
- AIC differences under about 2 are noise, not a ranking.

## Where it breaks

- **Across d.** Never. The app draws one d at a time, each on its own AIC scale, and labels the best
  cell of each d "display only".
- **Multimodal likelihoods.** Two optimisers, or two starting points, can stop at different optima of
  the same cell, as pmdarima's (2, 1, 2) shows. The grid's answer depends on how hard it searches.
  Measured on the training split: with L-BFGS from the default, padded and 2, 6, 12 or 24 random
  starts per cell (the first fix round), the choice was ARIMA(2, 1, 4) with a drift every time, and the
  cells found within 2 of it were 3, 5, 4 and 6. A second review then ran Nelder-Mead from other
  cells' estimates and found ARIMA(3, 1, 4) with a drift 0.037 lower; the polish stage now does that,
  and it is the choice. So the stability across random starts held only for that L-BFGS search. The
  choice is the best this documented search found, a gap of a few hundredths of AIC means nothing, and
  the near-tie list is a lower bound. No setting of the search made the near ties go away, which is
  the point of "Over-fitting" above.
- **Volatility.** A constant-variance likelihood lets a short volatile stretch decide the order. A
  GARCH-type variance model is the usual fix; it is outside this project.

## In this project

- `src/arima_forecasting/selection.py`: `fit_cell` and `fit_grid` fit each cell from its starts
  (`padded_start`, `random_starts`), keep one run (`choose`, `polish_start`) and set its status;
  `nesting_violations` finds a cell below a model it nests; `refit_cell` reproduces a committed cell
  from its recorded start.
- `add_delta_aic` measures each delta from the best eligible cell of the same d, and `select` makes the
  choice, the near ties, BIC's choice and the counts. `pmdarima_check` runs pmdarima twice and compares
  its choice with the grid.
- `src/arima_forecasting/payloads.py` re-checks each delta, the selection, the start labels, the
  nesting rule and the cross-check when the file is read; the app's reader does the same
  (`app/src/lib/contract.order.ts`).
- The app's AIC landscape page draws one d at a time (`app/src/views/AicLandscapeScene.tsx`) and a
  table of every cell.
