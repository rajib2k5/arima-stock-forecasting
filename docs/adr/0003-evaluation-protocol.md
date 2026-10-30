# ADR-0003: How forecasts are made and scored: windows, walk-forward without refit, the random-walk baseline, Diebold–Mariano

**Status:** Accepted (milestone 4); the owner's defaults, each recorded in LEARNING_LOG ("Decisions
and defaults") and open to override.
**Date:** 2026-10-29
**Deciders:** the learner, with the milestone-4 session

---

## Context

Course modules 9 and 10 make one forecast and print three numbers. Fitted on the first 90% of
2015–2023, the model forecasts the last 10% in one shot (`get_forecast(steps=len(test_data))`),
exponentiates it, and reports RMSE, MAE and MAPE in dollars. Four things are missing or wrong
(PR/FAQ, the four mistakes):

1. A single static path from one origin says how far the model's long-run drift carries it, not how
   well it forecasts. For an ARIMA of the log price it is soon a straight line.
2. There is no baseline. "RMSE $10" means nothing without the error of a forecast that knows nothing.
3. exp(μ) is the median of the forecast price, not its mean.
4. The test period is the only one, and the order was chosen with it in view (ADR-0002 fixes that
   part; the out-of-sample window 2024-01-02 to 2026-09-30 was never seen by any step).

The course's code also no longer runs as written on the pinned libraries: its forecast step stops on
a trading-day date index (module 9 raises "No supported index is available"), so its MAPE line is
never reached as written; given forecasts, that line prints NaN (milestone-4 walkthrough, "Pitfalls
met", reproduces each on made-up data).

## Decision

### 1. Two windows, scored separately

**test** (the course's: 2023-02-06 to 2023-12-29, 227 days) and **oos** (2024-01-02 to
2026-09-30, 689 days). Both are scored with the parameters estimated on the training split only.
Every metric is reported per window; the windows are never pooled, because their price levels and
volatilities differ (concept note 10).

### 2. Three forecast methods

- **Static multi-step** (the course's way, kept so its result can be shown): one path from the last
  training day across the test window; for oos, one path from the last test day with the Kalman state
  filtered through the test window at the training parameters.
- **Walk-forward one-step, no refit** (the primary score): each day forecast from every observation
  before it, the parameters fixed at the training estimates, only the state updated. Done as one
  filter pass over the whole series, which equals the explicit `append(refit=False)` loop to 8.9e-16
  in the mean on the real series (tests check it on simulated data).
- **Walk-forward one-step, refit every 21 trading days** (a robustness check, the AIC model only):
  the parameters re-estimated on an expanding window before each block, each refit starting from the
  previous estimates.

### 3. The random walk is the baseline under every metric

Tomorrow's log price is today's: one step ahead the previous day's value; static, the origin's value
on every day. Every model metric is divided by the random walk's on the same days, kind and window.

### 4. Metrics in log points and in dollars, on the median and on the mean

RMSE and MAE in log points (comparable across windows), and RMSE, MAE and MAPE in dollars on both
exp(μ) (the course's, the headline) and exp(μ + s²/2). RMSE is minimised in expectation by the mean,
MAE by the median (concept note 11).

### 5. Diebold–Mariano against the random walk, with the Harvey–Leybourne–Newbold correction

For each one-step forecast and window, on squared and on absolute log errors, two-sided at 5%, the
loss differential's mean over √(γ̂₀/n), scaled by √((n − 1)/n) and compared with t(n − 1) (Diebold
and Mariano 1995; Harvey, Leybourne and Newbold 1997; concept note 10). The verdict is
`beats_rw`, `no_difference` or `worse_than_rw`; a forecast within 1e-9 log points of the random
walk's on every day is `same_as_rw` and not tested. Static paths are not tested (one path, errors
that share their origin).

### 6. Intervals: normal primary, a variance-matched Student-t beside it, coverage measured

Normal intervals (statsmodels' and the course's) at 80% and 95%, and the Student-t with the
milestone-3 residual fit's degrees of freedom, scaled to the model's forecast variance. The coverage
of each is counted per window; one-step coverage is tested with Kupiec's LR, static coverage shown.

### 7. Volatility clustering is reported, not modelled

No GARCH layer (project 1's ground). Its effect on the intervals is measured instead.

## Options considered

| Option | Rejected because | What would make it win |
|---|---|---|
| Static path only (the course) | It scores the drift, not the forecasting: the AIC model's static path is within $0.72 of a random walk with the same drift over the test window (milestone-4 walkthrough; every dollar figure in this ADR is a dividend-adjusted close, `prices.json`'s `price_basis` `adjusted_close`) | A question that is genuinely about one horizon from one date, such as a budget for a fixed date |
| Walk-forward with a refit every day | 916 refits of a 9-parameter model; the refit every 21 days, a twentieth of that, changes the RMSE ratio by less than 0.004 on either window | A long window in which the parameters visibly drift; a measured gain from refitting more often |
| Refit every 21 days as the primary method | It mixes two questions (the model, and how it is re-estimated) and costs 12 s to 28 s against 0.03 s for one filter pass (two measurements on a loaded machine) | Parameter estimates that change materially across the windows; they do not here (the last refit's estimates are within 0.08 of the training ones for every coefficient) |
| A random walk with drift as the baseline | The plain random walk is the textbook baseline and the course's implicit one; the drift is a parameter estimated like any other | Comparing static paths fairly: the walkthrough uses it as a probe for exactly that |
| DM without the HLN correction (DM against N(0, 1)) | HLN is the standard small-sample version; at h = 1 it is the one-sample t-test, which scipy checks independently | n in the thousands, where the two agree |
| DM with a Newey–West variance | At h = 1 the theory needs only γ̂₀, and it is what the owner's default names; under a sign-flip null the γ̂₀ test rejects at 5% in 4.0% to 5.7% of draws, so it is correctly sized here. On oos squared loss a Newey–West variance moves the BIC, AIC and AIC-refit verdicts across 5% with the lag count (6 or 9); it is reported in the walkthrough, not exported | Autocorrelation in the loss differential that a robust test confirms: not found (Revisit when, below) |
| DM on dollar errors | Dollar errors scale with a price that moved between $142.98 and $341.07 over the two windows, so the size of a dollar error moves with the price level as well as with the forecast's quality | A question about dollar losses specifically |
| GARCH intervals | Outside the course, and project 1's subject | Intervals that must be right in calm and stormy periods alike |
| The t intervals as primary | The course and statsmodels use the normal; the t is reported beside it and the coverage decides | Coverage evidence across more windows than these two |

## Consequences

- The page and the notebook show every method against the random walk; the course's static path is
  there, labelled, with its drift explained.
- Seven forecast files of about 0.65 MB each, one per model and method, under the 1 MB budget.
- The export takes 12 s to 28 s longer for the refit (two measurements on a loaded machine).
- The verdicts are Python's; the app keys text by them (ADR-0001).
- Timings are not in any JSON file: the contract keeps wall-clock values out of `data`, so that
  `--check` and byte-identical re-exports hold. They are in the walkthrough.

## Measured in milestone 4 (2026-10-29)

All from the committed files with the command in the milestone-4 walkthrough, "The commands behind
the table".

- One-step, every model is slightly worse than the random walk in RMSE on both windows (dollar ratios
  1.0056 to 1.0174). DM finds no difference in the test window; in the oos window all four one-step
  forecasts are worse than the random walk on absolute loss (p 0.0002 to 0.024), robustly (Newey–West
  at 6 and 9 lags and a block bootstrap agree), and on squared loss only BIC's (p 0.048). Every
  squared-loss verdict is borderline: five days carry 60% to 74% of the squared deviations of the loss
  differential, and its verdict moves with the variance estimator.
- The AIC model's static path beats the flat random walk (RMSE ratio 0.413 on test, 0.537 on oos),
  and a random walk with its drift scores RMSE $10.34 and $34.31 against its $10.63 and $34.26: the
  advantage is the drift.
- The normal one-step intervals are too wide in the test window (80%: 217 of 227 inside, for the AIC
  model), because 2023 was calm (errors 0.66 times the stated sd); in oos the 80% normal interval
  still covers 0.869 with the scale about right, and the variance-matched t covers 0.810.

## Revisit when

- the owner overrides a default in LEARNING_LOG;
- a model with materially time-varying parameters is added (then the refit becomes the primary
  method);
- volatility is modelled (then the intervals and the coverage tests change);
- the loss differential shows autocorrelation that a robust test confirms (then report a Newey–West
  DM, or move to h > 1 with its lags). **Not met** (re-examined in the third review pass, milestone-4
  walkthrough, DM assumptions). A White (HC0) joint test of five lags gave p 0.0008 and 0.0056 for the
  oos squared loss of BIC's and the course model, but under a sign-flip null with no autocorrelation
  that test rejects in 38% and 49% of draws, and its calibrated p-values are 0.15 and 0.34: the
  earlier reading of it as confirmation is withdrawn. The squared-loss verdicts depend on the variance
  all the same, and not only BIC's: with Newey–West at 9 lags the AIC model's (p 0.023) and the AIC
  refit's (0.039) reject as well, against 0.080 and 0.109 with γ̂₀. So γ̂₀ stays the exported variance
  and the robustness checks are reported beside it (LEARNING_LOG, overridable).
