# Milestone 4: forecast and evaluation

Status: built, reviewed, and revised in a fix round. Reviewed by: one adversarial review (statistics,
code, contract, app and docs, 2026-10-30) and the coordinator's checks in a real browser. What it
found wrong, and what changed, is in [Review fix round](#review-fix-round).

This walkthrough covers course modules 9 and 10: forecast the test period, then score the forecast.
It adds what the course leaves out: a walk-forward one-step forecast beside the course's static one,
the frozen out-of-sample window, a random walk under every metric, a Diebold–Mariano test against it,
the dollar mean beside the course's median, and the coverage of the intervals. It explains what
exists, why it is built this way, and where each guard lives.

How to use it:

1. Read the sections up to "Pitfalls met".
2. Answer [Predict before you look](#predict-before-you-look) on paper.
3. Only then read [Measured results](#measured-results).
4. Read the two concept notes listed at the end.
5. Answer [Explain it back](#explain-it-back) without notes.

Every `file:line` reference is relative to the repository root and was checked by a script against
the files as they stand. Every number was measured on 2026-10-29 from the committed files in
`app/public/data/`, with the scripts in [The commands behind the table](#the-commands-behind-the-table),
unless the row says otherwise.

---

## What we built and why

Eight new artifacts carry milestone 4 to the app under schema `1.5.0`. **Seven forecast files**,
`forecast_<model>_<method>`, hold one forecast path per model and method on two windows. **`evaluation`**
scores every one of them against the random walk.

**What is forecast.** The three models of milestone 3, with the parameters estimated on the 2,037
training rows (`fit.json`): **aic**, ARIMA(3, 1, 4) with a drift, the primary model; **bic**,
ARIMA(2, 1, 2) without a drift; **course**, ARIMA(0, 1, 1) without a drift. The two windows are
**test**, 2023-02-06 to 2023-12-29 (227 days, forecast from 2023-02-03, the last training day), and
**oos**, 2024-01-02 to 2026-09-30 (689 days, forecast from 2023-12-29, the last test day).

**Three methods.**

- **Static multi-step**, the course's `get_forecast(steps)`: one path from one origin. For oos the
  origin is the last test day, with the model's state filtered through the test rows at the
  training parameters (no refit).
- **Walk-forward one-step**: the forecast of each day uses every observation before it and nothing
  after, at the training parameters. It is one filter pass over the series, tested equal to the
  explicit loop that appends one day at a time.
- **Expanding refit** (aic only, the robustness check): walk-forward, with the parameters estimated
  again every 21 trading days on every observation before the block. 43 refits.

Each forecast row holds the actual price, the model's mean and standard deviation of the log price
(`mean_log`, `sd_log`), the dollar **median** exp(μ) (what the course calls the forecast), the
dollar **mean** exp(μ + s²/2), and the 80% and 95% bounds of a normal interval and of a Student-t
interval scaled to the same variance.

**`evaluation`** holds the random walk on each window (static: the origin's price every day; one
step: yesterday's price), each forecast's RMSE, MAE and MAPE in log points and dollars with its ratio
to the random walk's, a Diebold–Mariano test with the Harvey–Leybourne–Newbold correction for each
one-step forecast, window and loss, and the coverage of every interval with Kupiec's test for the
one-step forecasts. Each test carries a verdict, and the app keys fixed text by it.

The app has a new lazily loaded page, **Forecast and evaluation**: model, method and window
pickers; a fan chart of the median and the bands (the mean, the t bands and a log price axis on
request); a walk-forward animation that starts paused and has no timer under reduced motion; the
metrics beside the random walk; the DM result; the coverage table. It fetches `evaluation.json`
and then only the forecast file on show. Notebook 04 prints the same numbers from the committed
files and rebuilds them once to check they match.

**The answer on AAPL.** Every dollar figure in this milestone is a dividend-adjusted close
(`prices.json`'s `price_basis` `adjusted_close`); the log errors and every DM test do not depend on it.

- **Static.** The AIC model's static path beats the flat random walk on both windows: dollar RMSE
  ratio 0.413 (test) and 0.537 (oos). That is its drift. A random walk that carries the AIC model's
  drift (0.000902 log points a day) scores RMSE $10.339 against the AIC model's $10.632 (test) and
  $34.309 against $34.256 (oos), and the two paths are never more than $0.718 (test) and $0.276 (oos)
  apart. The BIC and course models have no drift, and their static paths score as the flat random
  walk does: ratios 0.999 to 1.011.
- **Walk-forward one step.** Every model is slightly worse than yesterday's price on dollar RMSE,
  log RMSE and dollar MAE: dollar RMSE ratios 1.006 to 1.017, log RMSE ratios 1.005 to 1.018.
  Diebold–Mariano finds no difference in the test window. In the oos window all four one-step forecasts are "worse than the
  random walk" on absolute loss (p 0.0002 to 0.024), and on squared loss only BIC's (p 0.048). The
  absolute-loss verdicts hold under every variance tried; the squared-loss ones are borderline, as five
  days carry 60% to 74% of the squared deviations of the loss differential ([DM
  assumptions](#dm-assumptions)). The refit changes little: AIC's ratios are 1.0122 (test) and 1.0137 (oos) with refits, 1.0118 and
  1.0174 without.
- **Intervals.** In the test window every one-step interval is too wide. A probe shows it is the
  scale: the errors were 0.66 times the stated standard deviation, 2023's daily returns varied less
  (sd 0.0122) than the training years' (0.0189), and rescaled to the realised scale the normal
  intervals cover close to their levels. In the oos window the scale is about right (0.95),
  the standardised errors have a kurtosis of 10.7 (6.8 once a trailing average takes out part of the
  clustering), the normal 80% interval is still too wide (0.869 inside),
  and the variance-matched t's 80% interval is consistent (0.810). At 95% both are consistent in oos.
- **Median and mean.** One step ahead the mean is 0.0172% (aic) to 0.0177% (course) above the median. At the end of a static
  path it is 3.32% to 3.80% (test) and 10.42% to 11.98% (oos) above. Neither scores better on every
  path.

**Two deviations from the brief.**

- **No timings in `evaluation.json`.** The brief asked for the walk-forward and refit times in the
  file. The contract keeps wall-clock values out of `data` (`docs/architecture/contract.md` §2,
  "Determinism"): a time differs on every run, so `--check` could never pass and no re-export would
  be byte-identical. The times are measured here instead ([Timings](#timings)).
- **One file per (model, method), not per model.** A model's static and walk-forward files with the
  t bands are 1,307,484 bytes for aic (652,916 + 654,568), past the 1 MB budget. Each file alone is
  652,916 to 700,824 bytes.

---

## Why this design

| Choice | Alternatives | Why this one | What it costs |
|---|---|---|---|
| **Forecast all three models** (owner's default, LEARNING_LOG; `forecasting.py` module docstring) | The AIC choice only | Tests whether the AIC model's extra parameters pay off out of sample, against BIC's rival and the course's model | Seven files and a model picker |
| **Two windows**: test, and the frozen oos window | The test window only (the course) | 227 days of one calm year; 689 more days, used for no choice and no fit, test the same forecasts again | The oos static path is not the course's: it starts from the last test day |
| **Walk-forward as one filter pass** at the training parameters, reading the one-step predictions | The explicit loop, `append(refit=False)` per day; an `extend()` loop | The pass equals the append loop (to 8.88e-16 on AAPL's 916 days) and takes 0.026 to 0.027 s against 5.52 to 8.08 s; `extend()` breaks with a drift (Pitfalls) | It relies on statsmodels' one-step predictions; `tests/test_forecasting.py:77` pins the equality and `:113` the absence of look-ahead |
| **The static oos path starts from the last test day**, the state filtered through the test rows at the training parameters | A 916-day path from the last training day; a refit on train and test | The path starts where the series was, and the parameters stay the training ones, as for every other forecast | One more filter over the test rows |
| **An expanding refit every 21 trading days**, AIC only, each starting from the previous block's estimates | Every day; a rolling window; a fresh start each time; all three models | A robustness check of "fixed parameters", at about a month's cadence; 43 refits | 12.21 s and 27.81 s in two runs under load; a warm start tracks one local maximum (open decision) |
| **The random walk under every metric**, static (flat at the origin) and one step (yesterday) | No baseline (the course); a random walk with a drift | A score means nothing alone, and the random walk needs no estimate | A flat line rewards any drift in a rising market; the drift baseline is measured as a probe, not exported |
| **The median exp(μ) is the headline dollar point**, the mean beside it (`headline_usd`) | The mean only | The median is what the course reports, and it minimises expected absolute error; the mean minimises expected squared error (concept note 11) | Two sets of dollar metrics |
| **Metrics in log points and dollars, each with its ratio to the random walk** | Dollars only (the course) | Dollar errors scale with the price level; ratios compare across windows | Three blocks per row |
| **Diebold–Mariano with the HLN correction**, h = 1, on log errors, squared and absolute loss, two-sided | Dollar errors; a Newey–West variance; no test | At h = 1 it is the one-sample t test of the loss differential (`tests/test_evaluation.py:107`). `evaluation.py`'s docstring gives the reason for log errors: dollar errors scale with a price that changes a lot over oos (not measured here) | γ₀ alone assumes no autocorrelation in the differential; in oos that is neither confirmed nor ruled out, and the squared-loss verdicts move with the variance ([DM assumptions](#dm-assumptions)) |
| **DM on the one-step forecasts only** | DM on the static paths | A static path's errors share one origin, so its differential is autocorrelated up to lag h − 1 | The static paths have no test |
| **`same_as_rw` when every one-step forecast is within 1e-9 log points of the random walk's** | Let DM run; raise | An ARIMA(0, 1, 0) without a drift is the random walk: DM would compute a statistic from rounding noise | One more closed-enum value; the tolerance is a pinned choice (open decision) |
| **Variance-matched Student-t intervals beside the normal** | The normal only (statsmodels', the course's); a t with scale 1 | The training residuals have fat tails (milestone 3); matching the variance keeps the model's s and changes only the shape | At 80% and 95% the t's multipliers are below the normal's (1.019 and 1.914 against 1.282 and 1.960 for aic) |
| **Kupiec's test on one-step forecasts; static coverage "not tested"** | Test the static paths too | A static path's days share one accumulated error, so they are not independent | The static coverage is shown without a test |
| **One file per (model, method)** | One file per model (the brief); a columnar layout (a major bump) | Within the 1 MB budget; the page shows one at a time | Seven forecast files instead of three |
| **No timings in the data** | Timings in `evaluation.json` (the brief) | Contract §2 "Determinism"; `--check` compares `data` exactly | The times live in this walkthrough only |
| **The app recomputes nothing**: verdicts, counts, ratios and bounds come from Python; text is keyed by verdict | The app compares p with alpha or a rate with its level | ADR-0001; app mutants show what drifts otherwise | Every new reading needs a verdict field |
| **Every count bounded before it is used**: a window's `n` ≤ `MAX_ROWS` = 10,000 before any row is read | Read whatever the file says | A stated 2³² must give one short error, not a loop (milestone 3's lesson) | A window of more than 10,000 days is refused (open decision) |
| **Linear price axis by default**, log on request | Log by default | The course draws dollars on a linear axis | The AIC model's 95% static band on its last oos day spans $147.91 to $847.18, a factor of 5.7, so on a linear axis the band dwarfs the price |
| **The animation starts paused and has no timer under reduced motion** | Autoplay | Motion the reader did not ask for | One more click |

---

## Map of what changed

| Path | What | Hand-written or generated |
|---|---|---|
| `src/arima_forecasting/forecasting.py` | Static, walk-forward and refit forecasts, the random walk, the dollar values and both intervals, `forecast_payload` | Hand-written (new) |
| `src/arima_forecasting/evaluation.py` | Metrics, Diebold–Mariano with HLN, Kupiec coverage, the verdicts, `evaluation_payload` | Hand-written (new) |
| `src/arima_forecasting/payloads.py` | `validate_forecast`, `validate_evaluation`, `validate_forecast_fit`, `validate_forecast_evaluation`; the t tail and Cornish–Fisher quantile without scipy | Hand-written (changed) |
| `src/arima_forecasting/export.py`, `contract.py` | `forecast_evaluation_payloads`; the eight artifacts; milestone 4 current; schema `1.5.0` | Hand-written (changed) |
| `tools/export_app_data.py` | The cross-file family grows to the forecasts and `evaluation`, checked before and after writing | Hand-written (changed) |
| `tools/build_notebooks.py` → `notebooks/04_forecast_and_evaluation.ipynb` | The milestone-4 notebook (and one sentence of notebook 03) | **Generated** notebook |
| `app/public/data/forecast_*.json`, `evaluation.json` | The eight new artifacts | **Generated**, committed |
| `app/public/data/{meta,prices,eda,stationarity,acf_pacf,aic_grid,fit,residuals_*}.json` | Re-exported: new envelopes (`schema_version` 1.5.0); `meta` lists 18 artifacts | **Generated**, committed |
| `app/src/lib/contract.forecast.ts` | `parseForecast`, `parseEvaluation` | Hand-written (new) |
| `app/src/lib/contract.reader.ts` | `shown`: every error message quotes a value in a bounded length | Hand-written (changed) |
| `app/src/lib/forecastText.ts`, `app/src/views/ForecastView.tsx`, `app/src/data/useForecastData.ts` | Fixed text per verdict and the animation's pace, the page, loading and parsing | Hand-written (new) |
| `app/src/lib/plot.ts` | `logTicks`, `formatLogTick` for the log price axis | Hand-written (changed) |
| `app/src/App.tsx`, `app/src/lib/gate.ts`, `app/src/index.css` | The page offered when `meta` lists its eight files, through `lazy()`; its styles | Hand-written (changed) |
| `app/src/test/fixtures/{forecast_*,evaluation}.data.json`, `payload_cases.json`, `payloads.ts` | Made-up bases (the production code on a simulated series), the new corpus cases, and their registration | Generated bases and cases; `payloads.ts` hand-written |
| `tests/test_{forecasting,evaluation,payloads_forecast}.py` | New suites | Hand-written (new) |
| `tests/test_committed_artifacts.py`, `test_export.py`, `test_notebooks.py`, `test_payload_corpus.py`, `test_contract.py` | The milestone-4 files rebuilt and cross-checked; notebook 04; schema 1.5.0 | Hand-written (changed) |
| `app/src/**/*.test.ts(x)` | `contract.forecast`, `contract.reader`, `forecastText`, `useForecastData`, `ForecastView` (new); `App`, `gate`, `plot`, the corpus and real-data tests (changed) | Hand-written |
| `docs/concepts/10-11`, `contract.md` §3.9 and §3.10, this file | Concept notes, the shipped contract | Hand-written |

---

## Code walkthrough

Read in this order. Each step names one file and line.

1. `src/arima_forecasting/export.py:186` is `forecast_evaluation_payloads`. It builds the seven
   forecast payloads from the fit and the residual files, then `evaluation` from those payloads.
   `build_payloads` (`:208`) runs it after the milestone-3 fit (`:221`).
2. `src/arima_forecasting/forecasting.py:329` is `forecast_payloads`. For each (model, method) in
   `FORECASTS` (`:81`) it reads the model's t fit from `residuals_<id>` and calls `forecast_payload`
   (`:265`), which refuses a refit of any model but aic (`:268`).
3. `src/arima_forecasting/forecasting.py:111` is `spec_from_fit`: the parameter vector from
   `fit.json`'s doubles, refused unless its names are statsmodels' for that order and trend (`:118`).
   `Spec.model` (`:106`) builds every model on a plain numpy array, which avoids the course's
   module-9 failure (Pitfalls).
4. `src/arima_forecasting/forecasting.py:211` is `windows`: the test and oos rows as positions in the
   price table. A window's origin is the row before it.
5. `src/arima_forecasting/forecasting.py:134` is `static_forecast`: filter `y[:origin]` at fixed
   parameters (`:137`), then `get_forecast(steps)` (`:138`). For oos the origin is the last test day,
   so the state has seen the test rows. `tests/test_forecasting.py:166` checks it equals the course's
   `get_forecast` and statsmodels' `append(refit=False)` route.
6. `src/arima_forecasting/forecasting.py:142` is `walk_forward`: one filter pass over `y[:stop]` and
   its one-step predictions (`:146`). `walk_forward_loop` (`:150`) is the reference loop, which
   appends one observation at a time (`:160`). `tests/test_forecasting.py:77` checks the two agree,
   and `:113` that a jump on day t moves no forecast of day t or earlier.
7. `src/arima_forecasting/forecasting.py:164` is `refit_walk_forward`. In blocks of `REFIT_EVERY` =
   21 rows (`:176`), it refits on `y[:block]` starting from the previous block's estimates (`:181`),
   records each refit, and forecasts the block with `walk_forward` (`:195`).
   `tests/test_forecasting.py:127` checks that a change on day t reaches no forecast of day t or
   earlier and no refit fitted before it, and `:143` the schedule.
8. `src/arima_forecasting/forecasting.py:123` is `t_multipliers`: the t quantile at (1 + level) / 2
   times √((ν − 2)/ν), the scale that gives the t the variance 1; ν ≤ 2 is refused (`:127`).
   `tests/test_forecasting.py:216` checks the variance, the quantiles, and that the t is narrower
   than the normal at 80% and 95% and wider at 99.9%.
9. `src/arima_forecasting/forecasting.py:227` is `forecast_rows`: every dollar value from the
   exported `mean_log` and `sd_log`, the mean as exp(μ + s²/2) (`:247`); a variance that is not
   positive is refused (`:232`). `tests/test_forecasting.py:190` works one row by hand, and `:205`
   draws a million log-normal prices to show which is the mean and which the median.
10. `src/arima_forecasting/evaluation.py:241` is `evaluation_payload`. The random walk's forecasts
    (`:217`) are scored first; then, per forecast file and window, the metrics (`:207`), the ratios
    to the random walk (`:233`), and the mean-over-median gap (`:263`). For a one-step forecast it
    measures the largest distance from the random walk's forecast (`:277`) and runs `dm_test` per
    loss (`:279`); every forecast gets its coverage rows (`:283`).
11. `src/arima_forecasting/evaluation.py:142` is `dm_test`: the differential d, its variance γ₀ with
    divisor n (`:159`), `same_as_rw` when the forecasts are within `SAME_TOLERANCE` of the random
    walk's (`:161`), the HLN factor, and the p-value from a t on n − 1 degrees of freedom (`:167`).
    `dm_verdict` (`:134`) reads p and the sign of the mean. `tests/test_evaluation.py:83` works DM by
    hand, `:107` checks it against scipy's `ttest_1samp`, and `:135` the `same_as_rw` boundary.
12. `src/arima_forecasting/evaluation.py:195` is `coverage`: a bound counts as inside (`:198`);
    `kupiec` (`:171`) clamps its LR at 0 (`:183`); `coverage_verdict` (`:187`).
    `tests/test_evaluation.py:157` works Kupiec by hand and `:177` puts actuals on the bounds.
13. `src/arima_forecasting/payloads.py:2603` is `validate_forecast` and `:2821`
    `validate_evaluation`. Both readers check shapes, pins and bookkeeping; Python alone also
    recomputes every dollar value (`:2434`), refuses a static `sd_log` that falls (`:2444`), checks
    each t quantile by the t's CDF or, from `T_ASYMPTOTIC_DF` on, by the Cornish–Fisher expansion
    (`:2525`), every DM row (`:2698`), every coverage row (`:2754`) and each ratio as the same
    division (`:2944`). `validate_forecast_fit` (`:3010`) and `validate_forecast_evaluation`
    (`:3126`) check the files against each other.
14. `tools/export_app_data.py:207` is `FAMILY`: fit, residuals, forecasts and evaluation, which
    `_family_problems` (`:213`) checks against each other and against `prices.json` (`CHECKED`, added
    in the review fix round) before writing (`:175`) and on the files read back after (`:196`).
15. `tests/test_committed_artifacts.py:282` rebuilds the static and walk-forward files from the
    committed `prices.json`, `fit.json` and residual files and compares them exactly; `:295` refits
    three sampled refit blocks from the estimates before them; `:322` rebuilds `evaluation.json`;
    `:326` ties every window to `prices.json`'s rows.
16. `app/src/App.tsx:15` loads `ForecastView` through `lazy()`, offered only when `meta.json` lists the
    eight files (`app/src/lib/gate.ts:25`).
17. `app/src/data/useForecastData.ts:67` is `useForecastFile`: the file of the pair on show, fetched
    once and kept; `loadForecast` (`:36`) parses it for the model and method its name gives (`:40`);
    a failed file is fetched again on the next pick (`:84`).
18. `app/src/lib/contract.forecast.ts:638` is `parseForecast`. It refuses another model's file
    (`:650`), bounds a window's `n` (`:373`) and reads the rows only after that (`:507`), and refuses an
    `sd_log` of 0 (`:470`). `parseDm` (`:901`) requires the three test fields null exactly for
    `same_as_rw` (`:916`); `parseCoverage` (`:941`) requires `lr` and `p_value` null exactly for a
    static path (`:964`).
19. `app/src/views/ForecastView.tsx:139` is the page body. A model without a refit shows the
    walk-forward in its place (`:149`). `FanChart` (`:326`) draws the exported bounds (`bandOf`,
    `:198`), on a log axis when asked (`:218`, ticks by `logTicks` at `app/src/lib/plot.ts:158`).
    In `app/src/views/ForecastView.tsx`, `WalkForward` (`:364`) starts paused (`:368`) and runs no
    timer under reduced motion (`:373`), and its status line is live only when paused (`:450`);
    `DmResult` (`:529`) shows a note instead of a test for a static path (`:530`), and every reading
    is the text of the exported verdict (`:570`, `:616`).
20. `app/src/lib/forecastText.ts:19` holds the fixed reading of each DM verdict, the `same_as_rw` one
    at `:26`, and `:33` those of the coverage verdicts. Each says what its test shows and what it does
    not.
21. `tools/build_notebooks.py:725` builds notebook 04. It prints the numbers below from the
    committed files, and rebuilds the static and walk-forward files and `evaluation.json` once to
    check they match (`:842`).

---

## Data flow

The AIC model's one-step forecast of 2024-01-02, the first oos day, followed from `fit.json` to the
page.

| # | Hop | Shape at this hop | Where |
|---|---|---|---|
| 1 | `price_table` rows from `prices.json` | 2,037 training, 227 test and 689 oos log closes; the oos window's origin is 2023-12-29, log 5.248134 ($190.21) | `src/arima_forecasting/forecasting.py:211` |
| 2 | `spec_from_fit` on `fit.models[0]` | ARIMA(3, 1, 4), trend `"t"`, 9 parameters in statsmodels' order | `src/arima_forecasting/forecasting.py:111` |
| 3 | `walk_forward(y, test.start, oos.stop, spec)` | one filter pass, 916 one-step means and variances (227 test, then 689 oos) | `src/arima_forecasting/forecasting.py:142` |
| 4 | Sliced to the oos window; its first row | `mean_log` 5.247584, `sd_log` 0.018549: the forecast sits 0.00055 log points below the random walk's | `src/arima_forecasting/forecasting.py:282` |
| 5 | `forecast_rows` | median $190.11, mean $190.14; normal 80% $185.64 to $194.68, 95% $183.32 to $197.15; t 80% $186.55 to $193.74, 95% $183.48 to $196.98; actual $183.40 | `src/arima_forecasting/forecasting.py:227` |
| 6 | `validate_forecast`, then the family check | every dollar value recomputed to 1e-9; the file against `fit.json` and `residuals_aic.json` | `src/arima_forecasting/payloads.py:2603` |
| 7 | `evaluation_payload`: this row's share | the random walk forecasts the origin's 5.248134; the model's error −0.035893, the random walk's −0.036443; absolute-loss d −0.00055 (the model is closer on this day); inside the normal 95% band, outside the t 95% band and both 80% bands | `src/arima_forecasting/evaluation.py:241` |
| 8 | `dm_test` over the 689 rows, absolute loss | mean d 2.6608e-4, DM* 2.5844 on 688 df, p 0.0100: `worse_than_rw` | `src/arima_forecasting/evaluation.py:142` |
| 9 | `coverage`, normal 80% | 599 of 689 inside (0.8694), Kupiec LR 22.95, p 1.7e-6: `too_wide` | `src/arima_forecasting/evaluation.py:195` |
| 10 | validate, check the family, `dumps`, write, check again | `forecast_aic_walk_forward.json` 654,568 bytes, `evaluation.json` 44,965 | `tools/export_app_data.py:175` |
| 11 | The reader opens **Forecast and evaluation** | `useEvaluationData` fetches `evaluation.json`; `parseEvaluation` re-checks it | `app/src/data/useForecastData.ts:45` |
| 12 | The reader picks aic, walk-forward, out of sample | `useForecastFile` fetches `forecast_aic_walk_forward.json`; `parseForecast` checks its id and method | `app/src/data/useForecastData.ts:67` |
| 13 | The walk-forward animation, day 1 | "Day 1 of 689, 2024-01-02 … median $190.11, 80% $185.64 to $194.68, 95% $183.32 to $197.15. Actual $183.40." | `app/src/views/ForecastView.tsx:364` |

```mermaid
sequenceDiagram
    participant X as export_app_data.py
    participant F as forecasting.py
    participant E as evaluation.py
    participant J as app/public/data
    participant A as Forecast page
    X->>F: price table (2,953 rows), fit.json models, residual t fits
    F->>F: static: filter to the origin, get_forecast(n)
    F->>F: walk-forward: one filter pass, one-step predictions
    F->>F: refit (aic): 43 refits, each block forecast at its estimates
    F-->>E: seven forecast payloads (rows: mean_log, sd_log, dollars, bounds)
    E->>E: random walk, metrics, ratios, DM (one-step), coverage
    E-->>X: evaluation
    X->>J: validate each, check the family, write (or --check: compare)
    A->>J: fetch evaluation.json, then the picked forecast file
    A->>A: re-check, draw; readings keyed by verdict
```

---

## Pitfalls met and how each is guarded

| Pitfall | How it showed up | Guard (`file:line`) |
|---|---|---|
| **The course's module 9 cannot forecast** | `ARIMA(train_data, order).fit()` on a frame indexed by trading dates, then `get_forecast(steps=len(test_data))`: trading dates have no frequency (holidays), and statsmodels 0.15 raises "No supported index is available". Reproduced on a simulated series with three holidays taken out | Every model is built on a numpy array and the dates are put back from the table (`src/arima_forecasting/forecasting.py:106`); `tests/test_forecasting.py:282` reproduces the course's failure and shows ours forecasts the same dates |
| **The course's module 10 MAPE is NaN** | It subtracts a one-column DataFrame (yfinance 1.7.0's `Close`) from a Series; pandas lines the Series' index up against the column labels, so every cell is NaN. Reproduced on three made-up prices | `_vector` refuses anything but one-dimensional numbers (`src/arima_forecasting/evaluation.py:86`); `tests/test_evaluation.py:52` reproduces the NaN, shows the frame refused and its column giving the hand value 4.697% |
| **`extend()` restarts the drift's time trend** | Found while choosing the reference loop: on statsmodels 0.15.0, a loop of `extend()` agrees with the single pass without a trend, but with trend `"t"` its second forecast is lower by drift × 220 = 0.176 on the simulated series, as if the next day were t = 2 | The reference loop appends instead (`src/arima_forecasting/forecasting.py:160`); `tests/test_forecasting.py:96` pins both behaviours, so a statsmodels change shows up |
| **An ARIMA(0, 1, 0) without a drift is the random walk** | The synthetic export tests (`tests/test_export.py`, a 2 × 2 grid on a simulated snapshot) produced a model whose one-step errors were the random walk's (the traceback shows the two error arrays equal, and the loss differential was constant); `dm_test` raised "the loss differential is constant" in the module fixture, and the tests that used it errored | `same_as_rw` when the largest forecast gap is ≤ `SAME_TOLERANCE` = 1e-9 log points: no statistic, no p-value (`src/arima_forecasting/evaluation.py:161`); both readers tie the nulls to the verdict (`src/arima_forecasting/payloads.py:2713`) and pin the tolerance (`:2838`, `app/src/lib/contract.forecast.ts:812`); `tests/test_evaluation.py:135` (the boundary, one ulp above it) and `:222` (a random-walk model in a payload) |
| **A near-normal residual series gives a huge t df** | `payloads.py` records that scipy's `t.fit` on a simulated Gaussian walk returned more than 1e6. Python's reader checks each t quantile by evaluating the t's CDF, whose continued fraction needs about √df terms, and the plain difference of two log-gamma values loses digits at large df (7e-10 when half the df is 10⁶, `_lgamma_ratio`'s docstring) | From `T_ASYMPTOTIC_DF` = 1e4 the quantile is checked against the Cornish–Fisher expansion to 1e-12 relative (`src/arima_forecasting/payloads.py:2525`); `_lgamma_ratio` uses Stirling's series from 50 (`:2266`); `tests/test_payloads_forecast.py:286` passes the producer's numbers at df up to 1e300, and `:301` checks the expansion against scipy from df 1e3 |
| **Kupiec's LR can be −0.0** | A count exactly at the level (8 of 10 at 80%) gives −2 × 0.0 = −0.0 in floating point, which JSON writes as `-0.0` | `kupiec` clamps at 0 (`src/arima_forecasting/evaluation.py:183`), and so does Python's reader (`src/arima_forecasting/payloads.py:2358`); `tests/test_payloads_forecast.py:307` checks the sign bit with `copysign` |
| **Timings would break `--check`** | The brief asked for the walk-forward and refit times in `evaluation.json`; a wall-clock value differs on every run | Kept out (`docs/architecture/contract.md` §2 "Determinism" and §3.10); measured in [Timings](#timings) |
| **A forecast that sees its own day** | Mutants P2 (the walk-forward reads one day ahead) and P12 (each refit sees its own block) | `tests/test_forecasting.py:113` and `:127` change every observation from day t on and require every forecast of day t or earlier unchanged |
| **A flat baseline rewards a drift** | The AIC model's static path beats the flat random walk (ratio 0.413 and 0.537) and a random walk with its drift does as well | Not guarded in code: measured in [The two probes](#the-two-probes-that-separate-causes), and stated in concept note 10 |
| **The 1 MB budget** | A model's two methods with t bands: 1,307,484 bytes for aic | One file per (model, method) (`src/arima_forecasting/forecasting.py:81`); `tests/test_committed_artifacts.py:124` fails any file over 1,000,000 bytes |
| **A stated count used before it is bounded** | Milestone 3's trap, again: a window's `n`, the refit list, the coverage rows | `n` ≤ `MAX_ROWS` before any row is read (`src/arima_forecasting/payloads.py:2361`, `app/src/lib/contract.forecast.ts:373`); a list of the wrong length is one short problem; `tests/test_payloads_forecast.py:319` gives a million refits and a million coverage rows and requires one problem in under a second; app mutant `m4-rows-read-past-max` |
| **An error message as long as the value** | Quoting a wrong array of a million elements with `JSON.stringify` | `shown` quotes at most 8 items or 80 characters (`app/src/lib/contract.ts:98`); app mutant `m4-reader-quotes-whole-array` |
| **Legend icons drawn at 300 px** | Milestone 3's browser-only trap: `.plot svg` is 100% wide | Explicit sizes on each mark (`app/src/views/ForecastView.tsx:47`); app mutant `m4-legend-mark-unsized` |
| **Motion the reader did not ask for** | An animation that plays on load, or ignores reduced motion | Starts paused (`app/src/views/ForecastView.tsx:368`), no timer under reduced motion (`:373`); app mutants `m4-animation-autoplays`, `m4-reduced-motion-ignored` |
| **The app recomputing a verdict** | App mutants that read one row's verdict for another, or swap a reading | Readings keyed by each row's exported verdict (`app/src/views/ForecastView.tsx:570`, `:616`); `ForecastView.test.tsx` flips one verdict at a time |

---

## Predict before you look

**Write your answers down before you scroll.** Commit to a number, even a guess.

1. The course's static path from the last training day: will the AIC model beat a flat line at the
   origin's price on the test window? On the oos window? Give the ratio of its dollar RMSE to the
   flat line's. Will the BIC and course models?
2. If the AIC model does beat the flat line, how much of that is its drift? Guess the dollar RMSE
   of a random walk that carries the AIC model's drift, against the AIC model's.
3. Walk-forward one step ahead: will any model beat yesterday's price? Give a ratio of RMSE.
4. Diebold–Mariano: on which window and loss, if any, will it reject equal accuracy, and in which
   direction?
5. Re-estimating every 21 trading days: will the AIC model's one-step RMSE ratio move by more than
   0.01? Will every refit converge?
6. The normal 80% and 95% one-step intervals: too narrow, too wide or about right, in 2023? From
   2024 on? The variance-matched t intervals?
7. How far is the mean price above the median one step ahead? At the end of the 227-day and 689-day
   static paths? On which static paths will the mean have the lower RMSE?
8. How long does one filter pass over 916 days take, against the append loop and the 43 refits?
   How big is each file against the 1 MB budget?

---

## Measured results

### Environment

The committed files were exported from the 13:37 UTC snapshot of milestone 1 (`prices.json`,
`source.downloaded_at` 2026-10-29T13:37:24Z, `raw_sha256` beginning `f1c0e13fd87a`; no new download).
No dependency was added or upgraded in this milestone (`pyproject.toml`, `uv.lock`, `app/package.json`
and `app/package-lock.json` are unchanged since milestone 3's commit), so the versions are those in
the milestone-3 walkthrough. The machine was shared with other jobs throughout; each timing below
gives the load average it ran under.

### Answers to the predictions

Rounding: values are rounded to the digits shown; the files hold the full doubles. "Command" names
the script section that printed the value (item numbers of `m4_numbers.py`).

| What | Command | Result | Date |
|---|---|---|---|
| Q1. Static against the flat random walk | `m4_numbers.py`, item 1 | AIC: RMSE $10.632 against $25.717 (ratio **0.4134**) on test; $34.256 against $63.796 (**0.5370**) on oos. BIC: 1.0027 and 1.0002. Course: 1.0107 and 0.9991 | 2026-10-29 |
| Q2. The drift | item 6 | A random walk with the AIC model's drift (0.000901858 a day): RMSE **$10.339** (AIC $10.632) on test, **$34.309** (AIC $34.256) on oos; the two paths at most **$0.718** and **$0.276** apart on any day | 2026-10-29 |
| Q3. One step against yesterday's price | item 1 | No model beats it on dollar RMSE, log RMSE or dollar MAE. Dollar RMSE ratios 1.0056 (bic, test) to 1.0174 (aic, oos); log RMSE ratios 1.0054 to 1.0175; dollar MAE ratios 1.0019 to 1.0263 | 2026-10-29 |
| Q4. Diebold–Mariano | items 1 and 2 | Test window: `no_difference` on every row (p 0.23 to 0.91). Oos: absolute loss `worse_than_rw` for all four one-step forecasts (p 0.0100 aic, 0.0103 aic refit, **0.0002** bic, 0.0242 course); squared loss `worse_than_rw` for bic only (p **0.0480**), the others 0.080 to 0.18. 5 of 16 tests reject, every one in oos, every one "worse" | 2026-10-29 |
| Q5. The refit | items 1 and 11 | AIC ratio 1.0122 (test) and 1.0137 (oos), against 1.0118 and 1.0174 without refits. 43 refits, **all converged**, 2 to 54 iterations, 0 warnings. From the training fit to the last refit the MA terms moved most (`ma.L2` 1.5029 to 1.5714, `ma.L3` 0.2476 to 0.327, `ma.L4` −0.0831 to −0.0457), the AR terms by under 0.004 | 2026-10-29 |
| Q6. One-step coverage | item 3 | Test: **every** one-step interval `too_wide` (normal 80%: 0.9515 to 0.9559 inside). Oos: normal 80% `too_wide` for all four (0.8679 to 0.8795); t 80% `consistent` for all four (0.7983 to 0.8099); 95% `consistent` for all, normal and t | 2026-10-29 |
| Q7. Median and mean | item 4 | One step: mean above median by at most 0.0165% to 0.0177% per path. End of the static paths: test 3.32% (aic), 3.80% (bic), 3.47% (course); oos 10.42%, 11.98%, 10.91%. Mean RMSE lower than the median's on 5 of the 6 static paths; higher on aic oos ($49.817 against $34.256) | 2026-10-29 |
| Q8. Timings | item 13, two runs | One filter pass over 916 days: **0.0261 s** and **0.0270 s** (aic); the append loop: **8.08 s** and **5.52 s**; the 43 refits: **27.81 s** and **12.21 s** | 2026-10-29 |
| Q8. Sizes | item 12 | Forecast files 652,916 to 700,824 bytes (refit the largest, 70.1% of 1 MB); `evaluation.json` 44,965. All 18 files carry `schema_version` 1.5.0 (`m4_facts.py`) | 2026-10-29 |

### The headline table

`m4_numbers.py` item 1. RMSE and MAE are of the median price, in dollars; "ratio" is the model's
over the random walk's of the same kind and window (static: flat at the origin; one step:
yesterday's price). DM p-values are HLN-corrected, two-sided, for squared then absolute loss of the
log errors; static paths are not tested.

| Model | Method | Window | RMSE $ | Random walk $ | RMSE ratio | Log RMSE ratio | MAE ratio | MAPE % | DM p: squared; absolute |
|---|---|---|---|---|---|---|---|---|---|
| aic | static | test | 10.632 | 25.717 | **0.4134** | 0.3956 | 0.3669 | 4.649 | not tested |
| aic | static | oos | 34.256 | 63.796 | **0.5370** | 0.5083 | 0.5450 | 12.173 | not tested |
| aic | walk_forward | test | 2.111 | 2.087 | 1.0118 | 1.0093 | 1.0044 | 0.939 | 0.4483; 0.8125 |
| aic | walk_forward | oos | 4.114 | 4.044 | 1.0174 | 1.0175 | 1.0211 | 1.206 | 0.0801; **0.0100 worse** |
| aic | refit | test | 2.112 | 2.087 | 1.0122 | 1.0097 | 1.0047 | 0.940 | 0.4296; 0.7967 |
| aic | refit | oos | 4.099 | 4.044 | 1.0137 | 1.0143 | 1.0187 | 1.203 | 0.1090; **0.0103 worse** |
| bic | static | test | 25.788 | 25.717 | 1.0027 | 1.0030 | 1.0028 | 12.571 | not tested |
| bic | static | oos | 63.811 | 63.796 | 1.0002 | 1.0003 | 1.0003 | 19.500 | not tested |
| bic | walk_forward | test | 2.098 | 2.087 | 1.0056 | 1.0054 | 1.0019 | 0.937 | 0.5862; 0.9095 |
| bic | walk_forward | oos | 4.110 | 4.044 | 1.0165 | 1.0157 | 1.0263 | 1.210 | **0.0480 worse**; **0.0002 worse** |
| course | static | test | 25.991 | 25.717 | 1.0107 | 1.0118 | 1.0111 | 12.676 | not tested |
| course | static | oos | 63.738 | 63.796 | 0.9991 | 0.9989 | 0.9989 | 19.474 | not tested |
| course | walk_forward | test | 2.102 | 2.087 | 1.0075 | 1.0068 | 1.0039 | 0.939 | 0.2334; 0.6274 |
| course | walk_forward | oos | 4.078 | 4.044 | 1.0085 | 1.0075 | 1.0098 | 1.190 | 0.1813; **0.0242 worse** |

**What the numbers say.**

- **The AIC model's static win is its drift.** The static test origin is $151.79 (2023-02-03) and
  the test window ended at $190.21. A flat line at the origin misses the whole rise; a path with a
  drift of 0.0009 log points a day follows part of it. A random walk with the same drift scores
  within $0.30 of the AIC model's RMSE on both windows (item 6). BIC and course have no drift, and
  their static paths score within 1.1% of the flat line's RMSE.
- **One step ahead, no model knows more than yesterday's price.** Every one-step ratio in the table
  is above 1, by 0.2% to 2.6%. The AIC model's one-step forecasts sit on average 0.00088 (test) and 0.00091 (oos) log
  points above yesterday's price, about its drift; BIC's and the course's sit within 0.0001 of it
  on average (item 9). Why the models lose by this much is not measured.
- **The DM rejections are all in oos, and all say "worse".** Absolute loss rejects for all four
  forecasts; squared loss for BIC only, at p 0.048. 16 tests are run, so about 0.8 rejections would
  come by chance with every null true; five rejections in one direction, on one window, are a
  pattern, with the caveats in [DM assumptions](#dm-assumptions).
- **The refit does not rescue the one-step forecasts.** Re-estimating every 21 days moves the AIC
  model's oos ratio from 1.0174 to 1.0137, still above 1, and its DM verdicts do not change.

### Coverage

`m4_numbers.py` item 3. The share of days whose actual log price lies inside each interval, with
Kupiec's verdict for the one-step forecasts ("< 0.0001" where the script printed p 0.0000).

| Forecast | Window | Normal 80% | Normal 95% | t 80% | t 95% |
|---|---|---|---|---|---|
| aic walk_forward | test | 0.9559 too wide (p < 0.0001) | 0.9868 too wide (p 0.0026) | 0.9031 too wide (p < 0.0001) | 0.9868 too wide (p 0.0026) |
| aic walk_forward | oos | 0.8694 too wide (p < 0.0001) | 0.9507 consistent (p 0.9372) | 0.8099 consistent (p 0.5146) | 0.9463 consistent (p 0.6594) |
| aic refit | test | 0.9515 too wide (p < 0.0001) | 0.9868 too wide (p 0.0026) | 0.9031 too wide (p < 0.0001) | 0.9868 too wide (p 0.0026) |
| aic refit | oos | 0.8679 too wide (p < 0.0001) | 0.9478 consistent (p 0.7879) | 0.7983 consistent (p 0.9091) | 0.9405 consistent (p 0.2657) |
| bic walk_forward | test | 0.9559 too wide (p < 0.0001) | 0.9868 too wide (p 0.0026) | 0.9163 too wide (p < 0.0001) | 0.9824 too wide (p 0.0102) |
| bic walk_forward | oos | 0.8752 too wide (p < 0.0001) | 0.9536 consistent (p 0.6649) | 0.8026 consistent (p 0.8637) | 0.9521 consistent (p 0.7986) |
| course walk_forward | test | 0.9559 too wide (p < 0.0001) | 0.9912 too wide (p 0.0005) | 0.8899 too wide (p 0.0003) | 0.9868 too wide (p 0.0026) |
| course walk_forward | oos | 0.8795 too wide (p < 0.0001) | 0.9579 consistent (p 0.3280) | 0.7983 consistent (p 0.9091) | 0.9507 consistent (p 0.9372) |

The static paths are shown and not tested (their days are not independent). At 80%, normal then t:
aic 1.0000 and 1.0000 (test), 0.9550 and 0.9245 (oos); bic 1.0000 and 0.8414, 0.9942 and 0.8723;
course 0.9824 and 0.8018, 0.9869 and 0.8302. At 95% every static path covers 0.9985 to 1.0000.

The t multipliers (item 5) are below the normal's at both levels: aic (t df 3.4070) 1.0194 at 80%
and 1.9136 at 95%, bic (3.3738) 1.0146 and 1.9092, course (3.2392) 0.9931 and 1.8887, against
1.2816 and 1.9600. So each t interval lies inside the normal one, and covers no more days than it:
fewer in most rows, as many where no actual fell between the two (the test window's 95% rows of aic
and its refit, for example).

### Median vs mean

`m4_numbers.py` item 4. "Gap" is how far the mean exp(μ + s²/2) sits above the median exp(μ),
largest and average over the window's rows; then each one's dollar RMSE and MAE.

| Model | Method | Window | Gap max | Gap mean | RMSE: median | RMSE: mean | MAE: median | MAE: mean |
|---|---|---|---|---|---|---|---|---|
| aic | static | test | 3.3221% | 1.6612% | 10.632 | 9.552 | 8.291 | 7.302 |
| aic | static | oos | 10.4195% | 5.1332% | **34.256** | 49.817 | **27.813** | 41.737 |
| bic | static | test | 3.7979% | 1.8958% | 25.788 | 22.710 | 22.660 | 19.866 |
| bic | static | oos | 11.9772% | 5.8848% | 63.811 | **51.853** | 51.047 | **40.838** |
| course | static | test | 3.4714% | 1.7348% | 25.991 | 23.176 | 22.849 | 20.296 |
| course | static | oos | 10.9072% | 5.3688% | 63.738 | **52.815** | 50.978 | **41.601** |
| aic | walk_forward | test / oos | 0.0172% | 0.0172% | 2.111 / 4.114 | 2.112 / 4.114 | 1.613 / 2.830 | 1.613 / 2.830 |
| aic | refit | test / oos | 0.0172% / 0.0165% | 0.0168% / 0.0161% | 2.112 / 4.099 | 2.113 / 4.099 | 1.613 / 2.823 | 1.613 / 2.823 |
| bic | walk_forward | test / oos | 0.0173% | 0.0173% | 2.098 / 4.110 | 2.096 / 4.108 | 1.609 / 2.844 | 1.606 / 2.841 |
| course | walk_forward | test / oos | 0.0177% | 0.0177% | 2.102 / 4.078 | 2.100 / 4.076 | 1.612 / 2.799 | 1.609 / 2.795 |

**What it says.** One step ahead the two differ by under 0.02%, and the choice does not matter. On a
long static path it does, and which one scores better depends on the path, not on the loss: on aic's
oos path the mean is worse on both RMSE and MAE, on bic's and the course's it is better on both. The
last oos day shows why (item 10): aic's median is $353.99 and its mean $390.87 against an actual
$333.02, so its drift already overshoots and the mean overshoots more; bic's median is $190.19 and
mean $212.97, and the course's $190.29 and $211.05, both far below $333.02, so the higher mean is
closer. In expectation the mean minimises squared error and the median absolute error (concept note
11); one path is one draw, and says nothing about the expectation.

### The two probes that separate causes

**1. Is the AIC model's static advantage its drift?** (item 6.) The probe scores a random walk that
carries the AIC model's drift (0.000901858 log points a day, from `fit.json`) on the same windows.

| Window | RW + drift RMSE | AIC static RMSE | Flat RW RMSE | Largest daily gap, AIC against RW + drift |
|---|---|---|---|---|
| test | $10.339 | $10.632 | $25.717 | $0.718 |
| oos | $34.309 | $34.256 | $63.796 | $0.276 |

The AIC model's seven AR and MA coefficients move its static path by at most $0.718 from the drift
line. The drift takes the RMSE from the flat line's $25.717 to $10.339 (test) and from $63.796 to
$34.309 (oos); the ARMA part then changes it by $0.29 for the worse (test) and $0.05 for the better
(oos). So the advantage over the flat line is the drift.

**2. Is a one-step interval wrong in its scale or in its shape?** (items 7 and 8.) Divide each
one-step error by its stated `sd_log`. If the scale is right, the root mean square of the result is
close to 1. Then rescale every error to that window's realised scale and count again: what is still
off is the shape. Item 8 gives the scale of the market itself: the sd of daily log returns was 0.01886 in
training (√σ² of the AIC model: 0.01855), 0.01215 in the test window and 0.01732 in oos.

| Model | Window | rms(e / sd) | Kurtosis of e / sd | Rescaled: normal 80% | normal 95% | t 80% | t 95% |
|---|---|---|---|---|---|---|---|
| aic | test | 0.6633 | 4.810 | 0.824 | 0.956 | 0.727 | 0.952 |
| aic | oos | 0.9511 | 10.651 | 0.864 | 0.942 | 0.792 | 0.936 |
| bic | test | 0.6586 | 4.883 | 0.833 | 0.956 | 0.722 | 0.956 |
| bic | oos | 0.9463 | 10.985 | 0.861 | 0.949 | 0.779 | 0.946 |
| course | test | 0.6523 | 4.642 | 0.828 | 0.956 | 0.718 | 0.956 |
| course | oos | 0.9284 | 11.638 | 0.858 | 0.945 | 0.776 | 0.939 |

- **Test window: the scale.** The errors were 0.65 to 0.66 times the stated sd, as the daily returns
  were 0.64 times as variable as in training (0.01215 against 0.01886). Rescaled, the normal covers
  0.824 to 0.833 at 80% and 0.956 at 95%, close to the levels. So the intervals were too wide
  because the model's one σ² came from more volatile years. Rescaled, the t's 80% interval covers
  0.718 to 0.727, too few: the test window's standardised errors (kurtosis 4.6 to 4.9) have less
  of their mass near the centre than a t on 3.2 to 3.4 degrees of freedom. These rescaled rates are
  not tested.
- **Oos window: what is left after the scale.** The scale is close (0.93 to 0.95), and rescaling
  changes the normal 80% coverage little (0.869 to 0.864 for aic). The standardised errors have a
  kurtosis of 10.7 to 11.6, and 85.8% to 86.4% of them lie within 1.2816 times their own root mean
  square, where a normal puts 80%: too many sit near the centre, so the normal 80% interval holds too
  many days. The variance-matched t, narrower in the centre, covers 0.810 (aic), consistent.

**3. How much of that kurtosis is clustering inside the window?** (`ewma_probe.py`, added in the
review fix round.) A window-wide rescale cannot see volatility that moves within the window. Dividing
each error instead by the square root of a trailing exponentially weighted average of the squared
errors before it (λ = 0.94, seeded with the first sd_log², days before t only) lowers the oos
kurtosis from 10.65 to 6.80 (aic), 10.99 to 6.99 (bic) and 11.64 to 6.92 (course): about half the
excess is clustering this average can follow. The normal 80% over-coverage survives it: 0.853, 0.856
and 0.855 after this rescale. So the over-coverage is not the window's scale and not the clustering
a trailing average removes; what remains is a shape with more errors near the centre than a normal
has. That is not a proof of fat tails in the shocks themselves: a trailing average removes only the
clustering it can follow.

### DM assumptions

At h = 1 the test uses γ₀ alone, which is right only if the loss differential d is serially
uncorrelated. Four probes ask whether it is (`m4_numbers.py` items 14 to 17; walk-forward forecasts,
item 15 also the refit).

**Item 14: Ljung–Box at lag 10 on d.** Test window: no autocorrelation for any model or loss (p 0.252
to 0.873). Oos: autocorrelation in the squared-loss d of every model (p printed as 0.000, so below
0.0005; lag-1 autocorrelation 0.157, 0.253 and 0.263 for aic, bic and course), and in the absolute-loss d of bic and course
(p 0.001; aic 0.297).

**Item 17: is that real, or heavy tails?** Ljung–Box assumes independent, equally variable terms; d
has fat tails and clustered variance. A regression of d_t on d_(t−1) with White's (HC0) standard
errors does not find the lag-1 term in any oos squared-loss d: p 0.1407 (aic), 0.0678 (bic), 0.0910
(course), against p below 0.0001 with ordinary errors. For the course model's oos absolute-loss d
the same happens (ordinary p 0.0075, White 0.1291). White's errors change only the inference; the
lag-1 slopes stay at 0.157 to 0.263. Lag 1 alone is not the question, though.

**Probe 4: all five lags at once, with White's errors** (added in the second review pass; now
computed by `signflip_bootstrap.py`). The regression of d_t on d_(t−1) to d_(t−5) with White's (HC0)
errors, and the joint Wald test of the five slopes: for the oos squared loss, p 0.0008 (bic), 0.0056
(course) and 0.0763 (aic); for every absolute loss and every test-window row, p 0.2512 to 0.7783. The
second review pass read the first two as robust evidence of autocorrelation, and the h = 1 test as
mis-specified there. **That reading is withdrawn** (probe 5): the White test itself is far too
liberal on these series.

**Probe 5: every test against a null that has no autocorrelation** (`signflip_bootstrap.py`, added
in the third review pass). The sign-flip null keeps each |d_t − mean| where it is, so the heavy tails
and the clustered variance stay, and gives each a random sign, so d has no autocorrelation. Under it,
how often does each test reject at nominal 5%? And where does the observed statistic fall among the
null's (the calibrated p)? Oos rows; 1,000 draws for the White test and 2,000 for the DM reference,
seed 20261030:

| Forecast, oos | White joint p | its rejections under the null | calibrated p | DM p (γ₀) | t-reference rejections under the null | top-5 days' share of Σ(d − mean)² |
|---|---|---|---|---|---|---|
| aic walk_forward, squared | 0.0763 | 37.9% | 0.4206 | 0.0801 | 4.0% | 0.67 |
| aic walk_forward, absolute | 0.5697 | 10.2% | 0.6593 | 0.0100 | 5.1% | 0.20 |
| aic refit, squared | 0.0787 | 36.4% | 0.4246 | 0.1090 | 4.4% | 0.69 |
| aic refit, absolute | 0.6764 | 11.9% | 0.7832 | 0.0103 | 4.3% | 0.23 |
| bic walk_forward, squared | 0.0008 | 38.2% | 0.1518 | 0.0480 | 4.3% | 0.60 |
| bic walk_forward, absolute | 0.4063 | 15.0% | 0.5774 | 0.0002 | 5.0% | 0.21 |
| course walk_forward, squared | 0.0056 | 49.1% | 0.3357 | 0.1813 | 4.4% | 0.74 |
| course walk_forward, absolute | 0.3774 | 12.4% | 0.5075 | 0.0242 | 4.8% | 0.22 |

- **The White test rejects 38% and 49% of the time with no autocorrelation at all** (bic, course
  squared), so its p of 0.0008 and 0.0056 are not evidence: calibrated against the null, they are
  0.15 and 0.34. Nothing here confirms autocorrelation beyond what the tails and the clustering make
  on their own; nothing rules it out either. ADR-0003's condition to revisit the test is not met.
- **The γ̂₀ test with its t(n − 1) reference is correctly sized here**: 4.0% to 5.7% under the null
  over all 16 rows, test window included (the standard error of a rate near 5% from 2,000 draws is
  0.5 points).
- **Every oos squared-loss verdict is borderline anyway.** Five days carry 60% to 74% of Σ(d −
  mean)², so a handful of days decide the test, and other variances move the verdicts across 5%
  (next table, and item 15).

| Forecast, oos | Block bootstrap p, blocks of 5 / 10 / 20 days | Newey–West p, 6 / 9 lags |
|---|---|---|
| aic walk_forward, squared | 0.0825 / 0.0280 / 0.0180 | 0.0629 / 0.0234 |
| aic walk_forward, absolute | 0.0095 / 0.0060 / 0.0025 | 0.0057 / 0.0034 |
| aic refit, squared | 0.1109 / 0.0410 / 0.0180 | 0.0920 / 0.0393 |
| aic refit, absolute | 0.0085 / 0.0020 / 0.0030 | 0.0069 / 0.0041 |
| bic walk_forward, squared | 0.1159 / 0.0475 / 0.0140 | 0.0858 / 0.0426 |
| bic walk_forward, absolute | 0.0020 / 0.0005 / 0.0010 | 0.0002 / 0.0001 |
| course walk_forward, squared | 0.1579 / 0.0655 / 0.0295 | 0.1046 / 0.0660 |
| course walk_forward, absolute | 0.0195 / 0.0085 / 0.0065 | 0.0165 / 0.0131 |

The circular block bootstrap resamples blocks of the centred d (2,000 draws); Newey–West is
statsmodels' HAC variance of the mean (Bartlett weights, autocovariances divided by n), against
t(n − 1). **The absolute-loss "worse than the random walk" verdicts are robust**: every p is at most
0.024 under γ̂₀, both Newey–West lag counts and all three block lengths. **The squared-loss ones are
not**: with blocks of 10 or 20 days, or Newey–West at 9 lags, the AIC model's and the AIC refit's
reject as well (p 0.018 to 0.041), the course model's does with blocks of 20 (0.030), and bic's moves
from 0.116 to 0.014 with the block length. So it is not only bic's verdict that depends on the
variance, as the second pass wrote. The defaults
(LEARNING_LOG, overridable by the owner): no Newey–West DM in the contract; the γ̂₀ test stays the
exported one; these checks stay in the docs.

**Item 16: which part of the squared-loss d?** With g the model's forecast minus the random walk's
and e the model's error, d = −2ge − g². In oos the −2ge part carries the variance (its variance is
1.008 to 1.073 times d's; the two parts covary negatively) and has lag-1 autocorrelation 0.188,
0.273 and 0.247 (aic, bic, course); −g² has lag-1 autocorrelation 0.637, 0.863 and 0.231, but its variance is only
0.005 to 0.016 of d's.

**Item 15: a Bartlett-weighted long-run variance in place of γ₀** (lags int(4 (n/100)^(2/9)) and
round(n^(1/3)): 4 and 6 on test, 6 and 9 on oos; against a t on n − 1, two-sided). `m4_numbers.py`
divides each autocovariance by n − k, so this is not quite statsmodels' Newey–West (divisor n, in
probe 5's table); the p-values differ by at most 0.0009 on oos (bic: 0.0856 and 0.0421 here, 0.0858
and 0.0426 there).

| Forecast | Oos squared: L 6 | L 9 | Oos absolute: L 6 | L 9 |
|---|---|---|---|---|
| aic walk_forward | 0.0627 | 0.0229 | 0.0057 | 0.0034 |
| aic refit | 0.0917 | 0.0387 | 0.0069 | 0.0041 |
| bic walk_forward | 0.0856 | 0.0421 | 0.0002 | 0.0001 |
| course walk_forward | 0.1039 | 0.0651 | 0.0165 | 0.0130 |

The absolute-loss verdicts stand under both lags (p 0.0001 to 0.017). The squared-loss ones move
across 5% with the lag: none rejects with 6 lags, three do with 9. Read them as borderline, not as
findings. In the test window every p is from 0.2204 to 0.9015, no rejection, as with γ₀.

**Does clustering alone break the test? A simulation** (`dm_size.py`, 2,000 runs each, seed
20261029). A random-walk log price and two one-step forecasts on either side of the best one,
y_(t−1) ± 0.001 × sign(r_(t−1)), so their expected losses are equal by symmetry: every rejection at
5% is false.

| Returns | n | Squared loss | Absolute loss |
|---|---|---|---|
| iid normal | 227 | 0.0520 | 0.0455 |
| iid normal | 689 | 0.0420 | 0.0510 |
| GARCH(1, 1), t(4) shocks | 227 | 0.0445 | 0.0465 |
| GARCH(1, 1), t(4) shocks | 689 | 0.0475 | 0.0450 |
| GARCH, two forecasts with their own clustered error parts | 227 | **0.1255** | **0.1420** |

The standard error of a rate near 5% from 2,000 runs is √(0.05 × 0.95 / 2000) = 0.0049, so the first
four rows (0.0420 to 0.0520) are at 5% within about two standard errors: when both forecasts are
made from the day before and their difference is known then, clustering and fat tails do not break
the test. The last row does: when each forecast's error carries its own clustered part, d inherits
the clustering, and the test rejects 2.5 (squared) and 2.8 (absolute) times as often as it should.
Whether AAPL's oos d is closer to the first set-up or the last is not measured: probe 5 finds
no evidence of the autocorrelation the last row needs, and cannot rule it out. The Newey–West and
block-bootstrap columns are the hedge.

### Timings

`m4_numbers.py --time`, item 13, `time.perf_counter()`; the single pass is the median of five. Run 2
repeated run 1's command three minutes later (23:23, then 23:26), at a lower load.

| What | Run 1 (load average 63.5 → 55.6) | Run 2 (52.3 → 46.4) |
|---|---|---|
| aic walk-forward, one filter pass over 916 days | 0.0261 s | 0.0270 s |
| bic, the same | 0.0077 s | 0.0081 s |
| course, the same | 0.0042 s | 0.0045 s |
| aic append loop, 916 steps | 8.08 s | 5.52 s |
| aic expanding refit, 43 refits and their forecasts | 27.81 s | 12.21 s |

The append loop and the single pass give the same forecasts on AAPL's 916 days: means within
8.88e-16 and variances identical (relative difference 0.00e+00). The loop took 204 and 310 times as
long as the pass (5.52 / 0.0270 and 8.08 / 0.0261), because it filters the whole history again at
every step. The refit ran 2.3 times as long in run 1 as in run 2, and the append loop 1.5 times;
the variation is the load, which these runs do not control.

The full export (`/usr/bin/time -v tools/export_app_data.py`, no `--only`) took **862 s** wall clock
(14:22), 5,651.7 s of user time at 657% CPU, under a load average of 50 to 64 and, for part of it,
beside this milestone's Python mutant run. How the 862 s split between the grid, the fits, the
forecasts and the refit was not measured in that run; the refit alone took 12 to 28 s above.

### The commands behind the table

Every number in Measured results except the full-export time came from one of these scripts, each
run from the repository root against the committed files (the scripts are not committed; the review
rounds' probes are listed after them):

```bash
OPENBLAS_NUM_THREADS=1 uv run python m4_numbers.py --time   # items 1 to 17; --time adds item 13
uv run python dm_size.py                                     # the DM size simulation, about 2 s
uv run python m4_facts.py                                    # windows, envelopes, the data-flow row
OPENBLAS_NUM_THREADS=1 uv run python ewma_probe.py          # probe 3 (review fix round)
OPENBLAS_NUM_THREADS=1 uv run python signflip_bootstrap.py  # probes 4 and 5 (third review pass), about 5 s
uv run python t_crossover.py                                 # where the t interval passes the normal (concept note 11)
OPENBLAS_NUM_THREADS=1 uv run python variance_excess.py     # why SIGMA2_REL is 1e-4 (third review pass)
uv run python sweep.py 200000   # the size sweep of both readers (third review pass): every array of every base payload,
                                # 200,000 items, each case in its own process; with case_ts.mjs and the app's parsers bundled by esbuild
```

`m4_numbers.py`, every milestone-4 number from the committed files:

```python
# Every milestone-4 number in the docs, from the committed files in app/public/data.
# Usage: OPENBLAS_NUM_THREADS=1 uv run python m4_numbers.py [--time]
import json, math, sys, time
from pathlib import Path
import numpy as np
from scipy import stats
from arima_forecasting.artifacts import read_artifact, table_from_prices
from arima_forecasting.forecasting import FORECASTS, NORMAL_Z, refit_walk_forward, spec_from_fit, walk_forward, walk_forward_loop, windows

D = Path("app/public/data")
ev = read_artifact(D, "evaluation")["data"]
fc = {f"forecast_{m}_{k}": read_artifact(D, f"forecast_{m}_{k}")["data"] for m, k in FORECASTS}
fit = read_artifact(D, "fit")["data"]
models = {m["id"]: m for m in fit["models"]}
table = table_from_prices(read_artifact(D, "prices")["data"])
y = table["log_close"].to_numpy()
test, oos = windows(table)
kinds = {m["id"]: m["kind"] for m in ev["methods"]}
rw = {(r["kind"], r["window"]): r for r in ev["random_walk"]}
dm = {(r["model_id"], r["method"], r["window"], r["loss"]): r for r in ev["dm"]}

print("1. headline: model method window | RMSE $ (median) | RW | ratio | RMSE log ratio | MAE $ ratio | MAPE % | DM p squared, absolute")
for r in ev["metrics"]:
    b = rw[(kinds[r["method"]], r["window"])]
    p = [dm.get((r["model_id"], r["method"], r["window"], l)) for l in ("squared", "absolute")]
    ps = "-" if p[0] is None else f"{p[0]['p_value']:.4f} {p[0]['verdict']}, {p[1]['p_value']:.4f} {p[1]['verdict']}"
    print(f"   {r['model_id']:>6} {r['method']:>12} {r['window']:>4} | {r['usd_median']['rmse']:8.3f} | {b['usd']['rmse']:8.3f} | {r['ratio_to_rw']['usd_median']['rmse']:.4f} | {r['ratio_to_rw']['log']['rmse']:.4f} | {r['ratio_to_rw']['usd_median']['mae']:.4f} | {r['usd_median']['mape_pct']:.3f} | {ps}")

print("2. DM rows: statistic_hln, df, p")
for r in ev["dm"]:
    print(f"   {r['model_id']:>6} {r['method']:>12} {r['window']:>4} {r['loss']:>8}: mean_diff {r['mean_diff']: .4e} DM* {r['statistic_hln']: .4f} df {r['df']} p {r['p_value']:.4f} gap {r['max_forecast_gap']:.4g} {r['verdict']}")

print("3. coverage: inside/n rate verdict (Kupiec p)")
for c in ev["coverage"]:
    pv = "" if c["p_value"] is None else f" p {c['p_value']:.4f}"
    print(f"   {c['model_id']:>6} {c['method']:>12} {c['window']:>4} {c['distribution']:>6} {c['level']}: {c['inside']}/{c['n']} = {c['rate']:.4f} {c['verdict']}{pv}")

print("4. median vs mean: back_transform max and mean (%), RMSE $ on median vs on mean")
for r in ev["metrics"]:
    bt = r["back_transform"]
    print(f"   {r['model_id']:>6} {r['method']:>12} {r['window']:>4}: max {bt['max_pct']:.4f}% mean {bt['mean_pct']:.4f}% | RMSE median {r['usd_median']['rmse']:.3f} mean {r['usd_mean']['rmse']:.3f} | MAE median {r['usd_median']['mae']:.3f} mean {r['usd_mean']['mae']:.3f}")

print("5. t fits and multipliers")
for m in ev["models"]:
    iv = fc[f"forecast_{m['id']}_static"]["intervals"]
    print(f"   {m['id']}: t_df {m['t_df']:.4f}, multipliers 80% {iv['t_multiplier'][0]:.4f} 95% {iv['t_multiplier'][1]:.4f} (normal {NORMAL_Z[0]:.4f}, {NORMAL_Z[1]:.4f})")

print("6. probe: is the static AIC gain the drift? RMSE $ of a random walk with the AIC model's drift, static")
drift = next(p["value"] for p in models["aic"]["params"] if p["name"] == "drift")
for w in (test, oos):
    h = np.arange(1, w.stop - w.start + 1)
    path = np.exp(y[w.start - 1] + drift * h)
    a = np.exp(y[w.start:w.stop])
    aic = np.array([r["median_usd"] for r in next(x for x in fc["forecast_aic_static"]["windows"] if x["id"] == w.id)["rows"]])
    print(f"   {w.id}: drift {drift:.6g}/day; RW+drift RMSE {np.sqrt(np.mean((a - path) ** 2)):.3f}; AIC static RMSE {np.sqrt(np.mean((a - aic) ** 2)):.3f}; max |AIC - RW+drift| {np.max(np.abs(aic - path)):.3f} $")

print("7. probe: one-step coverage, scale or shape? per window: realised sd of one-step errors / mean sd_log; kurtosis of e/sd; coverage after rescaling sd to the realised one")
for mid in ("aic", "bic", "course"):
    data = fc[f"forecast_{mid}_walk_forward"]
    k = data["intervals"]["t_multiplier"]
    for w in data["windows"]:
        e = np.array([r["actual_log"] - r["mean_log"] for r in w["rows"]]); s = np.array([r["sd_log"] for r in w["rows"]])
        z = e / s
        scale = np.sqrt(np.mean(z ** 2))
        zz = z / scale
        cov = {f"{d}{int(l*100)}": np.mean(np.abs(zz) <= m) for d, ms in (("n", NORMAL_Z), ("t", k)) for l, m in zip((0.8, 0.95), ms)}
        print(f"   {mid} {w['id']:>4}: rms(e/sd) {scale:.4f}; Pearson kurtosis of e/sd {stats.kurtosis(z, fisher=False):.3f}; rescaled coverage " + " ".join(f"{a} {b:.3f}" for a, b in cov.items()))

print("8. training sd of daily log returns vs the windows' (log points)")
r = np.diff(y)
print(f"   train {np.std(r[:test.start - 1]):.5f}, test {np.std(r[test.start - 1:test.stop - 1]):.5f}, oos {np.std(r[oos.start - 1:oos.stop - 1]):.5f}; sqrt(sigma2) aic {math.sqrt(next(p['value'] for p in models['aic']['params'] if p['name'] == 'sigma2')):.5f}")

print("9. one-step forecasts' distance from the random walk's: max |mean_log - previous actual| (log points), and the drift share")
for mid in ("aic", "bic", "course"):
    for w in fc[f"forecast_{mid}_walk_forward"]["windows"]:
        prev = [w["origin"]["log_close"]] + [r["actual_log"] for r in w["rows"][:-1]]
        g = np.array([r["mean_log"] - p for r, p in zip(w["rows"], prev)])
        print(f"   {mid} {w['id']:>4}: mean {g.mean():.3e} sd {g.std():.3e} max |.| {np.abs(g).max():.3e}")

print("10. static paths at their last day: sd_log and the 95% band")
for mid in ("aic", "bic", "course"):
    for w in fc[f"forecast_{mid}_static"]["windows"]:
        last = w["rows"][-1]
        print(f"   {mid} {w['id']:>4} day {w['n']}: median ${last['median_usd']:.2f} mean ${last['mean_usd']:.2f} sd_log {last['sd_log']:.4f} 95% ${last['lower_95_usd']:.2f}-${last['upper_95_usd']:.2f} actual ${last['actual_usd']:.2f}")

print("11. refits: count, converged, iterations, first and last estimates of the AIC model")
rf = fc["forecast_aic_refit"]["refits"]
print(f"   {len(rf)} refits, all converged {all(x['converged'] for x in rf)}, iterations {min(x['iterations'] for x in rf)}-{max(x['iterations'] for x in rf)}, warnings {sum(len(x['warnings']) for x in rf)}")
print("   train  ", [round(p["value"], 4) for p in models["aic"]["params"]])
print("   last   ", [round(p["value"], 4) for p in rf[-1]["params"]])

print("12. file sizes (bytes)")
for p in sorted(D.glob("forecast_*.json")) + [D / "evaluation.json"]:
    print(f"   {p.name} {p.stat().st_size}")

if "--time" in sys.argv:
    print("13. timings (perf_counter, seconds; median of 5 for the single pass)")
    for mid in ("aic", "bic", "course"):
        spec = spec_from_fit(models[mid])
        ts = []
        for _ in range(5):
            t0 = time.perf_counter(); walk_forward(y, test.start, oos.stop, spec); ts.append(time.perf_counter() - t0)
        print(f"   {mid} walk-forward single filter pass, {oos.stop - test.start} days: {sorted(ts)[2]:.4f}")
    spec = spec_from_fit(models["aic"])
    t0 = time.perf_counter(); m1, v1 = walk_forward_loop(y, test.start, oos.stop, spec); t1 = time.perf_counter()
    m2, v2 = walk_forward(y, test.start, oos.stop, spec)
    print(f"   aic append loop, {oos.stop - test.start} steps: {t1 - t0:.2f}; max |mean - single pass| {np.max(np.abs(m1 - m2)):.2e}, max rel |var - single pass| {np.max(np.abs(v1 / v2 - 1)):.2e}")
    t0 = time.perf_counter(); refit_walk_forward(y, test.start, oos.stop, spec); t1 = time.perf_counter()
    print(f"   aic expanding refit every 21 days: {t1 - t0:.2f}")

print("14. is the loss differential serially uncorrelated (what gamma_0 alone assumes at h = 1)? ACF lags 1-5 and Ljung-Box p at lag 10")
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf
for mid in ("aic", "bic", "course"):
    for w in fc[f"forecast_{mid}_walk_forward"]["windows"]:
        prev = np.array([w["origin"]["log_close"]] + [r["actual_log"] for r in w["rows"][:-1]])
        a = np.array([r["actual_log"] for r in w["rows"]]); m = np.array([r["mean_log"] for r in w["rows"]])
        for loss, f in (("squared", np.square), ("absolute", np.abs)):
            d = f(a - m) - f(a - prev)
            print(f"   {mid} {w['id']:>4} {loss:>8}: acf {np.round(acf(d, nlags=5, fft=False)[1:], 3).tolist()}; Ljung-Box(10) p {float(acorr_ljungbox(d, lags=[10])['lb_pvalue'].iloc[0]):.3f}")

print("15. probe: DM with a Newey-West (Bartlett) long-run variance instead of gamma_0, lags L = int(4 (n/100)^(2/9)) and round(n^(1/3)), against t(n - 1), two-sided")
def nw(d, L):
    n = len(d); x = d - d.mean()
    v = np.mean(x * x) + 2 * sum((1 - k / (L + 1)) * np.mean(x[k:] * x[:-k]) for k in range(1, L + 1))
    return d.mean() / np.sqrt(v / n)
for mid, meth in (("aic", "walk_forward"), ("aic", "refit"), ("bic", "walk_forward"), ("course", "walk_forward")):
    for w in fc[f"forecast_{mid}_{meth}"]["windows"]:
        prev = np.array([w["origin"]["log_close"]] + [r["actual_log"] for r in w["rows"][:-1]])
        a = np.array([r["actual_log"] for r in w["rows"]]); m = np.array([r["mean_log"] for r in w["rows"]])
        for loss, f in (("squared", np.square), ("absolute", np.abs)):
            d = f(a - m) - f(a - prev); n = len(d)
            L1 = int(4 * (n / 100) ** (2 / 9)); L2 = int(round(n ** (1 / 3)))
            out = []
            for L in (L1, L2):
                s = nw(d, L); out.append(f"L {L}: DM {s: .3f} p {2 * stats.t.sf(abs(s), n - 1):.4f}")
            print(f"   {mid} {meth:>12} {w['id']:>4} {loss:>8}: " + "; ".join(out))

print("16. probe: which part of the squared-loss differential d = -2 g e - g^2 (g = model - random-walk forecast, e = model error) is autocorrelated? oos, lag-1 ACF and Ljung-Box(10) p of each part, and each part's share of var(d)")
for mid in ("aic", "bic", "course"):
    w = fc[f"forecast_{mid}_walk_forward"]["windows"][1]
    prev = np.array([w["origin"]["log_close"]] + [r["actual_log"] for r in w["rows"][:-1]])
    a = np.array([r["actual_log"] for r in w["rows"]]); m = np.array([r["mean_log"] for r in w["rows"]])
    g, e = m - prev, a - m
    for name, part in (("-2 g e", -2 * g * e), ("-g^2", -g * g)):
        print(f"   {mid} {name:>7}: acf1 {acf(part, nlags=1, fft=False)[1]: .3f}; Ljung-Box(10) p {float(acorr_ljungbox(part, lags=[10])['lb_pvalue'].iloc[0]):.3f}; var share {np.var(part) / np.var(-2 * g * e - g * g):.3f}")

print("17. probe: is the lag-1 autocorrelation of d real, or heavy tails and clustering inflating the sample ACF? OLS of d_t on d_(t-1) with White (HC0) standard errors, and the ordinary ones")
import statsmodels.api as sm
for mid, meth in (("aic", "walk_forward"), ("bic", "walk_forward"), ("course", "walk_forward")):
    for w in fc[f"forecast_{mid}_{meth}"]["windows"]:
        prev = np.array([w["origin"]["log_close"]] + [r["actual_log"] for r in w["rows"][:-1]])
        a = np.array([r["actual_log"] for r in w["rows"]]); m = np.array([r["mean_log"] for r in w["rows"]])
        for loss, f in (("squared", np.square), ("absolute", np.abs)):
            d = f(a - m) - f(a - prev)
            X = sm.add_constant(d[:-1])
            ols = sm.OLS(d[1:], X).fit(); rob = sm.OLS(d[1:], X).fit(cov_type="HC0")
            print(f"   {mid} {w['id']:>4} {loss:>8}: slope {ols.params[1]: .3f}; p ordinary {ols.pvalues[1]:.4f}, p White {rob.pvalues[1]:.4f}")
```

<details>
<summary>What it printed (without <code>--time</code>, 23:28; items 1 to 12 and 14 are byte-identical, by <code>diff</code>, to the first <code>--time</code> run's, whose item 13 is below)</summary>

```text
1. headline: model method window | RMSE $ (median) | RW | ratio | RMSE log ratio | MAE $ ratio | MAPE % | DM p squared, absolute
      aic       static test |   10.632 |   25.717 | 0.4134 | 0.3956 | 0.3669 | 4.649 | -
      aic       static  oos |   34.256 |   63.796 | 0.5370 | 0.5083 | 0.5450 | 12.173 | -
      aic walk_forward test |    2.111 |    2.087 | 1.0118 | 1.0093 | 1.0044 | 0.939 | 0.4483 no_difference, 0.8125 no_difference
      aic walk_forward  oos |    4.114 |    4.044 | 1.0174 | 1.0175 | 1.0211 | 1.206 | 0.0801 no_difference, 0.0100 worse_than_rw
      aic        refit test |    2.112 |    2.087 | 1.0122 | 1.0097 | 1.0047 | 0.940 | 0.4296 no_difference, 0.7967 no_difference
      aic        refit  oos |    4.099 |    4.044 | 1.0137 | 1.0143 | 1.0187 | 1.203 | 0.1090 no_difference, 0.0103 worse_than_rw
      bic       static test |   25.788 |   25.717 | 1.0027 | 1.0030 | 1.0028 | 12.571 | -
      bic       static  oos |   63.811 |   63.796 | 1.0002 | 1.0003 | 1.0003 | 19.500 | -
      bic walk_forward test |    2.098 |    2.087 | 1.0056 | 1.0054 | 1.0019 | 0.937 | 0.5862 no_difference, 0.9095 no_difference
      bic walk_forward  oos |    4.110 |    4.044 | 1.0165 | 1.0157 | 1.0263 | 1.210 | 0.0480 worse_than_rw, 0.0002 worse_than_rw
   course       static test |   25.991 |   25.717 | 1.0107 | 1.0118 | 1.0111 | 12.676 | -
   course       static  oos |   63.738 |   63.796 | 0.9991 | 0.9989 | 0.9989 | 19.474 | -
   course walk_forward test |    2.102 |    2.087 | 1.0075 | 1.0068 | 1.0039 | 0.939 | 0.2334 no_difference, 0.6274 no_difference
   course walk_forward  oos |    4.078 |    4.044 | 1.0085 | 1.0075 | 1.0098 | 1.190 | 0.1813 no_difference, 0.0242 worse_than_rw
2. DM rows: statistic_hln, df, p
      aic walk_forward test  squared: mean_diff  2.7642e-06 DM*  0.7595 df 226 p 0.4483 gap 0.005792 no_difference
      aic walk_forward test absolute: mean_diff  2.8634e-05 DM*  0.2375 df 226 p 0.8125 gap 0.005792 no_difference
      aic walk_forward  oos  squared: mean_diff  1.0614e-05 DM*  1.7524 df 688 p 0.0801 gap 0.01694 no_difference
      aic walk_forward  oos absolute: mean_diff  2.6608e-04 DM*  2.5844 df 688 p 0.0100 gap 0.01694 worse_than_rw
      aic        refit test  squared: mean_diff  2.8921e-06 DM*  0.7914 df 226 p 0.4296 gap 0.005943 no_difference
      aic        refit test absolute: mean_diff  3.1175e-05 DM*  0.2579 df 226 p 0.7967 gap 0.005943 no_difference
      aic        refit  oos  squared: mean_diff  8.6757e-06 DM*  1.6048 df 688 p 0.1090 gap 0.01591 no_difference
      aic        refit  oos absolute: mean_diff  2.3581e-04 DM*  2.5739 df 688 p 0.0103 gap 0.01591 worse_than_rw
      bic walk_forward test  squared: mean_diff  1.6059e-06 DM*  0.5452 df 226 p 0.5862 gap 0.004462 no_difference
      bic walk_forward test absolute: mean_diff  1.2671e-05 DM*  0.1138 df 226 p 0.9095 gap 0.004462 no_difference
      bic walk_forward  oos  squared: mean_diff  9.5412e-06 DM*  1.9810 df 688 p 0.0480 gap 0.01312 worse_than_rw
      bic walk_forward  oos absolute: mean_diff  3.1999e-04 DM*  3.7810 df 688 p 0.0002 gap 0.01312 worse_than_rw
   course walk_forward test  squared: mean_diff  2.0193e-06 DM*  1.1949 df 226 p 0.2334 gap 0.003932 no_difference
   course walk_forward test absolute: mean_diff  3.0672e-05 DM*  0.4860 df 226 p 0.6274 gap 0.003932 no_difference
   course walk_forward  oos  squared: mean_diff  4.5305e-06 DM*  1.3382 df 688 p 0.1813 gap 0.0109 no_difference
   course walk_forward  oos absolute: mean_diff  1.1658e-04 DM*  2.2588 df 688 p 0.0242 gap 0.0109 worse_than_rw
3. coverage: inside/n rate verdict (Kupiec p)
      aic       static test normal 0.8: 227/227 = 1.0000 not_tested
      aic       static test normal 0.95: 227/227 = 1.0000 not_tested
      aic       static test      t 0.8: 227/227 = 1.0000 not_tested
      aic       static test      t 0.95: 227/227 = 1.0000 not_tested
      aic       static  oos normal 0.8: 658/689 = 0.9550 not_tested
      aic       static  oos normal 0.95: 689/689 = 1.0000 not_tested
      aic       static  oos      t 0.8: 637/689 = 0.9245 not_tested
      aic       static  oos      t 0.95: 688/689 = 0.9985 not_tested
      aic walk_forward test normal 0.8: 217/227 = 0.9559 too_wide p 0.0000
      aic walk_forward test normal 0.95: 224/227 = 0.9868 too_wide p 0.0026
      aic walk_forward test      t 0.8: 205/227 = 0.9031 too_wide p 0.0000
      aic walk_forward test      t 0.95: 224/227 = 0.9868 too_wide p 0.0026
      aic walk_forward  oos normal 0.8: 599/689 = 0.8694 too_wide p 0.0000
      aic walk_forward  oos normal 0.95: 655/689 = 0.9507 consistent p 0.9372
      aic walk_forward  oos      t 0.8: 558/689 = 0.8099 consistent p 0.5146
      aic walk_forward  oos      t 0.95: 652/689 = 0.9463 consistent p 0.6594
      aic        refit test normal 0.8: 216/227 = 0.9515 too_wide p 0.0000
      aic        refit test normal 0.95: 224/227 = 0.9868 too_wide p 0.0026
      aic        refit test      t 0.8: 205/227 = 0.9031 too_wide p 0.0000
      aic        refit test      t 0.95: 224/227 = 0.9868 too_wide p 0.0026
      aic        refit  oos normal 0.8: 598/689 = 0.8679 too_wide p 0.0000
      aic        refit  oos normal 0.95: 653/689 = 0.9478 consistent p 0.7879
      aic        refit  oos      t 0.8: 550/689 = 0.7983 consistent p 0.9091
      aic        refit  oos      t 0.95: 648/689 = 0.9405 consistent p 0.2657
      bic       static test normal 0.8: 227/227 = 1.0000 not_tested
      bic       static test normal 0.95: 227/227 = 1.0000 not_tested
      bic       static test      t 0.8: 191/227 = 0.8414 not_tested
      bic       static test      t 0.95: 227/227 = 1.0000 not_tested
      bic       static  oos normal 0.8: 685/689 = 0.9942 not_tested
      bic       static  oos normal 0.95: 689/689 = 1.0000 not_tested
      bic       static  oos      t 0.8: 601/689 = 0.8723 not_tested
      bic       static  oos      t 0.95: 688/689 = 0.9985 not_tested
      bic walk_forward test normal 0.8: 217/227 = 0.9559 too_wide p 0.0000
      bic walk_forward test normal 0.95: 224/227 = 0.9868 too_wide p 0.0026
      bic walk_forward test      t 0.8: 208/227 = 0.9163 too_wide p 0.0000
      bic walk_forward test      t 0.95: 223/227 = 0.9824 too_wide p 0.0102
      bic walk_forward  oos normal 0.8: 603/689 = 0.8752 too_wide p 0.0000
      bic walk_forward  oos normal 0.95: 657/689 = 0.9536 consistent p 0.6649
      bic walk_forward  oos      t 0.8: 553/689 = 0.8026 consistent p 0.8637
      bic walk_forward  oos      t 0.95: 656/689 = 0.9521 consistent p 0.7986
   course       static test normal 0.8: 223/227 = 0.9824 not_tested
   course       static test normal 0.95: 227/227 = 1.0000 not_tested
   course       static test      t 0.8: 182/227 = 0.8018 not_tested
   course       static test      t 0.95: 227/227 = 1.0000 not_tested
   course       static  oos normal 0.8: 680/689 = 0.9869 not_tested
   course       static  oos normal 0.95: 689/689 = 1.0000 not_tested
   course       static  oos      t 0.8: 572/689 = 0.8302 not_tested
   course       static  oos      t 0.95: 688/689 = 0.9985 not_tested
   course walk_forward test normal 0.8: 217/227 = 0.9559 too_wide p 0.0000
   course walk_forward test normal 0.95: 225/227 = 0.9912 too_wide p 0.0005
   course walk_forward test      t 0.8: 202/227 = 0.8899 too_wide p 0.0003
   course walk_forward test      t 0.95: 224/227 = 0.9868 too_wide p 0.0026
   course walk_forward  oos normal 0.8: 606/689 = 0.8795 too_wide p 0.0000
   course walk_forward  oos normal 0.95: 660/689 = 0.9579 consistent p 0.3280
   course walk_forward  oos      t 0.8: 550/689 = 0.7983 consistent p 0.9091
   course walk_forward  oos      t 0.95: 655/689 = 0.9507 consistent p 0.9372
4. median vs mean: back_transform max and mean (%), RMSE $ on median vs on mean
      aic       static test: max 3.3221% mean 1.6612% | RMSE median 10.632 mean 9.552 | MAE median 8.291 mean 7.302
      aic       static  oos: max 10.4195% mean 5.1332% | RMSE median 34.256 mean 49.817 | MAE median 27.813 mean 41.737
      aic walk_forward test: max 0.0172% mean 0.0172% | RMSE median 2.111 mean 2.112 | MAE median 1.613 mean 1.613
      aic walk_forward  oos: max 0.0172% mean 0.0172% | RMSE median 4.114 mean 4.114 | MAE median 2.830 mean 2.830
      aic        refit test: max 0.0172% mean 0.0168% | RMSE median 2.112 mean 2.113 | MAE median 1.613 mean 1.613
      aic        refit  oos: max 0.0165% mean 0.0161% | RMSE median 4.099 mean 4.099 | MAE median 2.823 mean 2.823
      bic       static test: max 3.7979% mean 1.8958% | RMSE median 25.788 mean 22.710 | MAE median 22.660 mean 19.866
      bic       static  oos: max 11.9772% mean 5.8848% | RMSE median 63.811 mean 51.853 | MAE median 51.047 mean 40.838
      bic walk_forward test: max 0.0173% mean 0.0173% | RMSE median 2.098 mean 2.096 | MAE median 1.609 mean 1.606
      bic walk_forward  oos: max 0.0173% mean 0.0173% | RMSE median 4.110 mean 4.108 | MAE median 2.844 mean 2.841
   course       static test: max 3.4714% mean 1.7348% | RMSE median 25.991 mean 23.176 | MAE median 22.849 mean 20.296
   course       static  oos: max 10.9072% mean 5.3688% | RMSE median 63.738 mean 52.815 | MAE median 50.978 mean 41.601
   course walk_forward test: max 0.0177% mean 0.0177% | RMSE median 2.102 mean 2.100 | MAE median 1.612 mean 1.609
   course walk_forward  oos: max 0.0177% mean 0.0177% | RMSE median 4.078 mean 4.076 | MAE median 2.799 mean 2.795
5. t fits and multipliers
   aic: t_df 3.4070, multipliers 80% 1.0194 95% 1.9136 (normal 1.2816, 1.9600)
   bic: t_df 3.3738, multipliers 80% 1.0146 95% 1.9092 (normal 1.2816, 1.9600)
   course: t_df 3.2392, multipliers 80% 0.9931 95% 1.8887 (normal 1.2816, 1.9600)
6. probe: is the static AIC gain the drift? RMSE $ of a random walk with the AIC model's drift, static
   test: drift 0.000901858/day; RW+drift RMSE 10.339; AIC static RMSE 10.632; max |AIC - RW+drift| 0.718 $
   oos: drift 0.000901858/day; RW+drift RMSE 34.309; AIC static RMSE 34.256; max |AIC - RW+drift| 0.276 $
7. probe: one-step coverage, scale or shape? per window: realised sd of one-step errors / mean sd_log; kurtosis of e/sd; coverage after rescaling sd to the realised one
   aic test: rms(e/sd) 0.6633; Pearson kurtosis of e/sd 4.810; rescaled coverage n80 0.824 n95 0.956 t80 0.727 t95 0.952
   aic  oos: rms(e/sd) 0.9511; Pearson kurtosis of e/sd 10.651; rescaled coverage n80 0.864 n95 0.942 t80 0.792 t95 0.936
   bic test: rms(e/sd) 0.6586; Pearson kurtosis of e/sd 4.883; rescaled coverage n80 0.833 n95 0.956 t80 0.722 t95 0.956
   bic  oos: rms(e/sd) 0.9463; Pearson kurtosis of e/sd 10.985; rescaled coverage n80 0.861 n95 0.949 t80 0.779 t95 0.946
   course test: rms(e/sd) 0.6523; Pearson kurtosis of e/sd 4.642; rescaled coverage n80 0.828 n95 0.956 t80 0.718 t95 0.956
   course  oos: rms(e/sd) 0.9284; Pearson kurtosis of e/sd 11.638; rescaled coverage n80 0.858 n95 0.945 t80 0.776 t95 0.939
8. training sd of daily log returns vs the windows' (log points)
   train 0.01886, test 0.01215, oos 0.01732; sqrt(sigma2) aic 0.01855
9. one-step forecasts' distance from the random walk's: max |mean_log - previous actual| (log points), and the drift share
   aic test: mean 8.779e-04 sd 1.704e-03 max |.| 5.792e-03
   aic  oos: mean 9.102e-04 sd 2.613e-03 max |.| 1.694e-02
   bic test: mean -2.895e-05 sd 1.697e-03 max |.| 4.462e-03
   bic  oos: mean -1.992e-05 sd 2.298e-03 max |.| 1.312e-02
   course test: mean -9.721e-05 sd 9.723e-04 max |.| 3.932e-03
   course  oos: mean -6.780e-05 sd 1.375e-03 max |.| 1.090e-02
10. static paths at their last day: sd_log and the 95% band
   aic test day 227: median $185.64 mean $191.81 sd_log 0.2557 95% $112.47-$306.40 actual $190.21
   aic  oos day 689: median $353.99 mean $390.87 sd_log 0.4452 95% $147.91-$847.18 actual $333.02
   bic test day 227: median $151.71 mean $157.47 sd_log 0.2730 95% $88.84-$259.07 actual $190.21
   bic  oos day 689: median $190.19 mean $212.97 sd_log 0.4757 95% $74.87-$483.14 actual $333.02
   course test day 227: median $151.47 mean $156.73 sd_log 0.2612 95% $90.77-$252.75 actual $190.21
   course  oos day 689: median $190.29 mean $211.05 sd_log 0.4550 95% $78.00-$464.23 actual $333.02
11. refits: count, converged, iterations, first and last estimates of the AIC model
   43 refits, all converged True, iterations 2-54, warnings 0
   train   [0.0009, -2.15, -1.6519, -0.4038, 2.092, 1.5029, 0.2476, -0.0831, 0.0003]
   last    [0.0009, -2.1501, -1.6482, -0.4024, 2.1149, 1.5714, 0.327, -0.0457, 0.0003]
12. file sizes (bytes)
   forecast_aic_refit.json 700824
   forecast_aic_static.json 652916
   forecast_aic_walk_forward.json 654568
   forecast_bic_static.json 653233
   forecast_bic_walk_forward.json 654114
   forecast_course_static.json 653590
   forecast_course_walk_forward.json 654966
   evaluation.json 44965
14. is the loss differential serially uncorrelated (what gamma_0 alone assumes at h = 1)? ACF lags 1-5 and Ljung-Box p at lag 10
   aic test  squared: acf [0.067, -0.036, 0.016, 0.036, -0.079]; Ljung-Box(10) p 0.408
   aic test absolute: acf [-0.011, -0.142, 0.048, 0.029, 0.023]; Ljung-Box(10) p 0.252
   aic  oos  squared: acf [0.157, -0.017, -0.105, -0.18, -0.09]; Ljung-Box(10) p 0.000
   aic  oos absolute: acf [-0.005, 0.021, -0.071, -0.048, -0.005]; Ljung-Box(10) p 0.297
   bic test  squared: acf [0.036, -0.08, -0.053, -0.038, -0.009]; Ljung-Box(10) p 0.873
   bic test absolute: acf [0.041, -0.152, -0.047, 0.007, 0.018]; Ljung-Box(10) p 0.583
   bic  oos  squared: acf [0.253, 0.197, -0.002, -0.237, -0.197]; Ljung-Box(10) p 0.000
   bic  oos absolute: acf [-0.002, 0.118, -0.038, -0.035, -0.037]; Ljung-Box(10) p 0.001
   course test  squared: acf [0.014, -0.012, -0.082, 0.029, 0.005]; Ljung-Box(10) p 0.669
   course test absolute: acf [-0.126, -0.027, -0.08, 0.069, -0.022]; Ljung-Box(10) p 0.522
   course  oos  squared: acf [0.263, -0.083, -0.417, -0.202, -0.027]; Ljung-Box(10) p 0.000
   course  oos absolute: acf [0.102, -0.076, -0.128, -0.071, 0.04]; Ljung-Box(10) p 0.001
15. probe: DM with a Newey-West (Bartlett) long-run variance instead of gamma_0, lags L = int(4 (n/100)^(2/9)) and round(n^(1/3)), against t(n - 1), two-sided
   aic walk_forward test  squared: L 4: DM  0.728 p 0.4672; L 6: DM  0.739 p 0.4606
   aic walk_forward test absolute: L 4: DM  0.257 p 0.7977; L 6: DM  0.260 p 0.7952
   aic walk_forward  oos  squared: L 6: DM  1.865 p 0.0627; L 9: DM  2.280 p 0.0229
   aic walk_forward  oos absolute: L 6: DM  2.773 p 0.0057; L 9: DM  2.939 p 0.0034
   aic        refit test  squared: L 4: DM  0.753 p 0.4520; L 6: DM  0.764 p 0.4456
   aic        refit test absolute: L 4: DM  0.278 p 0.7816; L 6: DM  0.281 p 0.7790
   aic        refit  oos  squared: L 6: DM  1.689 p 0.0917; L 9: DM  2.072 p 0.0387
   aic        refit  oos absolute: L 6: DM  2.711 p 0.0069; L 9: DM  2.883 p 0.0041
   bic walk_forward test  squared: L 4: DM  0.575 p 0.5660; L 6: DM  0.593 p 0.5537
   bic walk_forward test absolute: L 4: DM  0.124 p 0.9015; L 6: DM  0.127 p 0.8992
   bic walk_forward  oos  squared: L 6: DM  1.721 p 0.0856; L 9: DM  2.036 p 0.0421
   bic walk_forward  oos absolute: L 6: DM  3.711 p 0.0002; L 9: DM  3.970 p 0.0001
   course walk_forward test  squared: L 4: DM  1.226 p 0.2215; L 6: DM  1.229 p 0.2204
   course walk_forward test absolute: L 4: DM  0.571 p 0.5687; L 6: DM  0.572 p 0.5679
   course walk_forward  oos  squared: L 6: DM  1.628 p 0.1039; L 9: DM  1.847 p 0.0651
   course walk_forward  oos absolute: L 6: DM  2.404 p 0.0165; L 9: DM  2.489 p 0.0130
16. probe: which part of the squared-loss differential d = -2 g e - g^2 (g = model - random-walk forecast, e = model error) is autocorrelated? oos, lag-1 ACF and Ljung-Box(10) p of each part, and each part's share of var(d)
   aic  -2 g e: acf1  0.188; Ljung-Box(10) p 0.000; var share 1.071
   aic    -g^2: acf1  0.637; Ljung-Box(10) p 0.000; var share 0.016
   bic  -2 g e: acf1  0.273; Ljung-Box(10) p 0.000; var share 1.073
   bic    -g^2: acf1  0.863; Ljung-Box(10) p 0.000; var share 0.014
   course  -2 g e: acf1  0.247; Ljung-Box(10) p 0.000; var share 1.008
   course    -g^2: acf1  0.231; Ljung-Box(10) p 0.000; var share 0.005
17. probe: is the lag-1 autocorrelation of d real, or heavy tails and clustering inflating the sample ACF? OLS of d_t on d_(t-1) with White (HC0) standard errors, and the ordinary ones
   aic test  squared: slope  0.067; p ordinary 0.3111, p White 0.2778
   aic test absolute: slope -0.011; p ordinary 0.8718, p White 0.8752
   aic  oos  squared: slope  0.157; p ordinary 0.0000, p White 0.1407
   aic  oos absolute: slope -0.005; p ordinary 0.8901, p White 0.9536
   bic test  squared: slope  0.036; p ordinary 0.5842, p White 0.7395
   bic test absolute: slope  0.041; p ordinary 0.5427, p White 0.6760
   bic  oos  squared: slope  0.253; p ordinary 0.0000, p White 0.0678
   bic  oos absolute: slope -0.002; p ordinary 0.9655, p White 0.9878
   course test  squared: slope  0.014; p ordinary 0.8265, p White 0.8850
   course test absolute: slope -0.126; p ordinary 0.0563, p White 0.0718
   course  oos  squared: slope  0.263; p ordinary 0.0000, p White 0.0910
   course  oos absolute: slope  0.102; p ordinary 0.0075, p White 0.1291
```

Item 13 of the two `--time` runs (load averages 63.5 → 55.6, then 52.3 → 46.4):

```text
13. timings (perf_counter, seconds; median of 5 for the single pass)
   aic walk-forward single filter pass, 916 days: 0.0261
   bic walk-forward single filter pass, 916 days: 0.0077
   course walk-forward single filter pass, 916 days: 0.0042
   aic append loop, 916 steps: 8.08; max |mean - single pass| 8.88e-16, max rel |var - single pass| 0.00e+00
   aic expanding refit every 21 days: 27.81
13. timings (perf_counter, seconds; median of 5 for the single pass)
   aic walk-forward single filter pass, 916 days: 0.0270
   bic walk-forward single filter pass, 916 days: 0.0081
   course walk-forward single filter pass, 916 days: 0.0045
   aic append loop, 916 steps: 5.52; max |mean - single pass| 8.88e-16, max rel |var - single pass| 0.00e+00
   aic expanding refit every 21 days: 12.21
```

</details>

`dm_size.py`, the size of DM under a true null:

```python
# How often does DM with the HLN correction reject at 5% when the two one-step forecasts have the same
# expected loss? Usage: uv run python dm_size.py
# The log price is a random walk, y_t = y_(t-1) + r_t. Two forecasts made on day t - 1 sit on each side of
# the best one: y_(t-1) + c_t and y_(t-1) - c_t, with c_t = 0.001 times the sign of yesterday's return (known
# on day t - 1). By symmetry their expected losses are equal: the null is true. "separate parts" instead
# gives the two forecasts errors with their own independent clustered parts, unknown on day t - 1.
import numpy as np
from arima_forecasting.evaluation import dm_test
rng = np.random.default_rng(20261029)
def garch(n, omega=1e-5, alpha=0.1, beta=0.85):
    """GARCH(1, 1) returns with Student-t(4) innovations scaled to variance 1: clustering and fat tails."""
    z = rng.standard_t(4, n) / np.sqrt(2.0)
    s2 = omega / (1 - alpha - beta); out = np.empty(n)
    for t in range(n):
        out[t] = np.sqrt(s2) * z[t]; s2 = omega + alpha * out[t] ** 2 + beta * s2
    return out
iid = lambda n: 0.017 * rng.standard_normal(n)
reps = 2000
for label, draw in (("iid normal returns", iid), ("GARCH(1,1) returns, t(4) shocks", garch)):
    for n in (227, 689):
        hits = {"squared": 0, "absolute": 0}
        for _ in range(reps):
            r = draw(n + 1)
            c = 0.001 * np.sign(r[:-1]); r = r[1:]
            for loss in hits:
                hits[loss] += dm_test(r - c, r + c, loss)["p_value"] < 0.05
        print(f"{label}, n {n}, forecasts on each side of the best: squared {hits['squared'] / reps:.4f}, absolute {hits['absolute'] / reps:.4f} ({reps} runs)")
n = 227; hits = {"squared": 0, "absolute": 0}
for _ in range(reps):
    e, a, b = garch(n), 0.3 * garch(n), 0.3 * garch(n)
    for loss in hits:
        hits[loss] += dm_test(e + a, e + b, loss)["p_value"] < 0.05
print(f"GARCH, n {n}, separate clustered error parts: squared {hits['squared'] / reps:.4f}, absolute {hits['absolute'] / reps:.4f} ({reps} runs)")
```

It printed:

```text
iid normal returns, n 227, forecasts on each side of the best: squared 0.0520, absolute 0.0455 (2000 runs)
iid normal returns, n 689, forecasts on each side of the best: squared 0.0420, absolute 0.0510 (2000 runs)
GARCH(1,1) returns, t(4) shocks, n 227, forecasts on each side of the best: squared 0.0445, absolute 0.0465 (2000 runs)
GARCH(1,1) returns, t(4) shocks, n 689, forecasts on each side of the best: squared 0.0475, absolute 0.0450 (2000 runs)
GARCH, n 227, separate clustered error parts: squared 0.1255, absolute 0.1420 (2000 runs)
```

`m4_facts.py`, the facts the other two do not print:

```python
# The milestone-4 facts the walkthrough states that m4_numbers.py does not print: the windows, the
# row counts, one forecast row followed to the page, the refit bookkeeping and the envelopes.
# Usage (from the repository root): uv run python m4_facts.py
import json
from pathlib import Path
from arima_forecasting.artifacts import read_artifact
from arima_forecasting.forecasting import FORECAST_ARTIFACTS

D = Path("app/public/data")
ev = read_artifact(D, "evaluation")["data"]
fit = read_artifact(D, "fit")["data"]
meta = read_artifact(D, "meta")["data"]
source = read_artifact(D, "prices")["data"]["source"]
print("snapshot downloaded_at", source["downloaded_at"], "raw_sha256", source["raw_sha256"][:12])
print("windows", [(w["id"], w["start"], w["end"], w["n"], w["origin_date"]) for w in ev["windows"]])
print("rows: random_walk", len(ev["random_walk"]), "metrics", len(ev["metrics"]), "dm", len(ev["dm"]), "coverage", len(ev["coverage"]))
print("verdicts: dm", sorted({r["verdict"] for r in ev["dm"]}), "coverage", sorted({r["verdict"] for r in ev["coverage"]}))
print("meta lists", len(meta["artifacts"]), "artifacts; current milestone", [m["id"] for m in meta["milestones"] if m["status"] == "current"])
print("schema versions", sorted({json.loads((D / f"{n}.json").read_text())["schema_version"] for n in meta["artifacts"]}))
print("models", [(m["id"], m["order"], m["trend"]) for m in fit["models"]])
static = read_artifact(D, "forecast_aic_static")["data"]
print("static origins", [(x["id"], x["origin"]["date"], round(x["origin"]["close_usd"], 2)) for x in static["windows"]])
refit = read_artifact(D, "forecast_aic_refit")["data"]
print("n_train", fit["n_train"], "first refit", refit["refits"][0]["start_date"], refit["refits"][0]["n_obs"], "last refit", refit["refits"][-1]["start_date"], refit["refits"][-1]["n_obs"])
walk = read_artifact(D, "forecast_aic_walk_forward")["data"]
w = walk["windows"][1]
print("aic walk_forward oos origin", w["origin"])
print("aic walk_forward oos row 0", w["rows"][0])
print("intervals", walk["intervals"], "t_df", walk["t_df"])
row, origin = w["rows"][0], w["origin"]
e_model, e_rw = row["actual_log"] - row["mean_log"], row["actual_log"] - origin["log_close"]
print("row 0: e_model", e_model, "e_rw", e_rw, "d absolute", abs(e_model) - abs(e_rw), "d squared", e_model**2 - e_rw**2, "gap to the random walk", abs(row["mean_log"] - origin["log_close"]))
for dist, key in (("normal", "normal_z"), ("t", "t_multiplier")):
    for level, m in zip((0.8, 0.95), walk["intervals"][key]):
        print(f"row 0 inside {dist} {level}:", row["mean_log"] - m * row["sd_log"] <= row["actual_log"] <= row["mean_log"] + m * row["sd_log"])
for name in FORECAST_ARTIFACTS:
    data = read_artifact(D, name)["data"]
    print(name, "rows", [x["n"] for x in data["windows"]], "refits", None if data["refits"] is None else len(data["refits"]))
r = next(x for x in ev["dm"] if (x["model_id"], x["method"], x["window"], x["loss"]) == ("aic", "walk_forward", "oos", "absolute"))
print("dm aic walk_forward oos absolute", r)
c = next(x for x in ev["coverage"] if (x["model_id"], x["method"], x["window"], x["distribution"], x["level"]) == ("aic", "walk_forward", "oos", "normal", 0.8))
print("coverage aic walk_forward oos normal 0.8", c)
```

It printed:

```text
snapshot downloaded_at 2026-10-29T13:37:24Z raw_sha256 f1c0e13fd87a
windows [('test', '2023-02-06', '2023-12-29', 227, '2023-02-03'), ('oos', '2024-01-02', '2026-09-30', 689, '2023-12-29')]
rows: random_walk 4 metrics 14 dm 16 coverage 56
verdicts: dm ['no_difference', 'worse_than_rw'] coverage ['consistent', 'not_tested', 'too_wide']
meta lists 18 artifacts; current milestone [4]
schema versions ['1.5.0']
models [('aic', [3, 1, 4], 't'), ('bic', [2, 1, 2], 'n'), ('course', [0, 1, 1], 'n')]
static origins [('test', '2023-02-03', 151.79), ('oos', '2023-12-29', 190.21)]
n_train 2037 first refit 2023-03-08 2058 last refit 2026-09-14 2940
aic walk_forward oos origin {'close_usd': 190.21102905273438, 'date': '2023-12-29', 'log_close': 5.248134135037568}
aic walk_forward oos row 0 {'actual_log': 5.211691490971171, 'actual_usd': 183.40402221679688, 'date': '2024-01-02', 'lower_80_usd': 185.64061319548185, 'lower_95_usd': 183.31915363039434, 'mean_log': 5.247584311727054, 'mean_usd': 190.13918321885808, 'median_usd': 190.10647534071228, 'sd_log': 0.018549151556261814, 't_lower_80_usd': 186.5454626219106, 't_lower_95_usd': 183.47676922910273, 't_upper_80_usd': 193.7354651167162, 't_upper_95_usd': 196.97573768230663, 'upper_80_usd': 194.67977046818135, 'upper_95_usd': 197.14509504737725}
intervals {'levels': [0.8, 0.95], 'normal_z': [1.2815515655446004, 1.959963984540054], 't_multiplier': [1.0194177821324084, 1.9136320249213719], 't_quantile': [1.5863312216033982, 2.9778313474608535], 't_scale': 0.6426260595829557} t_df 3.4069707615721128
row 0: e_model -0.035892820755882404 e_rw -0.036442644066396745 d absolute -0.0005498233105143413 d squared -3.977172473617913e-05 gap to the random walk 0.0005498233105143413
row 0 inside normal 0.8: False
row 0 inside normal 0.95: True
row 0 inside t 0.8: False
row 0 inside t 0.95: False
forecast_aic_static rows [227, 689] refits None
forecast_aic_walk_forward rows [227, 689] refits None
forecast_aic_refit rows [227, 689] refits 43
forecast_bic_static rows [227, 689] refits None
forecast_bic_walk_forward rows [227, 689] refits None
forecast_course_static rows [227, 689] refits None
forecast_course_walk_forward rows [227, 689] refits None
dm aic walk_forward oos absolute {'df': 688, 'hln_factor': 0.9992740470912524, 'loss': 'absolute', 'max_forecast_gap': 0.01693660692732646, 'mean_diff': 0.00026608029447546064, 'method': 'walk_forward', 'model_id': 'aic', 'n': 689, 'p_value': 0.009960326488979527, 'statistic': 2.5862564293147323, 'statistic_hln': 2.584378928937104, 'var_diff': 7.292920516223025e-06, 'verdict': 'worse_than_rw', 'window': 'oos'}
coverage aic walk_forward oos normal 0.8 {'distribution': 'normal', 'inside': 599, 'level': 0.8, 'lr': 22.95146245749578, 'method': 'walk_forward', 'model_id': 'aic', 'n': 689, 'p_value': 1.661437614903965e-06, 'rate': 0.8693759071117562, 'verdict': 'too_wide', 'window': 'oos'}
```

The full-export time is from that run's `/usr/bin/time -v` report, as recorded in the measurement
log; the load averages are `uptime`'s at the start and end of each `--time` run. Notebook 04 prints
the windows, the metrics, the DM rows and the AIC model's coverage from the committed files, and
`tests/test_notebooks.py` checks the printed lines.

---

**`ewma_probe.py`** (added in the review fix round; probe 3 above). Run from the repo root:
`OPENBLAS_NUM_THREADS=1 uv run python ewma_probe.py`.

```python
# How much of the oos standardised errors' kurtosis is volatility clustering inside the window?
# Usage: OPENBLAS_NUM_THREADS=1 uv run python ewma_probe.py (from the repo root)
import numpy as np
from pathlib import Path
from scipy import stats
from arima_forecasting.artifacts import read_artifact
D = Path("app/public/data")
for mid in ("aic", "bic", "course"):
    rows = []
    for w in read_artifact(D, f"forecast_{mid}_walk_forward")["data"]["windows"]:
        rows += w["rows"]
    e = np.array([r["actual_log"] - r["mean_log"] for r in rows]); s = np.array([r["sd_log"] for r in rows])
    oos = slice(227, None)
    # A trailing exponentially weighted variance of the errors before each day (lambda 0.94), seeded with the first sd_log^2.
    v = np.empty_like(e); v[0] = s[0] ** 2
    for t in range(1, len(e)):
        v[t] = 0.94 * v[t - 1] + 0.06 * e[t - 1] ** 2
    for name, z in (("constant sd", (e / s)[oos]), ("EWMA sd", (e / np.sqrt(v))[oos])):
        zz = z / np.sqrt(np.mean(z ** 2))
        print(f"{mid} oos {name:>11}: Pearson kurtosis {stats.kurtosis(z, fisher=False):.2f}; rescaled normal-80% coverage {np.mean(np.abs(zz) <= 1.2815515655446004):.3f}")
```

Output on 2026-10-30, from the committed files:

```text
aic oos constant sd: Pearson kurtosis 10.65; rescaled normal-80% coverage 0.864
aic oos     EWMA sd: Pearson kurtosis 6.80; rescaled normal-80% coverage 0.853
bic oos constant sd: Pearson kurtosis 10.99; rescaled normal-80% coverage 0.861
bic oos     EWMA sd: Pearson kurtosis 6.99; rescaled normal-80% coverage 0.856
course oos constant sd: Pearson kurtosis 11.64; rescaled normal-80% coverage 0.858
course oos     EWMA sd: Pearson kurtosis 6.92; rescaled normal-80% coverage 0.855
```

**`signflip_bootstrap.py`** (added in the third review pass; probes 4 and 5 above). It replaces the
second pass's `white_joint.py`, whose HC0 joint p-values it prints in its first column. Run from the
repo root: `OPENBLAS_NUM_THREADS=1 uv run python signflip_bootstrap.py` (4.6 s wall clock).

```python
# Are the loss differentials autocorrelated, or do heavy tails and clustered variance fool the tests?
# A sign-flip null keeps every |d_t - mean| where it is (the tails and the clustering) and gives each a
# random sign, so it has no autocorrelation. Under it: the size of the White (HC0) joint test of lags
# 1-5, its calibrated p (the share of null Wald statistics at least the observed one), and the size of
# the HLN-DM t reference. Then the DM verdicts under other variances: circular block bootstrap of the
# mean of d (blocks of 5, 10, 20) and statsmodels' Newey-West HAC (divisor n) at 6 and 9 lags.
# Usage: OPENBLAS_NUM_THREADS=1 uv run python signflip_bootstrap.py (from the repo root; 4.5 s wall clock, measured 2026-10-30)
import math
from pathlib import Path
import numpy as np, statsmodels.api as sm
from scipy import stats
from statsmodels.stats.sandwich_covariance import cov_hac
from arima_forecasting.artifacts import read_artifact
D = Path("app/public/data")
rng = np.random.default_rng(20261030)
L, B_JOINT, B_DM, B_CBB = 5, 1000, 2000, 2000
R = np.zeros((L, L + 1)); R[:, 1:] = np.eye(L)
def joint(d):  # HC0 Wald statistic and p of the five lag slopes (chi-squared on 5 df)
    X = sm.add_constant(np.column_stack([d[L - k:len(d) - k] for k in range(1, L + 1)]))
    w = sm.OLS(d[L:], X).fit(cov_type="HC0").wald_test(R, scalar=True, use_f=False)
    return float(np.squeeze(w.statistic)), float(w.pvalue)
def dm_p(d):  # gamma_0 HLN-DM against t(n - 1), two-sided
    n = len(d); s = d.mean() / math.sqrt(np.mean((d - d.mean()) ** 2) / n) * math.sqrt((n - 1) / n)
    return 2 * stats.t.sf(abs(s), n - 1)
def hac_p(d, lags):  # statsmodels' Newey-West (Bartlett) variance of the mean, divisor n, against t(n - 1)
    fit = sm.OLS(d, np.ones((len(d), 1))).fit()
    se = math.sqrt(cov_hac(fit, nlags=lags, use_correction=False)[0, 0])
    return 2 * stats.t.sf(abs(d.mean() / se), len(d) - 1)
def cbb_p(d, block):  # circular block bootstrap of the mean of d, centred, two-sided
    n = len(d); u = d - d.mean(); ext = np.concatenate([u, u[:block]]); k = math.ceil(n / block)
    means = np.array([ext[(rng.integers(0, n, k)[:, None] + np.arange(block)).ravel()[:n]].mean() for _ in range(B_CBB)])
    return (1 + np.sum(np.abs(means) >= abs(d.mean()))) / (B_CBB + 1)
for mid, meth in (("aic", "walk_forward"), ("aic", "refit"), ("bic", "walk_forward"), ("course", "walk_forward")):
    for w in read_artifact(D, f"forecast_{mid}_{meth}")["data"]["windows"]:
        prev = np.array([w["origin"]["log_close"]] + [r["actual_log"] for r in w["rows"][:-1]])
        a = np.array([r["actual_log"] for r in w["rows"]]); m = np.array([r["mean_log"] for r in w["rows"]])
        for loss, f in (("squared", np.square), ("absolute", np.abs)):
            d = f(a - m) - f(a - prev); u = np.abs(d - d.mean())
            s0, p0 = joint(d)
            null = [joint(d.mean() + u * rng.choice([-1.0, 1.0], len(u))) for _ in range(B_JOINT)]
            size_joint = np.mean([p < 0.05 for _, p in null]); calibrated = (1 + sum(s >= s0 for s, _ in null)) / (B_JOINT + 1)
            size_dm = np.mean([dm_p(u * rng.choice([-1.0, 1.0], len(u))) < 0.05 for _ in range(B_DM)])
            top5 = np.sum(np.sort(u)[::-1][:5] ** 2) / np.sum(u ** 2)
            print(f"{mid} {meth} {w['id']} {loss}: HC0 joint p {p0:.4f}, its size under the null {size_joint:.3f}, calibrated p {calibrated:.4f} | DM p {dm_p(d):.4f}, t-reference size {size_dm:.3f}"
                  f" | top-5 days {top5:.2f} of sum (d - mean)^2 | CBB p 5/10/20: {cbb_p(d, 5):.4f} {cbb_p(d, 10):.4f} {cbb_p(d, 20):.4f} | HAC p 6/9 lags: {hac_p(d, 6):.4f} {hac_p(d, 9):.4f}", flush=True)
```

Output on 2026-10-30, from the committed files:

```text
aic walk_forward test squared: HC0 joint p 0.7765, its size under the null 0.066, calibrated p 0.8372 | DM p 0.4483, t-reference size 0.054 | top-5 days 0.59 of sum (d - mean)^2 | CBB p 5/10/20: 0.4588 0.4453 0.2679 | HAC p 6/9 lags: 0.4607 0.4312
aic walk_forward test absolute: HC0 joint p 0.3538, its size under the null 0.090, calibrated p 0.4146 | DM p 0.8125, t-reference size 0.050 | top-5 days 0.16 of sum (d - mean)^2 | CBB p 5/10/20: 0.8006 0.7881 0.7131 | HAC p 6/9 lags: 0.7954 0.7813
aic walk_forward oos squared: HC0 joint p 0.0763, its size under the null 0.379, calibrated p 0.4206 | DM p 0.0801, t-reference size 0.040 | top-5 days 0.67 of sum (d - mean)^2 | CBB p 5/10/20: 0.0825 0.0280 0.0180 | HAC p 6/9 lags: 0.0629 0.0234
aic walk_forward oos absolute: HC0 joint p 0.5697, its size under the null 0.102, calibrated p 0.6593 | DM p 0.0100, t-reference size 0.051 | top-5 days 0.20 of sum (d - mean)^2 | CBB p 5/10/20: 0.0095 0.0060 0.0025 | HAC p 6/9 lags: 0.0057 0.0034
aic refit test squared: HC0 joint p 0.7368, its size under the null 0.052, calibrated p 0.7932 | DM p 0.4296, t-reference size 0.050 | top-5 days 0.59 of sum (d - mean)^2 | CBB p 5/10/20: 0.4433 0.3978 0.2444 | HAC p 6/9 lags: 0.4457 0.4163
aic refit test absolute: HC0 joint p 0.3691, its size under the null 0.069, calibrated p 0.3986 | DM p 0.7967, t-reference size 0.050 | top-5 days 0.16 of sum (d - mean)^2 | CBB p 5/10/20: 0.7801 0.7541 0.6887 | HAC p 6/9 lags: 0.7791 0.7639
aic refit oos squared: HC0 joint p 0.0787, its size under the null 0.364, calibrated p 0.4246 | DM p 0.1090, t-reference size 0.044 | top-5 days 0.69 of sum (d - mean)^2 | CBB p 5/10/20: 0.1109 0.0410 0.0180 | HAC p 6/9 lags: 0.0920 0.0393
aic refit oos absolute: HC0 joint p 0.6764, its size under the null 0.119, calibrated p 0.7832 | DM p 0.0103, t-reference size 0.043 | top-5 days 0.23 of sum (d - mean)^2 | CBB p 5/10/20: 0.0085 0.0020 0.0030 | HAC p 6/9 lags: 0.0069 0.0041
bic walk_forward test squared: HC0 joint p 0.7783, its size under the null 0.122, calibrated p 0.8392 | DM p 0.5862, t-reference size 0.052 | top-5 days 0.45 of sum (d - mean)^2 | CBB p 5/10/20: 0.5602 0.5237 0.4223 | HAC p 6/9 lags: 0.5543 0.5326
bic walk_forward test absolute: HC0 joint p 0.5938, its size under the null 0.103, calibrated p 0.6264 | DM p 0.9095, t-reference size 0.048 | top-5 days 0.13 of sum (d - mean)^2 | CBB p 5/10/20: 0.9040 0.8906 0.8846 | HAC p 6/9 lags: 0.8994 0.8974
bic walk_forward oos squared: HC0 joint p 0.0008, its size under the null 0.382, calibrated p 0.1518 | DM p 0.0480, t-reference size 0.043 | top-5 days 0.60 of sum (d - mean)^2 | CBB p 5/10/20: 0.1159 0.0475 0.0140 | HAC p 6/9 lags: 0.0858 0.0426
bic walk_forward oos absolute: HC0 joint p 0.4063, its size under the null 0.150, calibrated p 0.5774 | DM p 0.0002, t-reference size 0.050 | top-5 days 0.21 of sum (d - mean)^2 | CBB p 5/10/20: 0.0020 0.0005 0.0010 | HAC p 6/9 lags: 0.0002 0.0001
course walk_forward test squared: HC0 joint p 0.4033, its size under the null 0.096, calibrated p 0.5125 | DM p 0.2334, t-reference size 0.057 | top-5 days 0.54 of sum (d - mean)^2 | CBB p 5/10/20: 0.2304 0.1969 0.2079 | HAC p 6/9 lags: 0.2205 0.2171
course walk_forward test absolute: HC0 joint p 0.2512, its size under the null 0.073, calibrated p 0.3087 | DM p 0.6274, t-reference size 0.045 | top-5 days 0.22 of sum (d - mean)^2 | CBB p 5/10/20: 0.5802 0.5602 0.5912 | HAC p 6/9 lags: 0.5682 0.5727
course walk_forward oos squared: HC0 joint p 0.0056, its size under the null 0.491, calibrated p 0.3357 | DM p 0.1813, t-reference size 0.044 | top-5 days 0.74 of sum (d - mean)^2 | CBB p 5/10/20: 0.1579 0.0655 0.0295 | HAC p 6/9 lags: 0.1046 0.0660
course walk_forward oos absolute: HC0 joint p 0.3774, its size under the null 0.124, calibrated p 0.5075 | DM p 0.0242, t-reference size 0.048 | top-5 days 0.22 of sum (d - mean)^2 | CBB p 5/10/20: 0.0195 0.0085 0.0065 | HAC p 6/9 lags: 0.0165 0.0131
```

**`t_crossover.py`** (added in the third review pass; concept note 11). Run from the repo root:
`uv run python t_crossover.py`.

```python
# From what level is the variance-matched t interval wider than the normal one? And is milestone 3's
# fitted t (location-scale) the variance-matched t, or only its df?
# Usage: uv run python t_crossover.py (from the repo root)
import math
from pathlib import Path
from scipy import optimize, stats
from arima_forecasting.artifacts import read_artifact
D = Path("app/public/data")
for mid in ("aic", "bic", "course"):
    fit = read_artifact(D, f"residuals_{mid}")["data"]["t_fit"]
    df = fit["df"]; scale = math.sqrt((df - 2) / df)
    def k(level): return float(stats.t.ppf(0.5 + level / 2, df)) * scale
    def z(level): return float(stats.norm.ppf(0.5 + level / 2))
    cross = optimize.brentq(lambda level: k(level) - z(level), 0.9, 0.999)
    print(f"{mid}: df {df:.4f}; the t interval equals the normal's at level {cross:.4f}; 95%: {k(0.95):.3f} vs {z(0.95):.3f} sd; 99%: {k(0.99):.3f} vs {z(0.99):.3f}; 99.9%: {k(0.999):.3f} vs {z(0.999):.3f}"
          f" | fitted t: loc {fit['loc']:.4f}, scale {fit['scale']:.4f} (variance-matching {scale:.4f}), variance {fit['scale'] ** 2 * df / (df - 2):.4f}")
```

Output on 2026-10-30, from the committed files:

```text
aic: df 3.4070; the t interval equals the normal's at level 0.9568; 95%: 1.914 vs 1.960 sd; 99%: 3.342 vs 2.576; 99.9%: 6.812 vs 3.291 | fitted t: loc 0.0292, scale 0.6817 (variance-matching 0.6426), variance 1.1253
bic: df 3.3738; the t interval equals the normal's at level 0.9573; 95%: 1.909 vs 1.960 sd; 99%: 3.346 vs 2.576; 99.9%: 6.860 vs 3.291 | fitted t: loc 0.0745, scale 0.6768 (variance-matching 0.6381), variance 1.1251
course: df 3.2392; the t interval equals the normal's at level 0.9595; 95%: 1.889 vs 1.960 sd; 99%: 3.360 vs 2.576; 99.9%: 7.066 vs 3.291 | fitted t: loc 0.0751, scale 0.6623 (variance-matching 0.6185), variance 1.1466
```

## Mutation testing

A *mutant* is a deliberately broken copy of the code. A test that fails *kills* it. Each mutant was
applied to a scratch copy of the working tree by a harness that makes one textual change (the
changed text must occur exactly once), runs the named tests, and restores the file. The working
tree itself was never mutated.

**Every mutant below was killed.** The first run: 22 Python mutants and 20 app mutants. The review fix round re-ran the Python ones (less P4, whose function was removed) with R1 to R11 on the revised code: 32 of 32 killed, baseline `709 passed`. The second review pass's fixes added S1 to S6, run on the final code: 6 of 6 killed, baseline `713 passed` (S6 against its export-tool test). The app's fix-round mutants are listed after its table. The third review pass's 56 mutants (32 Python, 24 app), all killed, are listed in its own section below.

**Python.** Run against the unit tests only: `tests/test_forecasting.py`, `tests/test_evaluation.py`,
`tests/test_payloads_forecast.py` and `tests/test_payload_corpus.py`. Baseline on the unchanged copy:
`695 passed in 7.47s` (694 after the review fix round removed the dead `random_walk_one_step` and its
test, P4 below). They were not run against `tests/test_committed_artifacts.py`, which compares
the committed files with a rebuild; see the note after the table for which mutants that test would
also catch.

| # | File | Mutation | Result | What fails |
|---|---|---|---|---|
| P1 | `forecasting.py` | `mean_usd` written as the median exp(μ) | 7 failed | `test_the_dollar_values_of_one_row_by_hand`, `test_the_mean_is_the_mean_of_the_price_and_the_median_its_median`, the payload-shape tests, `test_the_back_transform_gap_is_mean_over_median` |
| P2 | `forecasting.py` | the walk-forward reads one day ahead | 6 failed | `test_the_single_filter_pass_equals_the_append_loop` (both), `test_no_walk_forward_forecast_uses_its_own_day_or_a_later_one`, `test_no_refit_forecast_uses_its_own_day_or_a_later_one`, the extend test, the random-walk-model test |
| P3 | `evaluation.py` | the one-step random walk uses today's value | 1 failed, 4 errors | `test_the_random_walk_forecasts_of_a_window_by_hand` (the 4 errors: a `ZeroDivisionError` in the module fixture, where the random walk now forecasts the actual exactly) |
| P4 | `forecasting.py` | `random_walk_one_step` offset by one | 1 failed | `test_the_random_walk_by_hand`. After this run the function and its test were removed: the export never called it (next note), and the random walk the evaluation uses is `evaluation.random_walk_forecasts`, whose offset is P3 |
| P5 | `evaluation.py` | DM without the HLN correction | 3 failed | `test_dm_by_hand_on_made_up_errors`, `test_dm_with_the_hln_correction_is_the_one_sample_t_test_at_h_1`, `test_the_evaluation_passes_both_python_readers` |
| P6 | `evaluation.py` | γ₀ with divisor n − 1 | 3 failed | the same three |
| P7 | `evaluation.py` | the p-value from the normal, not the t | 3 failed | the same three |
| P8 | `evaluation.py` | a bound counted as outside | 1 failed | `test_coverage_counts_a_bound_as_inside` |
| P9 | `evaluation.py` | the DM verdict keyed by the wrong sign | 1 failed | `test_the_dm_verdict_at_its_boundary` |
| P10 | `evaluation.py` | too narrow and too wide swapped | 2 failed | `test_the_coverage_verdict_at_its_boundary`, `test_the_evaluation_passes_both_python_readers` |
| P11 | `forecasting.py` | the t intervals not variance-matched (scale dropped) | 6 failed | `test_the_t_multipliers_give_the_t_the_forecast_variance`, the payload-shape tests, `test_the_t_quantile_check_holds_at_the_bounds_of_df` |
| P12 | `forecasting.py` | each refit sees its own block | 2 failed | `test_no_refit_forecast_uses_its_own_day_or_a_later_one`, `test_the_refit_schedule_and_its_first_block` |
| P13 | `evaluation.py` | the producer never says `same_as_rw` | 1 failed, 4 errors | `test_forecasts_that_are_the_random_walks_are_not_tested` (the 4 errors: a `ValueError` in the module fixture, whose bic model is the random walk) |
| V1 | `payloads.py` | no tie of `mean_usd` to exp(μ + s²/2) | 1 failed | `test_python_refuses_a_forecast_that_breaks_a_numeric_rule[the mean is the median]` |
| V2 | `payloads.py` | the DM p-value checked against the normal | 22 failed | `test_the_bases_are_valid`, the corpus's evaluation cases, and more |
| V3 | `payloads.py` | the HLN factor unchecked | 1 failed | `…[DM without the HLN correction (factor 1)]` |
| V4 | `payloads.py` | the coverage count not recomputed | 2 failed | `…[a coverage count off by one]`, `test_a_coverage_count_uses_the_closed_interval_of_the_file_multipliers` |
| V5 | `payloads.py` | Kupiec's LR unchecked | 1 failed | `…[a Kupiec LR that is not the formula]` |
| V6 | `payloads.py` | the `same_as_rw` tolerance unchecked | 1 failed | `…[same_as_rw for forecasts that differ]` |
| V7 | `payloads.py` | a static `sd_log` may fall | 1 failed | `…[a static path's sd_log falls]` |
| V8 | `payloads.py` | the ratio not tied to metric / random walk | 1 failed | `…[a ratio that is not metric / random walk]` |
| V9 | `payloads.py` | the t quantile's CDF unchecked | 1 failed | `…[a t quantile that is the normal's]` |
| R1 | `payloads.py` | `_close` accepts a value that is not finite | 1 failed | `test_a_dollar_value_cannot_hide_behind_an_overflow` |
| R2 | `payloads.py` | no tie of the windows across forecast files | 1 failed | `test_every_forecast_file_must_describe_the_same_days_and_actuals` |
| R3 | `payloads.py` | no tie of the forecasts to `prices.json` | 1 failed | `test_the_forecasts_must_be_the_rows_of_prices` |
| R4 | `payloads.py` | the cross-file check re-raises an arithmetic error | 2 failed | `test_the_cross_file_check_reports_instead_of_raising` (both cases) |
| R5 | `payloads.py` | warning lists unbounded | 3 failed | `test_a_warnings_list_is_bounded_before_it_is_walked` and the corpus's 101-warning cases |
| R6 | `payloads.py` | the beta function without its df guard | 1 failed | `test_the_t_tail_of_a_degenerate_df_is_nan_not_an_error` |
| R7 | `payloads.py` | the DM verdict check rejects at p = alpha | 1 failed | `test_a_dm_p_value_equal_to_alpha_is_not_a_rejection` |
| R8 | `payloads.py` | the coverage verdict check rejects at p = alpha | 1 failed | `test_a_coverage_p_value_equal_to_alpha_is_consistent` |
| R9 | `payloads.py` | the refit `n_obs` step unchecked | 1 failed | `test_each_refit_is_fitted_on_21_more_days_than_the_one_before` |
| R10 | `payloads.py` | the refit parameter names not tied to the fit | 1 failed | `test_a_refit_must_name_its_parameters_as_the_fit_does`. Later removed with the rule: the second review pass showed no valid file can reach it |
| R11 | `forecasting.py` | the static oos path built from the end of training | 1 failed | `test_a_forecast_payload_passes_the_reader_and_has_its_shape[static]` |
| S1 | `payloads.py` | the evaluation's model labels not tied to the forecast files | 1 failed | `test_each_model_label_in_the_evaluation_is_its_forecast_files` |
| S2 | `payloads.py` | the same-state ties off | 3 failed | `test_forecasts_from_the_same_state_must_be_the_same_numbers` (all three) |
| S3 | `payloads.py` | the static first day not tied (the refit still is) | 2 failed | the two static cases of the same test |
| S4 | `payloads.py` | `_same_windows` ignores the origin | 2 failed | `test_the_origin_is_tied_across_files_and_to_prices`, and one more |
| S5 | `payloads.py` | the prices check skips a missing file | 1 failed | `test_the_origin_is_tied_across_files_and_to_prices` |
| S6 | `export_app_data.py` | the tool does not run the prices check | 1 failed | `test_the_tool_checks_the_forecasts_against_prices_before_writing` |

**What `test_committed_artifacts.py` adds, measured.** The 13 producer mutants (P1 to P13) were also
run against its milestone-4 tests alone (`-k "forecast or refit or evaluation"`, 21 tests; baseline
`21 passed in 3.11s`; the copy's source files matched their hashes afterwards). It kills 9: P1, P2, P3, P5, P6, P7, P9, P10 and P11, each of which changes a number or a
verdict in a committed file. It does not kill 4, and each has a reason in the data or the test:

- **P4**: `forecasting.random_walk_one_step` was not used by the export (the evaluation has its own
  `random_walk_forecasts`), so no committed file changed. Found this way, it was dead code, and it
  is now removed.
- **P8**: no AAPL actual lies exactly on an interval bound, so the counts do not change.
- **P12**: the sampled-refit test (`tests/test_committed_artifacts.py:295`) refits each block with
  its own `fit` call from the committed estimates, not through `refit_walk_forward`.
- **P13**: no AAPL model's forecasts are the random walk's, so no row says `same_as_rw`.

So the committed-artifacts test proves the committed files equal what the current code makes from
the committed inputs; it does not prove the code is right, and it cannot see a fault that does not
change these particular files. The unit tests are what kill those four.

**App** (`npx vitest run` on a scratch copy of `app/`, run 2, after the `same_as_rw` change; 1401
tests; each mutant restored afterwards):

| Mutant | File | Mutation | Result | What fails |
|---|---|---|---|---|
| `m4-dm-reading-swapped` | `ForecastView.tsx` | the "worse" reading shown for a "beats" verdict | 1 failed | "reads each DM row by its own exported verdict, with one verdict flipped at a time" |
| `m4-coverage-reading-wrong-key` | `ForecastView.tsx` | every coverage row read by the first row's verdict | 1 failed | "reads each coverage row by its own exported verdict, …" |
| `m4-level-not-pinned` | `contract.forecast.ts` | a pinned list compared by length only | 9 failed | the pin tests of both parsers and corpus cases |
| `m4-refit-count-unchecked` | `contract.forecast.ts` | a refit list shorter than expected accepted | 2 failed | the refit bookkeeping test and a corpus case |
| `m4-animation-autoplays` | `ForecastView.tsx` | the animation starts playing | 4 failed | the walk-forward animation tests |
| `m4-reduced-motion-ignored` | `ForecastView.tsx` | the timer runs under reduced motion | 1 failed | "stops a walk that is playing when the reader asks for reduced motion" |
| `m4-dm-shown-for-static` | `ForecastView.tsx` | the DM table drawn for a static path | 1 failed | "does not run the DM test for the static method, …" |
| `m4-refit-offered-everywhere` | `ForecastView.tsx` | every method offered for every model | 1 failed | "offers the refit only where evaluation.json lists it: the AIC model" |
| `m4-sd-log-zero-accepted` | `contract.forecast.ts` | `sd_log` of 0 accepted | 2 failed | "refuses a forecast with no spread, …" and a corpus case |
| `m4-legend-mark-unsized` | `ForecastView.tsx` | the legend icons lose their size | 1 failed | "gives the chart, the animation and every legend mark an explicit size, …" |
| `m4-rows-read-past-max` | `contract.forecast.ts` | no `MAX_ROWS` bound | 3 failed | the bound tests of both parsers and a corpus case |
| `m4-coverage-nulls-flipped` | `contract.forecast.ts` | the static and one-step null rules swapped | 56 failed | the integration, loading, parser, real-data, corpus and view tests |
| `m4-reader-quotes-whole-array` | `contract.reader.ts` | `shown` quotes a whole array | 3 failed | the short-message tests |
| `m4-refit-start-date-unchecked` | `contract.forecast.ts` | a refit's start date not checked against its row | 2 failed | the refit bookkeeping test and a corpus case |
| `m4-test-before-oos-unchecked` | `contract.forecast.ts` | equal test end and oos start accepted | 2 failed | the date test and a corpus case |
| `m4-same-as-rw-nulls-unchecked` | `contract.forecast.ts` | a `same_as_rw` row with a statistic accepted | 3 failed | "reads a model that is the random walk as same_as_rw, …" and corpus cases |
| `m4-same-tolerance-not-pinned` | `contract.forecast.ts` | `same_tolerance` read from the file | 3 failed | the pin test and corpus cases ("same_tolerance 1e-8") |
| `m4-max-gap-negative-accepted` | `contract.forecast.ts` | a negative `max_forecast_gap` accepted | 2 failed | the `same_as_rw` parser test and a corpus case |
| `m4-same-as-rw-reading-wrong` | `ForecastView.tsx` | `same_as_rw` read as "no difference" | 2 failed | the DM reading test and "shows a dash for the statistic and p-value of a model that is the random walk, …" |
| `m4-log-axis-ignored` | `ForecastView.tsx` | the log axis never used | 1 failed | "places the prices on a log axis when asked, with ticks at round dollar values" |

---

**App, review fix round** (run 3: the 20 above on the revised code and 13 new; 1,413 tests in the
scratch copies, where the two 3D scene test files cannot load through the symlinked font path, as in
milestone 3's runs). All 33 killed. The new ones:

| Mutant | File | Mutation | Result |
|---|---|---|---|
| `r-refit-warnings-unbounded` | `contract.forecast.ts` | refit warning lists walked without the bound | 2 failed |
| `r-fit-warnings-unbounded` | `contract.fit.ts` | fit warning lists walked without the bound | 2 failed |
| `r-kind-against-file-name` | `contract.forecast.ts` | `kind` checked against the file name's method, not the payload's | 3 failed |
| `r-metrics-test-window`, `r-metrics-walk-forward` | `ForecastView.tsx` | the metrics table always on the test window, or the walk-forward rows | 3 failed each |
| `r-rw-test-window` | `ForecastView.tsx` | the random walk's row always the test window's | 3 failed |
| `r-dm-test-window`, `r-dm-walk-forward` | `ForecastView.tsx` | the DM rows always the test window's, or the walk-forward's | 2 and 1 failed |
| `r-coverage-test-window`, `r-coverage-walk-forward` | `ForecastView.tsx` | the coverage rows likewise | 3 failed each |
| `r-legend-80-95-swapped` | `ForecastView.tsx` | the 80% and 95% legend labels swapped | 1 failed |
| `r-status-always-live` | `ForecastView.tsx` | the status line live while playing | 1 failed |
| `r-play-aria-pressed-back` | `ForecastView.tsx` | `aria-pressed` back on the Play button | 2 failed |


## Gate results

**After the third review pass**, on 2026-10-30, on the final code; the machine was loaded by this
pass's mutant runs during the full-tree Python suite and `--check`. The fresh clone is `git clone`
of HEAD with the working tree copied over it.

| Gate | Command | Full tree | Fresh clone |
|---|---|---|---|
| Python tests | `uv run pytest -q` | `1937 passed in 759.57s` | `1936 passed, 1 skipped in 619.02s` (the skip: `test_config.py:224`, the clone's folder is named `fresh`) |
| App gate | `cd app && npm run verify` | lint clean; `48 passed` files, `1534 passed` tests; coverage 96.94% statements, 93.42% branches, 99.62% functions, 99.42% lines; built; 25.3 s | lint clean; the same counts and coverage; built; 12.0 s |
| Notebook sync | `uv run python tools/build_notebooks.py --check` | `notebooks are in sync` | `notebooks are in sync` |
| Full export | `VOL_DATA_DIR=$PWD/data /usr/bin/time -v uv run python tools/export_app_data.py` | exit 0, 357.6 s wall (5:57.63); all 18 files' `data` identical to the files before it (only `generated_at` changed): the pins and ties of this pass change no payload | not run |
| Export check | `VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py --check` | `app data is current` for all 18 artifacts, 552.3 s wall (9:12.28), the family check on the rebuild included | without a snapshot: exit 2, "no complete snapshot" (no `data/` in a clone, as designed); with `VOL_DATA_DIR` pointed at the full tree's `data/`: `app data is current` for all 18 artifacts, 360.3 s |
| Cite script | `check_cites.py` on every doc this pass changed | `problems: 0` for this walkthrough (161 cites), concept notes 10 and 11, ADR-0003, LEARNING_LOG and the milestone-1 to 3 walkthroughs; the milestone-0 walkthrough 3, concept note 01 one and `contract.md` 4, the same as at HEAD (cites into installed packages, and one past the end of `AicAxesPreview.tsx`) | not run separately (same text) |

**After the second review pass**, on 2026-10-30, on that pass's code. The fresh clone is `git clone` of
HEAD with the working tree copied over it (tracked and untracked files no ignore rule covers), in the
session's scratch folder; it has no `data/`, so no snapshot.

| Gate | Command | Full tree | Fresh clone |
|---|---|---|---|
| Python tests | `uv run pytest -q` | `1810 passed in 372.43s` | `1809 passed, 1 skipped in 963.08s` (the skip: `test_config.py:224`, the clone's folder is named `fresh`) |
| App gate | `cd app && npm run verify` | lint clean; `48 passed` files, `1423 passed` tests; coverage 96.56% statements, 92.28% branches, 99.43% functions, 99.49% lines; built | the same counts and coverage; built |
| Notebook sync | `uv run python tools/build_notebooks.py --check` | `notebooks are in sync` | `notebooks are in sync` |
| Export check | `VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py --check` | `app data is current` for all 18 artifacts, 565.75 s wall (run after the first fix round's code; the second pass changed only cross-file checks, tests and docs, not what is exported) | exit 2, "no complete snapshot" (no `data/` in a clone, as designed) |
| Real-data parse | `npx vitest run src/lib/contract.realdata.test.ts` | in `npm run verify` | every file passes (in the script's output) |
| Cite script | `check_cites.py` on this walkthrough | `problems: 0`, 158 cites, each printed line read against the text | not run separately (same text) |

---

## Review fix round

An adversarial review attacked 14 claims. Nine survived (no look-ahead, the random walk, the dollar
values, the t intervals, the course's two failures, the committed files, the timings kept out of JSON,
most of the DM and coverage claims). It refuted three and found defects beside them. Each was
reproduced here before it was fixed, and each fix has a test that fails without it (mutants R1 to
R11 below).

| Found | How it showed | Fixed by |
|---|---|---|
| A recomputed value of inf matched any number | A row with `mean_log` 710 (exp overflows) and `median_usd` $183.18 passed every Python check: `_close` tested `abs(a - inf) <= rel * inf`, which is true | `_close` and `_near` refuse a value that is not finite on either side; `test_a_dollar_value_cannot_hide_behind_an_overflow` |
| Nothing tied the seven files' actuals to each other or to `prices.json` | BIC's oos actuals moved one day earlier, the evaluation rebuilt from them: every Python check passed, and `--only prices` after a new snapshot would have kept stale forecasts | `_same_windows` in `validate_forecast_evaluation`, and `validate_forecast_prices`, which the export tool now runs with `prices.json`; two tests |
| The cross-file check raised | `mean_log` −800 with `sd_log` 40 raised `OverflowError`; an actual of exp(−800) = $0 raised `ZeroDivisionError` under MAPE, against the docstring's "never raises" | arithmetic errors are reported as problems; `test_the_cross_file_check_reports_instead_of_raising` |
| Warning lists had no bound | 3.3 million warnings in a refit (a 9.9 MB file) gave 324 MB of messages in both readers | `MAX_WARNINGS` = 100 in both readers, checked before the list is walked, for the forecast refits and `fit`'s lists; corpus cases at 100 and 101 |
| Two alpha boundaries were untested in the validator | `p <= ALPHA` in the DM verdict check and `p > ALPHA` in the coverage one both passed every test | `test_a_dm_p_value_equal_to_alpha_is_not_a_rejection`, `test_a_coverage_p_value_equal_to_alpha_is_consistent` |
| Three rules had no Python test | the static oos path built from the end of training, the refit `n_obs` step, and the refit parameter names against the fit each passed the unit tests | a payload-level test of the static oos origin, and one test each for the other two |
| The corpus harness only asserted "some problem" | a case could pass because another rule refused it | each milestone-4 invalid case names the path(s) of its rule, and both harnesses require every problem to be there |
| View tests saw only the aic test window | the tables always showing the test window or the walk-forward row, and the 80% and 95% legend labels swapped, passed 1,401 tests | view tests on the oos window, the refit method and the other models, and on the legend labels |
| The status line was live and changed every 40 ms during play; Play swapped its label and set `aria-pressed` | read in `ForecastView.tsx` | the status line is `aria-live="off"` while playing and `"polite"` otherwise, so a step announces its day; Play swaps its label only. Pausing changes no text, so it announces nothing; whether a screen reader announces the last day, where the text and the attribute change in one render, is not verified (no screen reader was run) |
| Two causes asserted without a separating probe | concept note 11 called the oos over-coverage "the shape" (fat tails), and this walkthrough and note 10 called the lag-1 autocorrelation of d "at least partly the heavy tails" | probe 3 (`ewma_probe.py`): a trailing rescale halves the oos excess kurtosis (10.65 to 6.80 for aic), and the over-coverage survives it. The autocorrelation claim was first rewritten as "weak evidence", which the second pass refuted (next table); the third pass withdrew the second pass's reading in turn (probe 5) |
| Smaller errors | the expected number of false DM rejections (0.8 whatever the dependence, not "more if independent"); the t's infinite mean of exp(X) not mentioned; the mutant baseline 695 vs 694; "covers fewer days" where some counts are equal; 0.017% for the course model's 0.0177% | corrected in concept notes 10 and 11 and in this walkthrough |
| Dead code | `forecasting.random_walk_one_step` and `random_walk_static` were never called by the export (found by the doc pass's mutant P4) | removed with their test |
| `_t_sf(1.0, 5e-324)` raised | lgamma of a half-df that underflows to 0 | `_betainc` returns nan for such a df; unreachable from a file (df ≥ 1) |

**Second review pass.** A second adversarial review attacked the fixes. It confirmed the first
pass's holes closed (its probes re-run: inf refused, shifted actuals caught, no raise in 255 fuzzed
file sets) and found these, each reproduced here and fixed or stated:

| Found | How it showed | Fixed by |
|---|---|---|
| The autocorrelation of d is real for two rows | A White-robust joint test of lags 1 to 5 rejects for the oos squared loss of bic (p 0.0008) and the course model (p 0.0056); "weak evidence" came from testing lag 1 alone | probe 4 (`white_joint.py`) and the corrected text in DM assumptions and concept note 10; the h = 1 test is mis-specified there, which meets ADR-0003's revisit condition: an owner decision (What is next). **Withdrawn in the third review pass**: that White test rejects 38% and 49% of the time under a sign-flip null with no autocorrelation (probe 5) |
| Wrong pairs still passed the family check | evaluation's model labels swapped; a static path shifted; the refit's first block moved: each passed every check the export tool runs (`--check` and the committed-artifacts rebuild catch them) | `validate_forecast_evaluation` ties each model's label to its forecast files, each static path's first day and the refit's first 21 days to the walk-forward's (same state, same parameters); `test_each_model_label_in_the_evaluation_is_its_forecast_files`, `test_forecasts_from_the_same_state_must_be_the_same_numbers` |
| The origin half of the new ties had no test | mutants dropping the origin from `_same_windows` or from the prices check left every test passing | `test_the_origin_is_tied_across_files_and_to_prices`; the tool's call to `validate_forecast_prices`, `test_the_tool_checks_the_forecasts_against_prices_before_writing` |
| A rule no valid file can reach | `validate_forecast_fit`'s refit parameter-name loop: each file's names already follow its order and trend, tied to the fit's | removed, with its test (mutant R10 is gone) |
| `validate_forecast_prices` skipped a missing file | the other cross-file checks report one | it reports it |
| The export tool read `prices.json` first | a folder with `fit.json` and no residual files got "prices.json does not exist" instead of naming the residual file (`test_only_meta_into_a_folder_without_fit_files_writes_meta_as_before` failed) | the family is read first, `prices.json` last |

Found and not changed then, for the owner: `aic_grid`'s cell and run warning lists (milestone 2) were walked
without a bound in both readers (one cell with a million empty warnings gave Python 2,000,000 problems, 94.8 MB of text, measured); the other
fit-file lists of milestone 3 were bounded only through their orders; and swapping the walk-forward
trail's 80% and 95% data passed the view tests. The third review pass fixed all three (below). A screen reader was not run.

Not changed, and why: a one-day test window makes the producer refuse (a DM row needs two forecasts),
which no real window reaches; the review measured two-row windows, a model equal to the random walk
and refits on a window boundary end to end, and they pass.

**Third review pass.** Two more adversarial reviews, one of the statistics and one of the code,
contract and app, re-ran every number and attacked the readers with probes and mutants. Each finding
was reproduced here before it was fixed, and each fix has a test that fails on its own mutant (the
table after this one).

| Found | How it showed | Fixed by |
|---|---|---|
| "Robustly autocorrelated" rested on a test that is not | The White (HC0) joint test of five lags rejects at nominal 5% in 38% (bic) and 49% (course) of draws under a sign-flip null with no autocorrelation; calibrated, its p of 0.0008 and 0.0056 are 0.15 and 0.34 | the claim withdrawn here (probe 5), in concept note 10, ADR-0003 ("Revisit when": not met) and LEARNING_LOG; `signflip_bootstrap.py` replaces `white_joint.py`. Restated: the γ̂₀ test is correctly sized (4.0% to 5.7% under the null); every oos squared-loss verdict is borderline; the absolute-loss ones are robust. Default, overridable: no Newey–West DM in the contract |
| "Only BIC's squared-loss verdict depends on it" | This walkthrough's own table: at 9 lags the AIC model's p is 0.0229 and the AIC refit's 0.0387 | corrected wherever it was said (probe 5's tables) |
| The t interval "wider only at 99.9%" | It is wider from 95.68% up; at 99%, 3.34 against 2.58 standard deviations | concept note 11, with `t_crossover.py`; the note also says the milestone-3 t fit is location-scale (variance 1.125), so only its df is reused |
| Smaller errors | concept note 10 called every DM row's parameters fixed (the four refit rows re-estimate them); item 15 called an n − k divisor Newey–West; no milestone-4 doc said the dollars are dividend-adjusted closes; ADR-0003 said the course's MAPE prints NaN, but module 9 raises first; a cite pointed at the line that ties the DM nulls instead of the tolerance pin | each corrected in its doc |
| `aic_grid`'s lists unbounded (milestone 2), and many more | The review measured a 6 MB grid with 2,000,000 warnings in one cell: 2,000,000 problems and about 120 MB of text in each reader. A sweep here of every array of every base payload (314 paths; each list replaced by 200,000 copies of its first item, of 0 or of {}, in both readers, a time limit on each) flagged 169 cases across milestones 1 to 3: 200,000 warnings in one grid cell gave 200,000 problems (11.7 MB of text in Python, 12.3 MB in the app), 200,000 copies of a fit model took 9.5 s and 10.8 s, and the price, decomposition, residual and correlogram rows, the KDEs and their points, meta's lists and the fit's and grid's other lists were walked likewise; the app quoted a 200,000-item order whole (400 kB) | every list bounded before it is walked, in both readers, with the same message ("Bounds" in `contract.md`); TS messages quote through `shown`; 73 `size_cases` in the shared corpus (one past each bound, at it, and 2,000,000 grid items in under a second). The sweep afterwards: 0 of 314 flagged |
| Window boundaries pinned nowhere | Both readers accepted made-up windows anywhere in time; the Method picker showed free text from the file | the out-of-sample window (meta, `prices` splits) and the train fraction pinned in both readers; the forecast windows tied to `prices.json`'s splits across files (Python); the method labels pinned per id. Defaults recorded in LEARNING_LOG |
| A consistent wrong file passed every check | The review's probe: bic's one-step `sd_log` times 1.5, its dollars and the evaluation rebuilt, 0 problems (re-run here after the fix: 2, one per window) | each one-step row's `sd_log`² tied to its parameters' `sigma2` (fit's, or the refit's own) at `SIGMA2_REL` = 1e-4 (below). The same family with a look-ahead `mean_log` still passes every reader, as no reader can tell when a forecast was made; `contract.md` says so, and `--check` and the tests catch it |
| `validate_forecast_evaluation` raised; `--check` skipped the family check; `_t_sf` wrong past df 1e7 | 241 raises (AttributeError, IndexError) in 9,107 payloads with one node retyped; `--check` returned before the cross-file check; `_t_sf` is off by 1.2e-9 at df 10⁷ and by a factor of 3 at 2⁵³ | a file invalid on its own is named and left out of the cross-file checks (0 raises in the same 9,107); `--check` runs the family check on the rebuild; a DM df past `MAX_ROWS` − 1 is never given to `_t_sf` (reachable only when the windows are already refused) |
| Reduced motion turned off resumed a walk | The review's headless Chromium: a walk paused by reduced motion at day 15 was at day 39 a second after it was turned off, with no click | reduced motion ends the play; the walk stays paused until Play (a view test). Re-run in headless Chromium on a build of this code: day 15 when reduced motion came on, 15 a second later, 15 a second after it went off, Play enabled and no Pause button; day 35 after Play was pressed |
| Mutants that survived | Python tolerances loosened to 1e-3 or 1e-4 (S20 to S37); the view's trail and bars with 80% and 95% swapped, the mean line from the median, the walk's dots, its y range, the coverage tones, and a late fetch written under the current pick (T0 to T30) | a test per tolerance just past it and just inside it (the tolerances written as literals, so a loosened constant cannot move the test); view tests that check the walk-forward chart's marks against the fan chart's own coordinates; a race test |
| Corpus gaps | no walk-forward base; a test held the real AIC t df | the base `forecast_aic_walk_forward` with 10 cases; a made-up df |

**Why `SIGMA2_REL` is 1e-4.** A one-step variance is the Kalman filter's F_t, which for these models
settles at `sigma2`. statsmodels stops updating the state covariance once it changes by less than
1e-19 in a step, which leaves F_t a constant fraction above `sigma2`; turning that switch off
removes it. Measured on the committed files (`variance_excess.py`, below): 2.67e-5 (bic), 2.38e-7
(course), 5.7e-14 (aic). The tolerance is about four times the largest.

```python
# How far is each one-step forecast variance above its model's sigma2, and why? statsmodels' Kalman
# filter stops updating the state covariance once it changes by less than `tolerance` (1e-19) in a
# step; with the switch off (tolerance 0) it keeps converging. Usage: OPENBLAS_NUM_THREADS=1 uv run python variance_excess.py
from pathlib import Path
import numpy as np
from arima_forecasting.artifacts import read_artifact, table_from_prices
from arima_forecasting.forecasting import spec_from_fit, windows
D = Path("app/public/data")
fit = read_artifact(D, "fit")["data"]
y = table_from_prices(read_artifact(D, "prices")["data"])["log_close"].to_numpy(float)
test, oos = windows(table_from_prices(read_artifact(D, "prices")["data"]))
for m in fit["models"]:
    spec = spec_from_fit(m)
    sigma2 = spec.params[-1]
    exported = [r["sd_log"] ** 2 / sigma2 - 1 for w in read_artifact(D, f"forecast_{m['id']}_walk_forward")["data"]["windows"] for r in w["rows"]]
    out = [f"{m['id']}: exported sd_log^2 / sigma2 - 1 from {min(exported):.3e} to {max(exported):.3e}"]
    for tolerance in (None, 0.0):
        model = spec.model(y[:oos.stop])
        if tolerance is not None:
            model.ssm.tolerance = tolerance
        v = np.asarray(model.filter(spec.params).get_prediction(start=test.start, end=oos.stop - 1).var_pred_mean) / sigma2 - 1
        out.append(f"tolerance {model.ssm.tolerance}: {v.min():.3e} to {v.max():.3e}")
    print(" | ".join(out))
```

Output on 2026-10-30, from the committed files:

```text
aic: exported sd_log^2 / sigma2 - 1 from -1.987e-14 to 5.729e-14 | tolerance 1e-19: -1.998e-14 to 5.707e-14 | tolerance 0.0: -1.998e-14 to 5.707e-14
bic: exported sd_log^2 / sigma2 - 1 from 2.668e-05 to 2.668e-05 | tolerance 1e-19: 2.668e-05 to 2.668e-05 | tolerance 0.0: -3.031e-14 to -2.409e-14
course: exported sd_log^2 / sigma2 - 1 from 2.382e-07 to 2.382e-07 | tolerance 1e-19: 2.382e-07 to 2.382e-07 | tolerance 0.0: 0.000e+00 to 0.000e+00
```

**Third-pass mutants.** Run by a harness that copies the tree to scratch, checks that the named tests
pass on the unmutated copy, applies one change (its text must occur once), runs the tests, restores
the file and checks its hash. Every one was killed, on the final code: 32 Python and 24 app.

| # | File | Mutation | Result |
|---|---|---|---|
| R4a, R4b | `payloads.py` | a forecast file, or the evaluation, invalid on its own still checked across files | killed (4 and 2 tests) |
| R4c | `export_app_data.py` | `--check` without the family check | killed |
| R4d, R4e | `payloads.py` | no df bound before `_t_sf`; the bound one too low | killed |
| S20, S21, S22, S23, S24c, S33, S37 | `payloads.py` | the static sd fall, RMSE ≥ MAE, HLN factor, t CDF, p-value, p = 0 and same-state tolerances loosened (the review's survivors) | killed |
| R3a to R3d | `payloads.py` | no `sigma2` tie; `SIGMA2_REL` 1e-3; the refit's later rows tied to the fit's `sigma2`; the tie one-sided | killed |
| R1p1 to R1p8 | `payloads.py` | grid cells and cell warnings unbounded; `MAX_GRID_CELLS` + 1; `MAX_NAMES` 99; `_list` never refuses; residual rows unbounded; a long `params` object walked; `MAX_LIST` 10,001 | killed |
| R2p1 to R2p8 | `payloads.py` | the train fraction, oos split, oos end, test end, meta window and method label pins dropped or loosened; no tie to `prices.json`'s splits; the origin tied to the window's own segment | killed |
| T0, T1, T17, T20, T22, T23, T24, T30 | `ForecastView.tsx`, `useForecastData.ts` | the review's eight app survivors | killed |
| R5a | `ForecastView.tsx` | reduced motion pauses only the timer | killed |
| R1t1 to R1t9 | `contract.order.ts`, `contract.fit.ts`, `contract.ts`, `contract.reader.ts` | the app's side of the bounds, and messages quoting whole values | killed |
| R2t1 to R2t6 | `contract.payloads.ts`, `contract.ts`, `contract.forecast.ts` | the app's side of the pins | killed |

Found and not changed: two cites in the milestone-0 walkthrough and three in the milestone-2 one into
`tools/export_app_data.py` point at lines that had already moved before this pass (they are as they
were at HEAD), and one milestone-0 cite runs past the end of `AicAxesPreview.tsx`; the course window
is not pinned (only the out-of-sample window and the train fraction are); a screen reader was not run.

## Explain it back

Answer out loud or on paper, without notes. Name files, lines and functions.

1. **The data flow.** Follow the AIC model's one-step forecast of 2024-01-02 from `fit.json` to the
   animation: `spec_from_fit`, `walk_forward`, `forecast_rows`, `evaluation_payload`, `dm_test`,
   `coverage`, the export tool's family check, `useForecastFile`, `parseForecast`, `WalkForward`.
   Name every check that could stop it, in Python and in the app. Was that day inside the normal
   95% band? The t 95% band? Why can the two differ?
2. **One pass or a loop.** Why does one filter pass give the same one-step forecasts as the loop
   that appends a day at a time? Why is the pass the one exported, and how does
   `tests/test_forecasting.py` prove that no forecast sees its own day? Why not loop with
   `extend()`?
3. **The static baseline.** Why does any path with a drift beat a flat line in a rising market? What
   probe shows that the AIC model's static advantage is its drift, and what do its seven AR and MA
   coefficients add to the static path?
4. **Diebold–Mariano at h = 1.** Show that DM with the HLN factor is the one-sample t test of the loss
   differential. What does using γ₀ alone assume? What did Ljung–Box, the White regression and
   Newey–West find in the oos window, and why did the sign-flip null (probe 5) withdraw the White
   regression's verdict? Why are the squared-loss verdicts called borderline while the absolute-loss
   ones stand? What does the simulation's last row warn about?
5. **The random walk as a model.** Why would DM on an ARIMA(0, 1, 0) without a drift compute a
   statistic from nothing? Where is `SAME_TOLERANCE` set and pinned, which nulls go with
   `same_as_rw`, and which reader checks the gap against the tolerance?
6. **Coverage: scale or shape.** Why was every one-step interval too wide in 2023? Why was the normal
   80% interval too wide in oos while the t's was consistent? Which numbers in the probe separate
   the two causes, and what do they not show?
7. **Median and mean.** Which minimises expected squared error and which absolute error? Why is the
   gap 0.017% one step ahead and above 10% at the end of an oos static path? Why did the mean score
   worse on aic's oos path and better on bic's?
8. **The t intervals.** Why must ν be above 2? Why are the variance-matched t intervals narrower than
   the normal at 80% and 95%? What does Python's reader do with a t on 10⁶ degrees of freedom, and
   why not evaluate the t's CDF there?
9. **What a test proves.** What does `tests/test_committed_artifacts.py` prove, and what not? Which
   four producer mutants does it not catch, and why does each slip past?
10. **A trade-off.** The brief asked for one file per model and the timings in `evaluation.json`.
    Defend both deviations: what would each have cost the contract, `--check` and the reader of the
    page?

---

## Concepts used

- [10 · Forecast evaluation and Diebold–Mariano](../concepts/10-forecast-evaluation-and-diebold-mariano.md)
- [11 · The log-normal back-transform and interval coverage](../concepts/11-log-normal-back-transform-and-interval-coverage.md)
- From milestone 3: [08 · Residual diagnostics](../concepts/08-residual-diagnostics.md) (the fat
  tails and the volatility clustering that the intervals meet here) and
  [09 · Parameter inference and root cancellation](../concepts/09-parameter-inference-and-root-cancellation.md)
  (why the AIC model's coefficients are hard to read one by one).
- From milestone 0: [00 · Background](../concepts/00-background.md).

---

## What is next, and open decisions

**Milestone 5**, "where the sample goes wrong, and polish", collects the course's mistakes in one
place and measures what each one costs.

**Open, for the owner:**

- **Keep the BIC and course models on the page?** Neither beats the random walk one step ahead, and
  their static paths score as the flat line does. Beside them, the AIC model's extra parameters do
  not improve the one-step forecasts (dollar RMSE ratios 1.0118 and 1.0174 for aic, 1.0056 and
  1.0165 for bic, 1.0075 and 1.0085 for the course, test then oos). Keeping them shows that;
  dropping them would make the page simpler.
- **DM on log errors, or on dollars?** The code's reason for log errors (dollar errors scale with a
  price that moves a lot over oos) is stated in `evaluation.py`, not measured.
- **Report a Newey–West DM beside the HLN one, or test with h > 1 lags? Default taken (third review
  pass), overridable.** No Newey–West DM in the contract; the γ̂₀ HLN test stays the exported one, and
  the Newey–West and block-bootstrap checks stay in the docs (probe 5). The second pass's case for
  revisiting the test (a White-robust joint test, p 0.0008 and 0.0056) is withdrawn: that test rejects
  38% and 49% of the time under a sign-flip null with no autocorrelation, while the γ̂₀ test is
  correctly sized (4.0% to 5.7%). The squared-loss verdicts are borderline for every model, not only
  bic (p 0.023 for aic and 0.039 for the aic refit with Newey–West at 9 lags); the absolute-loss
  verdicts are robust. Adding a Newey–West row would change the contract and the page.
- **Numbers in the README before a verifier pass?** The headline results above have not yet been
  re-measured by a second agent or reviewed.
- **The log price axis default.** Linear by default, the course's view, with a log price axis on a
  checkbox; on its last oos day the AIC model's 95% static band spans $147.91 to $847.18, a factor
  of 5.7, so a log axis by default would show the band's
  shape better.
- **`MAX_ROWS` = 10,000.** Both readers refuse a window of more rows. The windows here have 227 and
  689; a longer out-of-sample window would need the bound raised.
- **`same_tolerance` = 1e-9 log points.** The real models' one-step forecasts are 0.0039 to 0.0169
  log points from the random walk's at their largest (`max_forecast_gap`), so the tolerance decides
  nothing on AAPL; it is a choice for models that are the random walk.
- **The refit's warm start.** Each refit starts from the previous block's estimates, so the 43
  refits follow one local maximum of the likelihood as the data grow. All 43 converged, in 2 to 54
  iterations, with no warnings. Whether a fresh start would find another maximum for some block is
  not measured; starting each refit from statsmodels' default, or from several starts as the grid
  does, is the alternative.
