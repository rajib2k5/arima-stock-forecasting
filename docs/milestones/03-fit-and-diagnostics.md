# Milestone 3: fit and diagnostics

Status: built, reviewed, and revised in a fix round. Reviewed by: two adversarial reviews (statistics;
code, contract and app) and the coordinator's check in a real browser. What they found wrong, and
what changed, is in [Review fix round](#review-fix-round).

This walkthrough covers course modules 7 and 8: fit the model, read its estimates, then ask whether
what it leaves over is white noise. Everything runs on the training segment, the first 90% of the
course window (ADR-0002, §1), except the one step of the course's recipe that does not: its order
search, which this milestone reproduces and measures. It explains what exists, why it is built this
way, and where each guard lives.

How to use it:

1. Read the sections up to "Pitfalls met".
2. Answer [Predict before you look](#predict-before-you-look) on paper.
3. Only then read [Measured results](#measured-results).
4. Read the two concept notes listed at the end.
5. Answer [Explain it back](#explain-it-back) without notes.

Every `file:line` reference is relative to the repository root and was checked by a script against
the final files. Every number was measured on 2026-10-29 with the command shown in
[Measured results](#measured-results), from the committed files in `app/public/data/` unless the
row says otherwise.

---

## What we built and why

Four new artifacts carry milestone 3 to the app under schema `1.4.0`. **`fit`** holds three models
fitted on the 2,037 training log closes, each with its estimates, standard errors, z, p-values and
95% intervals, its information criteria, its inverse AR and MA roots with the pairs that nearly
cancel, and its residual tests: Ljung–Box, Jarque–Bera and ARCH-LM, with a verdict for each. It also
holds `course_track`, the course's own recipe with its two problems measured, and
`clustering_prediction`, concept note 07's prediction tested. **`residuals_aic`**,
**`residuals_bic`** and **`residuals_course`** hold each model's residual series for the plots: the
standardised residuals over time, their ACF and the ACF of their squares with the white-noise band,
and a QQ plot against the normal and against a fitted Student-t. They are three files, not one,
because the three series together are 1,450,049 bytes, past the 1 MB budget.

The three models are the owner's default (LEARNING_LOG, "Decisions and defaults"): **aic**, ADR-0002's
choice, ARIMA(3, 1, 4) with a drift, the primary model; **bic**, BIC's choice, ARIMA(2, 1, 2) without
a drift; **course**, what the course's code gives, ARIMA(0, 1, 1) without a drift. The two grid
models are refitted from the estimates the grid recorded, so they are the grid's own points,
reproduced to 1e-6 in log-likelihood. That shows the point is reproduced, not that it is a maximum:
another optimiser started at the BIC choice's point climbs 1.27e-4 further.

The app has a new lazily loaded page, **Fit and diagnostics**: a model picker, the parameter table,
the inverse roots on the unit circle with the cancelling pairs ringed, the test table with a fixed
reading per verdict, the clustering prediction, the residual the burn-in drops, the residual plots
of the picked model (its file is fetched only when it is picked), and the course's recipe. Notebook
03 prints the same numbers from the committed files.

**The answer on AAPL.** The AIC choice leaves no autocorrelation that Ljung–Box can find at the
lags it can test (10 and 20; lag 5 is not above p + q = 7). Its residuals are not normal (kurtosis
7.03) and their volatility clusters (ARCH-LM p about 10⁻⁵⁰; 29 of 50 squared-residual ACF bars past
a band that noise crosses about 2.5 times): concept note 07's prediction is confirmed. So the model
describes the conditional mean about as well as these tests can check, and says nothing true about
the conditional variance. The course model leaves autocorrelation that Ljung–Box finds clearly
(p near 10⁻⁸). The BIC choice is rejected too, but narrowly and only by the stated rule (any
applied lag below 0.05, unadjusted for testing three lags): Holm's adjustment across its three lags
gives 0.0545, and a Ljung–Box made robust to volatility clustering does not reject (p 0.117 to
0.566).

**The course's recipe, measured.** Its order search ran on the full 2015–2023 series and saw 227
test rows; on the training rows alone the same search chose the same model, ARIMA(0, 1, 1) with an
intercept. So the leak is real in the procedure and changed nothing measurable in the order on
AAPL. The refit then dropped the drift the search had chosen: put back, the drift is 0.000899 log
points per day (p 0.021), and the AIC is 3.546 lower with it.

**The first residual is the price, not a shock.** Every model's first residual is about 3.18, the
first log price, while every later residual is within 0.13 of zero. statsmodels leaves that
observation out of the likelihood and out of its own diagnostics; so does every statistic here. The
course's module-8 plots include it.

---

## Why this design

| Choice | Alternatives | Why this one | What it costs |
|---|---|---|---|
| **Fit three models**: the AIC choice (primary), BIC's choice, the course's refit (owner's default) | The AIC choice only | BIC's choice is the obvious rival (milestone 2's near-cancelling neighbourhood), and the course's model is what a reader of the course would have; the residual tests separate them | Three residual files (1,450,049 bytes together) and a model picker |
| **Grid models refitted from the grid's recorded estimates**, with the grid's settings; the llf must equal the grid's within `LLF_TOLERANCE` = 1e-6 or the export stops (`GridMismatch`) | A fresh fit from statsmodels' default start | Milestone 2 showed one default start can stop at another local maximum. Starting at the recorded point, L-BFGS stops after 1 iteration, and the gap measures that it is the same point: 5.0e-10 (AIC choice) and 6.5e-8 (BIC choice). That shows the point is reproduced, not that it is a maximum: restarted there, Nelder–Mead climbs 1.27e-4 further for the BIC choice (Powell 1.24e-4) and nothing for the AIC choice (Powell 1.8e-8) | The fit depends on the committed `aic_grid.json`; a stale grid stops the export |
| **The course model fitted exactly as the course does**: `ARIMA(train, order=auto.order).fit()`, every default kept | Fix the recipe (put the drift back, search on train only) | The point is to show what the course's code gives. Each problem is measured beside it in `course_track` instead of being fixed silently | A model known to be mis-specified sits in the picker, labelled |
| **The leak measured by the same search on the training rows**, read from `aic_grid.pmdarima_check` (run `"course"`) | Run `auto_arima` again on the training rows | Milestone 2 already ran exactly that search on exactly those rows; re-running it would be a second copy of one fact | `train_only` is null if that run is missing |
| **The dropped drift measured by refitting the same order with a drift**, with the grid's settings | Report only that the trend is `"n"` | A number (drift, its p-value, the AIC gap) says how much the default costs | One more fit; it starts from statsmodels' default, so its AIC is 0.0003 above the grid's cell for the same model (Measured results) |
| **OPG standard errors** (statsmodels' default, `cov_type="opg"`, recorded in `fit_settings`) | The observed information (`"oim"`, `"approx"`); the robust sandwich (`"robust"`) | They are what the course's `summary()` prints, so the table matches the course | For the AR and MA coefficients they assume independent shocks with a constant variance, of any distribution: volatility clustering breaks that, fat tails alone do not (concept note 09 simulates both). Measured on the AIC choice: the information-based errors are 1.30 to 1.45 times OPG for the AR and MA coefficients, the sandwich 1.80 to 1.99 times, the size the clustering gives. With the sandwich, `ar.L3`'s z falls from −2.64 to −1.42 (concept note 09) |
| **The burn-in by statsmodels' own rule**, max(`loglikelihood_burn`, `nobs_diffuse`) | Drop d residuals by hand; keep them all (the course) | It is the rule statsmodels' `plot_diagnostics` applies (statsmodels/tsa/statespace/mlemodel.py:5345), and it follows the model if the initialisation or d changes | None measured; it is 1 for all three models |
| **Tests on `standardized_forecasts_error`** after the burn-in | The raw `resid` | Under the model these are independent N(0, 1); statsmodels' own `test_serial_correlation` and `test_normality` use them | The QQ axis is in standard deviations, not log points |
| **Ljung–Box with `model_df` = p + q**, not applied at a lag ≤ p + q | statsmodels' `df_adjust=True`; `acorr_ljungbox`'s default 0 | p + q is the textbook correction for the ARMA coefficients. statsmodels' rule counts every parameter but one, the drift included: 8 for the AIC choice, where p + q = 7, which gives lag-10 p 0.0898 instead of 0.185. Both are above 0.05, so the verdict is the same | Lag 5 tests nothing for the AIC choice |
| **A verdict is "any row rejects", with no correction** for testing several lags | Bonferroni or Holm across lags | Simple and stated; the app shows every row | More false alarms than 5%: 7.75% for three Ljung–Box lags in a simulation (concept note 08). The BIC choice's "found" is such a borderline call (Holm-adjusted 0.0545); the app's reading says the rule is unadjusted |
| **The residual ACF band is z/√n**, constant across lags | Bartlett's widening band (milestone 2) | Under the null the residuals are white noise, so every lag has the same band; the flags are decided in Python and exported | Slightly wide at small lags for residuals of a fitted ARMA (`diagnostics.py` docstring) |
| **QQ against the normal and a fitted Student-t** | The normal only (the course's `probplot`) | The normal plot shows the tails are fat; the t plot shows how far a fat-tailed law goes towards fitting them (df 3.41 for the AIC choice) | One more column of 2,036 numbers per file |
| **One residuals file per model** | One file (1,450,049 bytes, past the budget); a columnar layout (a major bump); thinning the rows | Each file is about 483 kB, within budget; the app fetches only the picked model | Three files and three parsers' worth of tests (one parser, three ids) |
| **Near-cancelling pairs by a stated rule**: among the AR–MA pairs within `CANCEL_DISTANCE` = 0.1, a one-to-one matching with as many pairs as possible, then the least total distance | No rule; a statistical test for a common factor; closest first (the first build's rule, which can miss a pair: AR {0.5, 0.6} and MA {0.51, 0.41} give one pair, not two) | A reader can apply the rule to the exported roots; the app draws Python's pairs | A display rule, not a test: the real AR root −0.465 and MA root −0.683 of the AIC choice are 0.218 apart and not flagged |
| **The app recomputes nothing**: verdicts, outside flags and pairs come from Python; text is keyed by verdict | The app compares p with alpha or a bar with its band | ADR-0001; two app mutants (a and d1 below) show what drifts otherwise | Every new reading needs a verdict field |
| **Statistical rules checked only by Python's validators** (z, p, the interval, AIC, BIC and AICc from llf, each test's p-value from its statistic, the roots, the pairs, the verdicts, the bands, the flags) | Mirror them in TypeScript | The app checks shapes and bookkeeping (ADR-0001); the corpus holds only cases both readers must decide alike | The Python-only rules are tested in `tests/test_payloads_fit.py`, outside the corpus |
| **`--only` in the export tool**: write named artifacts, reuse `aic_grid.json` from `--out` | Always refit the grid | The milestone-3 payloads take 1.20 s; the grid takes most of an export's 582 s | A shortcut only: a commit still needs a full export and `--check`. It refuses to write a `fit.json` that contradicts the residual files it leaves (checked again on the files after any write) |

---

## Map of what changed

| Path | What | Hand-written or generated |
|---|---|---|
| `src/arima_forecasting/fitting.py` | The three fits, parameter inference, inverse roots and the cancelling rule, `course_track` | Hand-written (new) |
| `src/arima_forecasting/diagnostics.py` | The burn-in, Ljung–Box, Jarque–Bera, ARCH-LM, the residual ACFs, QQ and the t fit, the verdicts, `clustering_prediction` | Hand-written (new) |
| `src/arima_forecasting/payloads.py` | `validate_fit`, `validate_residuals`, and `validate_fit_residuals` (the fit against the residual files) | Hand-written (changed) |
| `src/arima_forecasting/export.py`, `contract.py` | `fit_payloads`; the four artifacts; `build_payloads(…, aic_grid=…)`; milestone 3 current; schema `1.4.0` | Hand-written (changed) |
| `tools/export_app_data.py` | `--only`; a `GridMismatch` becomes exit 1 with a message; the fit and residual files checked against each other before and after writing | Hand-written (changed) |
| `tools/build_notebooks.py` → `notebooks/03_fit_and_diagnostics.ipynb` | The milestone-3 notebook | **Generated** notebook |
| `app/public/data/{fit,residuals_aic,residuals_bic,residuals_course}.json` | The four new artifacts | **Generated**, committed |
| `app/public/data/{meta,prices,eda,stationarity,acf_pacf,aic_grid}.json` | Re-exported: new envelopes (`schema_version` 1.4.0, `source_commit`, `generated_at`); `meta` lists ten artifacts; the data of the other five did not change | **Generated**, committed |
| `app/src/lib/contract.fit.ts` | `parseFit`, `parseResiduals` | Hand-written (new) |
| `app/src/lib/fitText.ts`, `app/src/views/FitView.tsx`, `app/src/data/useFitData.ts` | Fixed text per verdict, the page, loading and parsing | Hand-written (new) |
| `app/src/App.tsx`, `app/src/lib/gate.ts` | The page offered when `meta` lists its four files, through `lazy()` | Hand-written (changed) |
| `app/src/test/fixtures/{fit,residuals_aic}.data.json`, `payload_cases.json` | Made-up bases; 125 new corpus cases (101 fit, 24 residuals; 23 of them from the fix round) and 2 token cases | Hand-written bases, generated cases |
| `tests/test_{fitting,diagnostics,payloads_fit}.py` | New suites | Hand-written (new) |
| `tests/test_committed_artifacts.py`, `test_export.py`, `test_notebooks.py`, `test_payload_corpus.py`, … | The milestone-3 files rebuilt and cross-checked; the tool's new option; notebook 03 | Hand-written (changed) |
| `docs/concepts/08-09`, ADR-0002, `contract.md`, this file | Concept notes, the measured section of ADR-0002, the shipped contract | Hand-written |

---

## Code walkthrough

Read in this order. Each step names one file and line.

1. `src/arima_forecasting/export.py:172` is `fit_payloads`. It hands `fit_models` the training rows
   and the course rows (training and test, never out-of-sample), then `residual_payloads` the fitted
   results and the training dates. `build_payloads` (`:196`) runs it after the grid, or with a reused
   grid for `--only`.
2. `src/arima_forecasting/fitting.py:282` is `fit_models`. It refuses a course series that does not
   start with the training series (`:288`), then takes the AIC and BIC cells from the grid's
   `selection` (`:292-295`) and refits each (`:299`).
3. `src/arima_forecasting/fitting.py:194` is `fit_grid_cell`. It builds the model exactly as the grid
   did (`selection._model`), starts at the cell's recorded estimates (`:205`), fits with the grid's
   optimiser and `maxiter` and `cov_type="opg"` (`:208`), and raises `GridMismatch` when the llf is
   more than `LLF_TOLERANCE` from the grid's (`:210`). `tests/test_fitting.py:140` checks both paths;
   its helper at `tests/test_fitting.py:131` explains why the test cell is polished first.
4. `src/arima_forecasting/fitting.py:245` is `course_track`. `auto_arima_full` (`:224`) runs pmdarima
   with the course's arguments (`COURSE_SETTINGS`, `:70`, the same list as milestone 2's `"course"`
   run) on the full series; `course_refit` (`:215`) is the course's `ARIMA(train, order).fit()`; the
   same order is then fitted with a drift (`:255`); the training-only order comes from the grid's
   pmdarima run (`:257`), and `same_order` compares order and intercept (`:266`).
5. `src/arima_forecasting/fitting.py:130` is `parameter_rows`: z, the two-sided p-value and the 95%
   interval computed from the estimate and statsmodels' standard error (`:143`), all five null
   together when the standard error is not a positive finite number. `:90` renames statsmodels' `x1`
   to `drift`. `tests/test_fitting.py:108` checks z and p against statsmodels' own `zvalues` and
   `pvalues`.
6. `src/arima_forecasting/fitting.py:98` is `inverse_roots`, and `:110` `cancelling_pairs`: a
   maximum matching of the AR–MA pairs within the threshold (scipy's `linear_sum_assignment`, with
   a cost above the threshold larger than any total of the pairs within it), then the least total
   distance. `tests/test_fitting.py:51` works the rule by hand, ties and conjugates included, and
   `tests/test_fitting.py:69` shows where closest first would differ.
   `src/arima_forecasting/fitting.py:152` is `describe`, which assembles one `models[]` entry.
7. `src/arima_forecasting/diagnostics.py:59` is `burn_in`, statsmodels' rule, and `:65`
   `standardized_residuals`, the series every test sees. `tests/test_diagnostics.py:33` checks the
   rule against statsmodels for d = 1 and 2, and `tests/test_diagnostics.py:43` that the burned
   residual is the level, not a shock.
8. `src/arima_forecasting/diagnostics.py:83` is `ljung_box`: `applied` is lag > `model_df` (`:88`), and
   the caller passes p + q (`:152`). `:102` is `arch_lm` with `ddof=0` (`:111`), `:116` `normality`
   (Pearson kurtosis), `:121` `qq_points` (scipy's `probplot`, then the fitted t at the same
   positions), `:75` `correlogram` with the band z/√n (`:78`) and `outside` (`:70`).
9. `src/arima_forecasting/diagnostics.py:134` is `verdicts`: a test is "found" or "rejected" when any of
   its rows has p < alpha. `:145` `model_diagnostics` builds one model's test block and plot series,
   with the burned rows for display (`:162`). `:190` `residual_payloads` adds them to `fit`, writes one
   `residuals_<id>` payload per model, and tests concept note 07's prediction on the primary model
   (`:212`).
10. `src/arima_forecasting/payloads.py:1687` is `validate_fit` and `:1936` `validate_residuals`. Both
    readers bound the orders first (`:1339`, p and q ≤ 10, d ≤ 2), so a huge order gives one short
    problem. Python re-derives what the app does not: each parameter's p-value from z (`:1426`),
    each test's p-value from its statistic (`:1364`, with the chi-squared tail in closed form at
    `:1268`), AIC, BIC and AICc from llf (`:1668`), the cancelling rule (`:1464`), the llf gap
    against its tolerance (`:1776`), each band (`:1905`) and every outside flag (`:1929`).
    `tests/test_payloads_fit.py:103` breaks one statistical rule per case and expects the named
    refusal. `src/arima_forecasting/payloads.py:1991` is `validate_fit_residuals`, the fit against
    the residual files.
11. `tools/export_app_data.py:81` is `--only`; it reads the grid from `--out` (`:102`) and writes only
    the named files. Before writing it checks the fit and residual files the folder will hold
    (`:165`), and after writing it checks them again as read back (`:186`);
    `tests/test_export.py:472` shows `--only fit` refusing to write beside stale residual files. `tests/test_committed_artifacts.py:231` rebuilds all four milestone-3 files from
    the committed `prices.json` and `aic_grid.json` and compares them exactly; `:240` and `:252` are
    the cross-file checks (the fit names the grid's choices; each residuals file matches its model and
    the training dates).
12. `app/src/App.tsx:14` loads `FitView` through `lazy()`, offered only when `meta.json` lists the four
    files (`app/src/lib/gate.ts:18`). `app/src/data/useFitData.ts:36` fetches one model's file and
    parses it for that model's id; a parser that throws becomes an error state (`:50`), and a failed
    file is fetched again on the next pick (`:67`). `app/src/lib/contract.fit.ts:686` is `parseFit`,
    `:282` bounds an order before anything is built from it, and `:838` is where `parseResiduals`
    refuses another model's file.
13. `app/src/views/FitView.tsx:111` is the page body. `PValue` (`:49`) sets a power of ten in a
    superscript and an underflowed 0 as "< 1e-300". The unit circle (`:242`) rings Python's pairs
    (`:304`), the test table (`:346`) reads each verdict, `:444` shows the burned residual, `bars`
    (`:460`) passes Python's `outside` flag to each bar, and `:528` is the course card.
14. `tools/build_notebooks.py:566` builds notebook 03, which prints the numbers below from the committed
    files and rebuilds them once to check they match.

---

## Data flow

The training log price (2,037 values) followed to the page.

| # | Hop | Shape at this hop | Where |
|---|---|---|---|
| 1 | `price_table` → training rows and course rows | 2,037 log closes, 2015-01-02 to 2023-02-03; 2,264 with the test rows, to 2023-12-29 | `src/arima_forecasting/export.py:172` |
| 2 | `_grid_cell`, twice | the grid's (3, 1, 4) with a drift and (2, 1, 2) without, each with its recorded estimates | `src/arima_forecasting/fitting.py:187` |
| 3 | `fit_grid_cell` | two statsmodels results; llf gaps 5.0e-10 and 6.5e-8; 1 iteration each | `src/arima_forecasting/fitting.py:194` |
| 4 | `auto_arima_full` | 2,264 rows → (0, 1, 1) with an intercept | `src/arima_forecasting/fitting.py:224` |
| 5 | `course_refit`, and the same order with a drift | (0, 1, 1), trend `"n"`, 2 iterations; the drift fit beside it | `src/arima_forecasting/fitting.py:215`, `:255` |
| 6 | `describe` | three `models[]` entries: 9, 5 and 2 parameters; 3 + 4, 2 + 2 and 0 + 1 inverse roots; 2, 2 and 0 pairs | `src/arima_forecasting/fitting.py:152` |
| 7 | `model_diagnostics`, per model | 2,036 standardised residuals; 3 Ljung–Box rows, 1 Jarque–Bera, 2 ARCH-LM; 2 × 50 ACF rows; 2,036 QQ points | `src/arima_forecasting/diagnostics.py:145` |
| 8 | `residual_payloads` | `fit` with `diagnostics`, `diagnostic_settings` and `clustering_prediction`; three `residuals_<id>` payloads | `src/arima_forecasting/diagnostics.py:190` |
| 9 | validate, `dumps`, check the fit against the residual files, write, check again | four JSON files: 18,464 bytes and about 483 kB each | `tools/export_app_data.py` |
| 10 | The reader opens **Fit and diagnostics** | `loadFit` fetches `fit.json`; `parseFit` re-checks it | `app/src/data/useFitData.ts` |
| 11 | The reader picks a model | `loadResiduals` fetches that model's file; `parseResiduals` checks its id | `app/src/data/useFitData.ts:36` |
| 12 | Tables, unit circle, plots | the page draws what the files say | `app/src/views/FitView.tsx:111` |

```mermaid
sequenceDiagram
    participant X as export_app_data.py
    participant F as fitting.py
    participant P as pmdarima
    participant D as diagnostics.py
    participant J as app/public/data
    participant A as Fit page
    X->>F: training rows (2,037), course rows (2,264), aic_grid
    F->>F: refit the AIC and BIC cells from their recorded estimates (llf within 1e-6)
    F->>P: auto_arima, the course's arguments, 2,264 rows
    P-->>F: (0, 1, 1) with an intercept
    F->>F: ARIMA(train, order).fit(): trend n; the same order with a drift
    F-->>D: three fitted results
    D->>D: burn 1, Ljung-Box, Jarque-Bera, ARCH-LM, ACFs, QQ
    D-->>X: fit, residuals_aic, residuals_bic, residuals_course
    X->>J: validate, write (or --check: compare)
    A->>J: fetch fit.json, then the picked model's residuals file
    A->>A: re-check, draw
```

---

## Pitfalls met and how each is guarded

| Pitfall | How it showed up | Guard (`file:line`) |
|---|---|---|
| **The first residual is the level, not a shock** | Every model's first residual is about 3.18 (the first log price is 3.1852), every later one within 0.13 of zero; its standardised value is 0.0032, because statsmodels' approximate diffuse start gives that forecast a variance of about 10⁶. A QQ plot of `resid` whole, as the course draws it, has a top point at 3.185 and the next at 0.105 | `burn_in` (`src/arima_forecasting/diagnostics.py:59`); `tests/test_diagnostics.py:43`; the burned row is exported and shown, so the reader sees what the course plots |
| **The course's refit drops the drift** | `ARIMA(train, order=(0, 1, 1)).fit()` has trend `"n"`: statsmodels' default at d ≥ 1 (statsmodels/tsa/arima/model.py:156-160) | The drift fit beside it (`src/arima_forecasting/fitting.py:255`) and `course_track.drift_dropped`; `tests/test_fitting.py:173` |
| **The course's search sees the test period** | `auto_arima` ran on 2,264 rows, 227 of them test rows | `train_only` and `same_order` (`src/arima_forecasting/fitting.py:257`); `tests/test_committed_artifacts.py:240` ties `train_only` to the grid's run |
| **A fresh fit can stop short of the grid's point** | On the simulated (1, 1, 1) with a drift in `tests/test_fitting.py`, one default start stopped 5.4e-6 below a restart from its own estimates, more than the 1e-6 tolerance | Refit from the recorded estimates and `GridMismatch` (`src/arima_forecasting/fitting.py:210`); `tests/test_fitting.py:140` |
| **The 1 MB budget** | The three residual series together are 1,450,049 bytes | One file per model (`src/arima_forecasting/export.py:49`); `tests/test_committed_artifacts.py:114` fails any file over 1,000,000 bytes |
| **Near-cancelling roots make the estimates hard to read** | The AIC choice's AR and MA standard errors are 0.15 to 0.29 for lags 1 to 3, against 0.023 to 0.030 for the BIC choice; its complex AR and MA pairs are 0.0625 apart. Distance alone does not explain it: the BIC choice's pair is closer (0.037) and its errors are small (concept note 09) | The roots and pairs are exported and drawn (`src/arima_forecasting/fitting.py:110`); `tests/test_fitting.py:51`; concept note 09 says how to read them |
| **OPG errors assume no volatility clustering** | The robust sandwich errors of the AIC choice's AR and MA coefficients are 1.80 to 1.99 times OPG. The first build blamed the fat tails (kurtosis 7.03). The evidence says the ratio comes from dependence in the order of the shocks, as volatility clustering would give: rebuilt from AAPL's own shocks resampled independently (kurtosis kept, order lost) the AR and MA ratios run from 0.915 to 1.035 (medians over 10 resamples of the smallest and the largest); from the same shocks in their order, 1.80 to 1.99 (`aapl_iid_probe.py`, Second review fix round). A wrong conditional mean would also separate the sandwich from OPG | Not corrected: `cov_type` is recorded in `fit_settings` (`src/arima_forecasting/fitting.py:59`) and the page says which errors these are; the size of the difference is in Measured results |
| **statsmodels labels the drift `x1`** | In 0.15.0 `ARIMA` passes trend `'t'` as an exogenous column | `parameter_name` (`src/arima_forecasting/fitting.py:90`); `library_name` keeps statsmodels' label; `tests/test_fitting.py:28` |
| **Ljung–Box at a lag ≤ p + q** | `acorr_ljungbox` returns a NaN p-value there, which JSON cannot carry | `applied` (`src/arima_forecasting/diagnostics.py:88`); `p_value` and `df` null exactly when not applied; `tests/test_diagnostics.py:52` |
| **statsmodels' own degrees-of-freedom rule counts the drift** | `test_serial_correlation(df_adjust=True)` uses 8 for the AIC choice (statsmodels/tsa/statespace/mlemodel.py:3745) | p + q passed explicitly (`src/arima_forecasting/diagnostics.py:152`) and recorded as `ljung_box_model_df` |
| **A p-value can underflow to 0** | Jarque–Bera for the BIC and course models, and the BIC choice's `ar.L1` (z −74.8), give p = 0.0 in double precision | 0.0 is a valid number in the contract; the app prints it as "< 1e-300", never "0", and sets other powers of ten in a superscript (`pParts`, `app/src/lib/fitText.ts:33`) |
| **`sigma2`'s z-test is a boundary null** | The first build exported `sigma2`'s z (49.5) and p (0.0); its null value 0 is on the edge of what a variance can be, where z is not normal | `parameter_rows` exports its z and p as null (`src/arima_forecasting/fitting.py:130`); both readers refuse a `sigma2` with them; the table shows a dash and a note (`app/src/views/FitView.tsx:224`) |
| **The refit reproduces the grid's point; it does not prove a maximum** | Restarted at the BIC choice's recorded point, Nelder–Mead gains 1.27e-4 in llf, 127 times the tolerance | The docs and `fitting.py` say "reproduces"; the gains are measured (`m3_fix_probe.py`, Review fix round) |
| **Closest-first pairing misses pairs** | AR {0.5, 0.6} and MA {0.51, 0.41}: closest first gives one pair, two exist within 0.1 | A maximum matching (`src/arima_forecasting/fitting.py:110`); `tests/test_fitting.py:69`; Python's validator restates it by dynamic programming (`src/arima_forecasting/payloads.py:1464`) |
| **A stated order is used before it is bounded** | order [10⁸, 1, 0] in a file: Python's validator raised `MemoryError` and the app's parser ran out of heap; 2³² gave a `RangeError`, and the page stayed on "loading" | Both readers bound p, q ≤ 10 and d ≤ 2 first (`src/arima_forecasting/payloads.py:1339`, `app/src/lib/contract.fit.ts:282`); corpus cases; a parser that throws is an error state (`app/src/data/useFitData.ts:50`) |
| **A root list longer than its order** (second review) | k equal roots a side, the order unchanged: the validator's matching ran over 2^k subsets, 7.8 s at k = 18 (`roots_probe.py`, Second review fix round) | `_check_roots` returns no roots on a count mismatch (`src/arima_forecasting/payloads.py:1437`) and `_check_pairs` matches at most `MAX_PQ` roots a side (`:1515`); `tests/test_payloads_fit.py:414`, `:424`, `:431` |
| **A file set its own tolerances** (second review) | `llf_tolerance` 1.0 in a self-consistent file let a refit 0.5 from the grid's llf pass; `cancel_distance` was read from the file too | Both readers pin 1e-6 and 0.1 (`src/arima_forecasting/payloads.py:1243`, `app/src/lib/contract.fit.ts:50`) and refuse another stated value; `tests/test_payloads_fit.py:359`; corpus cases |
| **`--only fit` beside stale residual files** | After a code change, `--only fit` wrote a `fit.json` whose `nlags` (40) contradicted the residual files' (50); only pytest noticed | `validate_fit_residuals` before and after writing (`tools/export_app_data.py:165`, `:186`); `tests/test_export.py:472` |
| **Sizes that only a real browser shows** | The three legend icons drew at 300 × 300 px and the QQ plot at 927 × 579 px with its text scaled up (`.plot svg` is 100% wide) | `.plot svg.legend-mark` and `.qq-plot` in `app/src/index.css:216`; measured in headless Chromium: 12 × 12 px and 560 × 350 px (Review fix round) |
| **One model's residual file shown for another** | App mutant (b): a parser that accepted any id would draw the BIC series under the AIC label | `parseResiduals` checks `model_id` (`app/src/lib/contract.fit.ts:838`); Python's `validate_residuals(data, model_id)`; corpus case "residuals_aic: the model_id of another model" |
| **The app recomputing a flag** | App mutant (a): comparing \|acf\| with the band in the view | `FitView.tsx` passes Python's `outside` (`app/src/views/FitView.tsx:460`); the view test flips a flag and expects the bar to follow |

---

## Predict before you look

**Write your answers down before you scroll.** Commit to a number, even a guess.

1. The AIC and BIC choices are refitted from the grid's recorded estimates. How close will the
   log-likelihood come to the grid's, and in how many iterations?
2. The course runs `auto_arima` on the full 2015–2023 series. How many test rows does it see? Does
   the training-only search choose a different order? What happens to the drift in the refit, and
   how much AIC does that cost?
3. How big is each model's first residual, and why? How big is the largest residual after it?
4. Which of the AIC choice's Ljung–Box lags (5, 10, 20) can be tested with p + q degrees of freedom
   removed? Will the test find autocorrelation? Would statsmodels' own rule change the answer?
5. What kurtosis do the residuals have? What degrees of freedom will a Student-t fitted to them
   have?
6. Concept note 07 predicted volatility clustering. What will ARCH-LM say, and how many of the 50
   squared-residual ACF bars will cross a band that noise crosses about 2.5 times?
7. Do the BIC choice and the course model pass Ljung–Box? How many cancelling pairs does each model
   have, and are the AIC choice's standard errors larger or smaller than the BIC choice's?
8. How big are the four new files against the 1 MB budget, and how long does a full export take
   now, against milestone 2's 491 s?

---

## Measured results

### Environment

Data steps ran with `VOL_DATA_DIR=$PWD/data` on the 13:37 UTC snapshot of milestone 1
(`prices.json`, `source.downloaded_at` 2026-10-29T13:37:24Z; no new download). Versions: Python
3.12.13, numpy 2.5.4, scipy 1.18.1, statsmodels 0.15.0, pmdarima 2.1.1, Node v22.23.1; no dependency
was added or upgraded. The machine has 20 cores, and other agents were running during the export.

### Answers to the predictions

Rounding: values are rounded to the digits shown; the files hold the full doubles.

| What | Command | Result | Date |
|---|---|---|---|
| Q1. Refits | `m3_probe.py` (below) | AIC choice: llf gap 5.0e-10 (5.03e-10), BIC choice 6.5e-8 (6.48e-8), both converged after **1 iteration**; tolerance 1e-6. On the simulated walk of `tests/test_fitting.py`, one default start stopped **5.4e-6** below a restart from its own estimates. Restarted at the recorded points with tight tolerances (`m3_fix_probe.py`, Review fix round): Nelder–Mead gains −5.5e-12 and Powell +1.8e-8 for the AIC choice, **+1.27e-4** and **+1.24e-4** for the BIC choice, so the BIC choice's recorded point is not quite a maximum | 2026-10-29 |
| Q2. The course's recipe | `fit.json`, `course_track` | Full series: 2,264 rows, **227 test rows seen**; chose (0, 1, 1) with an intercept (AIC −11693.898, intercept 0.000910, `ma.L1` −0.0761). Training rows alone: (0, 1, 1) with an intercept: `same_order` true. Refit: trend `"n"`, `ma.L1` −0.0788 (SE 0.0145), AIC −10395.391, 2 iterations. With a drift: drift **0.000899** per day (SE 0.000389, p **0.0206**), AIC −10398.937: **3.546 lower**. The grid's own (0, 1, 1) with a drift is −10398.93703, 0.0003 below this default-start fit, so the gap is 3.546 either way | 2026-10-29 |
| Q3. The first residual | `fit.json`, `models[].diagnostics.burned` | 2015-01-02: AIC choice 3.18428, BIC choice and course 3.18518, exactly the first log price, 3.1851847 (the drift model's forecast of the first day is the drift, 0.0009). Standardised: 0.0032 (implied forecast variance 1,000,000.00036). Largest \|residual\| after it: 0.1227, 0.1188 and 0.1295 | 2026-10-29 |
| Q4. Ljung–Box, AIC choice | `fit.json`, `models[0].diagnostics.ljung_box` | p + q = 7. Lag 5: **not applied** (Q 0.460). Lag 10: Q 4.821 on 3 df, p **0.185**. Lag 20: Q 12.480 on 13 df, p **0.489**. Verdict `not_found`. statsmodels' `df_adjust=True`: `model_df` 8, lag-10 p 0.0898; still above 0.05 | 2026-10-29 |
| Q5. Normality | `fit.json`, `jarque_bera`; `residuals_aic.json`, `t_fit`, `qq` | AIC choice: skew −0.324, kurtosis **7.03**, JB 1415.10, p 5.2e-308: rejected. Student-t df **3.41** (BIC 3.37, course 3.24). Smallest standardised residual −6.616 at normal quantile −3.397 and t quantile −8.080; largest 5.166 at 3.397 and 8.138 | 2026-10-29 |
| Q6. Clustering | `fit.json`, `arch_lm`, `clustering_prediction`; `residuals_aic.json` | ARCH-LM: 5 lags LM 242.39, p **2.4e-50**; 10 lags LM 275.27, p **2.6e-53**. Squared-residual ACF: **29 of 50** bars past the band 0.04344, against 2.5 expected by chance. Residual ACF: 2 of 50, one of them (lag 18) only 8.7e-5 past its band, so another BLAS could flip that flag (`m3_fix_probe.py`). With `ddof` = p + q = 7, as `het_arch`'s docstring suggests for ARMA residuals, ARCH-LM p is 3.6e-50 and 4.1e-53: the same verdict. `clustering_prediction.confirmed` true | 2026-10-29 |
| Q7. The other two models, roots, errors | `fit.json`; `m3_probe.py`; `m3_fix_probe.py` | BIC choice: Ljung–Box p **0.0182** (lag 5, 1 df), **0.0392** (lag 10), 0.0837 (lag 20): `found`, by the unadjusted any-lag rule only: Holm-adjusted 0.0545, 0.0784, 0.0837, and a Box–Pierce robust to clustering gives 0.117, 0.384, 0.566. Course: 0.239, **6.6e-8**, **1.5e-8**: `found` (robust: 0.676, 0.0048, 0.0059). All three: normality rejected (kurtosis 7.20 and 7.76), clustering found (ARCH-LM p ≤ 6.7e-49). Residual ACF past the band: 3 and 10 of 50; squared: 28 and 26. Pairs: AIC choice **2**, the complex AR pair −0.842 ± 0.398i (modulus 0.932, ±154.7°) against the MA pair −0.782 ± 0.414i (0.885, ±152.1°), **0.0625** apart; its real AR root −0.465 and MA root −0.683 are 0.218 apart, not flagged. BIC choice **2**, 0.0371 apart (AR 0.960 at ±159.0°, MA 0.930 at ±160.3°). Course **none** (p = 0). OPG errors of `ar.L1`: **0.166** (AIC choice) against **0.024** (BIC choice) | 2026-10-29 |
| Q7. Other covariance estimators | `m3_probe.py` | AIC choice, ratio to OPG: `"oim"` 1.30 to 1.37 and `"approx"` 1.37 to 1.45 for the AR and MA coefficients; `"robust"` 1.80 to 1.99; drift 0.95 under all three; `sigma2` 1.55 and 2.69. With the robust errors, z: `ar.L3` −1.42 (OPG −2.64), `ma.L3` 0.85 (1.58), `ma.L4` −2.25 (−4.49), drift 2.40 (2.29). BIC choice: `"robust"` 1.43 to 1.64, every AR and MA \|z\| still above 18 | 2026-10-29 |
| Q8. Sizes | `m3_probe.py` (`wc -c` gives the same bytes) | `fit.json` 18,464 bytes (1.8% of 1 MB; gzip level 6, Python: 4,464); `residuals_aic.json` 483,331 (48.3%; 93,437), `residuals_bic.json` 483,320 (48.3%; 93,397), `residuals_course.json` 483,398 (48.3%; 93,578); the three together 1,450,049. `meta.json` 1,613; the other five unchanged in size. All ten have `schema_version` 1.4.0 | 2026-10-29 |
| Q8. Export time | `time (OPENBLAS_NUM_THREADS=1 VOL_DATA_DIR=$PWD/data .venv/bin/python tools/export_app_data.py)` | **582 s** (real 9 min 42.006 s; user 90 min 52.1 s), on a machine loaded by other agents; milestone 2's export took 491 s, measured the same day, also on a loaded machine (milestone-2 walkthrough, Q7). The fix round's export took **364 s** (real 6 min 4.1 s; user 84 min 43.8 s). The milestone-3 payloads alone (`fit_payloads` from the committed files) took **1.20 s** and equal the committed files; the rest is the grid | 2026-10-29 |
| Q8. App | `cd app && npm run build` (the gate's build) | After the fix round: `FitView-*.js` 41,302 bytes (41.30 kB; Vite reported gzip 12.98 kB), loaded only with the page; the first build's was 38,936. Main chunk `index-*.js` 227,091 bytes (227.09 kB), against milestone 2's 226.66 kB | 2026-10-29 |

**What the numbers say.**

- **The refits reproduce the grid's points.** Gaps of 5.0e-10 and 6.5e-8 after one iteration: the
  optimiser accepted the recorded point and stopped. That is not proof of a maximum: Nelder–Mead
  started at the BIC choice's point climbs 1.27e-4 further (the first build called both "the grid's
  maxima"; it is true of the AIC choice only, within 1.8e-8). A gain that small moves no number on
  the page. A fresh default start would have needed luck (the simulated 5.4e-6).
- **The AIC choice passes the only serial-correlation test it can take.** Lag 5 tests nothing when
  seven coefficients have been estimated; lags 10 and 20 find nothing. The verdict does not hinge on
  the degrees-of-freedom rule (0.185 with ours, 0.0898 with statsmodels').
- **The other two do not, one clearly and one narrowly.** The course model's one coefficient leaves
  autocorrelation at lags 10 and 20 (p near 10⁻⁸; 0.0048 even with a Box–Pierce robust to the
  clustering). BIC's four are rejected at lags 5 and 10 (p 0.018 and 0.039), but only by the stated
  rule, any applied lag below 0.05 with no adjustment for testing three: Holm's adjustment gives
  0.0545, and the robust statistic does not reject. These are in-sample results: a model that fits
  the training residuals better may still forecast worse, which milestone 4 tests.
- **Every model leaves fat tails and volatility clustering.** Kurtosis 7 to 7.8; ARCH-LM p below
  10⁻⁴⁸ for all three; 26 to 29 of 50 squared-residual bars past the band. No choice of (p, q) touches
  this: it lives in the variance, which an ARIMA model holds constant. The Student-t fit (df about
  3.4) describes the marginal tails better than the normal, as the QQ plot shows.
- **The prediction held.** Concept note 07 read the choice as a near-cancelling cycle fitted largely
  to spring 2020 and predicted clustering in its residuals; ARCH-LM and the squared-residual ACF
  confirm it.
- **The course's recipe, measured on AAPL.** The leak is in the procedure and did not change the
  order here. The dropped drift did change the model: 0.0009 log points per day, about 0.09% a day,
  with p 0.021 under OPG errors, and 3.5 AIC.
- **The AIC choice's individual coefficients are hard to read.** Two near-cancelling complex pairs
  and a looser real pair make its AR and MA estimates large, opposite in sign and imprecise
  (`ar.L1` −2.150, `ma.L1` 2.092). Under robust errors two of its seven ARMA coefficients have |z| below
  1.96. The model's forecasts can still be fine; its coefficients are not separately meaningful
  (concept note 09).

### The commands behind the table

```bash
time (OPENBLAS_NUM_THREADS=1 VOL_DATA_DIR=$PWD/data .venv/bin/python tools/export_app_data.py)
VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py --check
uv run python tools/build_notebooks.py --check
wc -c app/public/data/*.json
```

Notebook 03 prints the fits, the course track, the tests and the clustering prediction from the
committed files, and `tests/test_notebooks.py` checks the printed lines against the files. Every
other number in the table came from this script, `m3_probe.py`, run from the repository root with
`OPENBLAS_NUM_THREADS=1 .venv/bin/python -I m3_probe.py` (2.2 s in the first build; 6.6 s in the fix
round, beside the test suite). It reads the committed files and
refits the two grid cells and the course model from them:

```python
import gzip, json, math, warnings
import numpy as np
from scipy import stats
from arima_forecasting import selection
from arima_forecasting.fitting import course_refit, fit_grid_cell
warnings.simplefilter("ignore")
D = "app/public/data/"
load = lambda name: json.load(open(D + name + ".json"))
meta, fit, grid = load("meta"), load("fit")["data"], load("aic_grid")["data"]
for name in meta["data"]["artifacts"]:
    raw = open(D + name + ".json", "rb").read()
    print(f"{name}: {len(raw)} bytes, gzip-6 {len(gzip.compress(raw, 6))}, schema {json.loads(raw)['schema_version']}")
rows = [r for r in load("prices")["data"]["rows"] if r["segment"] == "train"]
y = np.array([r["log_close"] for r in rows])
print("train", len(y), rows[0]["date"], rows[-1]["date"], "y[0]", y[0])
cells = {(c["d"], c["p"], c["q"], c["trend"]): c for c in grid["cells"]}
for m in fit["models"]:
    g = m["diagnostics"]; r = load("residuals_" + m["id"])["data"]
    print(m["id"], m["order"], m["trend"], "gap", m["llf_gap"], "iter", m["iterations"], "aic", m["information"]["aic"])
    print("  params (name, value, se, z, p)", [(x["name"], float(f"{x['value']:.4g}"), float(f"{x['std_err']:.3g}"), None if x["z"] is None else round(x["z"], 2), None if x["p_value"] is None else float(f"{x['p_value']:.3g}")) for x in m["params"]])
    print("  burned", g["burned"], "max|resid| after", g["max_abs_resid_after_burn"])
    print("  LB", [(x["lag"], x["model_df"], x["applied"], x["p_value"]) for x in g["ljung_box"]])
    print("  JB", g["jarque_bera"], "ARCH", [(x["lags"], x["p_value"]) for x in g["arch_lm"]], g["verdicts"])
    print("  acf past band", r["acf"]["outside_count"], "squared", r["acf_squared"]["outside_count"], "band", r["acf"]["band"], "t df", r["t_fit"]["df"])
    print("  pairs", [(p["ar"], p["ma"], p["distance"]) for p in m["cancelling_pairs"]])
    ar, ma = ([complex(x["re"], x["im"]) for x in m[k]] for k in ("inv_roots_ar", "inv_roots_ma"))
    polar = lambda zs: [(round(abs(z), 3), round(float(np.degrees(np.angle(z))), 1)) for z in zs]
    print("  roots (modulus, degrees): AR", polar(ar), "MA", polar(ma), "| AR-MA distances", [[round(abs(a - b), 3) for b in ma] for a in ar])
    print("  rows", len(r["rows"]), r["rows"][0]["date"], r["rows"][-1]["date"], "QQ lowest", r["qq"][0], "highest", r["qq"][-1])
    key = (m["order"][1], m["order"][0], m["order"][2], m["trend"])
    if m["id"] == "course":
        res, _ = course_refit(y, m["order"])
        (_, ordered), _ = stats.probplot(res.resid, dist="norm")
        print("  course-style QQ (resid whole): top", ordered[-1], "next", ordered[-2], "| drift cell aic", cells[(1, 0, 1, "t")]["aic"])
        continue
    res, _ = fit_grid_cell(y, cells[key])
    model_df = max(0, res.df_model - res.k_diffuse_states - 1)
    sm = res.test_serial_correlation("ljungbox", df_adjust=True, lags=[10])[0][:, 0]
    print("  statsmodels df_adjust model_df", model_df, "p+q", m["order"][0] + m["order"][2], "lag-10 stat, p", sm.tolist())
    se = {c: res.model.smooth(res.params, cov_type=c).bse for c in ("opg", "oim", "approx", "robust")}
    print("  se opg", dict(zip(res.model.param_names, np.round(se["opg"], 4).tolist())))
    for c in ("oim", "approx", "robust"):
        print(f"  se {c}/opg", dict(zip(res.model.param_names, np.round(se[c] / se["opg"], 2).tolist())))
    print("  z with robust se", dict(zip(res.model.param_names, np.round(res.params / se["robust"], 2).tolist())))
track = fit["course_track"]
print("course", track["full_series"]["order"], track["full_series"]["with_intercept"], track["full_series"]["aic"], track["full_series"]["params"], track["train_only"], track["same_order"], track["n_course"], track["test_rows_seen"])
print("drift dropped", track["drift_dropped"])
print("clustering", fit["clustering_prediction"])
# tests/test_fitting.py's grid_cell: one default start on the simulated (1, 1, 1) + drift walk, then a restart.
rng = np.random.default_rng(20261029)
sim = math.log(30.0) + np.cumsum(0.0008 + 0.017 * rng.standard_normal(400))
first = selection.run_start(sim, (1, 1, 1, "t"), "default", None)
again = selection.run_start(sim, (1, 1, 1, "t"), "default, polished", np.array(list(first["params"].values())))
print("simulated restart gain", again["llf"] - first["llf"])
import collections, glob, os
print("three residuals files together", sum(os.path.getsize(D + f"residuals_{i}.json") for i in ("aic", "bic", "course")))
corpus = json.load(open("app/src/test/fixtures/payload_cases.json"))
print("corpus", sorted(collections.Counter((c["base"], c["valid"]) for c in corpus["cases"] if c["base"] in ("fit", "residuals_aic")).items()), len(corpus["cases"]), "cases,", len(corpus["token_cases"]), "token cases")
for f in sorted(glob.glob("app/dist/assets/FitView-*.js") + glob.glob("app/dist/assets/index-*.js")):
    print(f, os.path.getsize(f), "bytes")
```

It printed (re-run in the fix round, on the files the fix round exported):

```text
meta: 1613 bytes, gzip-6 585, schema 1.4.0
prices: 456025 bytes, gzip-6 67176, schema 1.4.0
eda: 529907 bytes, gzip-6 101505, schema 1.4.0
stationarity: 6685 bytes, gzip-6 1356, schema 1.4.0
acf_pacf: 44899 bytes, gzip-6 6626, schema 1.4.0
aic_grid: 153790 bytes, gzip-6 27719, schema 1.4.0
fit: 18464 bytes, gzip-6 4464, schema 1.4.0
residuals_aic: 483331 bytes, gzip-6 93437, schema 1.4.0
residuals_bic: 483320 bytes, gzip-6 93397, schema 1.4.0
residuals_course: 483398 bytes, gzip-6 93578, schema 1.4.0
train 2037 2015-01-02 2023-02-03 y[0] 3.1851847171036805
aic [3, 1, 4] t gap 5.029505700804293e-10 iter 1 aic -10440.245385756925
  params (name, value, se, z, p) [('drift', 0.0009019, 0.000394, 2.29, 0.0221), ('ar.L1', -2.15, 0.166, -12.95, 2.27e-38), ('ar.L2', -1.652, 0.293, -5.64, 1.72e-08), ('ar.L3', -0.4038, 0.153, -2.64, 0.00821), ('ma.L1', 2.092, 0.169, 12.36, 4.5e-35), ('ma.L2', 1.503, 0.294, 5.1, 3.32e-07), ('ma.L3', 0.2476, 0.157, 1.58, 0.114), ('ma.L4', -0.08306, 0.0185, -4.49, 7.18e-06), ('sigma2', 0.0003441, 6.95e-06, None, None)]
  burned [{'date': '2015-01-02', 'resid': 3.1842828594658132, 'resid_std': 0.003184282858899791}] max|resid| after 0.12271882678134016
  LB [(5, 7, False, None), (10, 7, True, 0.18537563114170724), (20, 7, True, 0.4887311918530781)]
  JB {'kurtosis': 7.032439351928712, 'p_value': 5.181567497409661e-308, 'skew': -0.3241920171548887, 'statistic': 1415.102202051986} ARCH [(5, 2.362533897732377e-50), (10, 2.5875447932782663e-53)] {'arch': 'found', 'normality': 'rejected', 'serial_correlation': 'not_found'}
  acf past band 2 squared 29 band 0.043436938124839806 t df 3.4069707615721128
  pairs [(0, 0, 0.06252431881237261), (1, 1, 0.06252431881237261)]
  roots (modulus, degrees): AR [(0.932, -154.7), (0.932, 154.7), (0.465, 180.0)] MA [(0.885, -152.1), (0.885, 152.1), (0.683, 180.0), (0.155, 0.0)] | AR-MA distances [[0.063, 0.815, 0.429, 1.074], [0.815, 0.063, 0.429, 1.074], [0.522, 0.522, 0.218, 0.62]]
  rows 2036 2015-01-05 2023-02-03 QQ lowest {'sample': -6.615872775049528, 't_theoretical': -8.080082905826078, 'theoretical': -3.397206692243049} highest {'sample': 5.165649608467589, 't_theoretical': 8.138451225413597, 'theoretical': 3.397206692243049}
  statsmodels df_adjust model_df 8 p+q 7 lag-10 stat, p [4.821100603872889, 0.08976588263871053]
  se opg {'x1': 0.0004, 'ar.L1': 0.166, 'ar.L2': 0.293, 'ar.L3': 0.1528, 'ma.L1': 0.1693, 'ma.L2': 0.2944, 'ma.L3': 0.1566, 'ma.L4': 0.0185, 'sigma2': 0.0}
  se oim/opg {'x1': 0.95, 'ar.L1': 1.33, 'ar.L2': 1.32, 'ar.L3': 1.32, 'ma.L1': 1.3, 'ma.L2': 1.3, 'ma.L3': 1.32, 'ma.L4': 1.37, 'sigma2': 1.55}
  se approx/opg {'x1': 0.95, 'ar.L1': 1.44, 'ar.L2': 1.45, 'ar.L3': 1.45, 'ma.L1': 1.41, 'ma.L2': 1.42, 'ma.L3': 1.42, 'ma.L4': 1.37, 'sigma2': 1.55}
  se robust/opg {'x1': 0.95, 'ar.L1': 1.9, 'ar.L2': 1.87, 'ar.L3': 1.86, 'ma.L1': 1.81, 'ma.L2': 1.8, 'ma.L3': 1.86, 'ma.L4': 1.99, 'sigma2': 2.69}
  z with robust se {'x1': 2.4, 'ar.L1': -6.82, 'ar.L2': -3.01, 'ar.L3': -1.42, 'ma.L1': 6.83, 'ma.L2': 2.83, 'ma.L3': 0.85, 'ma.L4': -2.25, 'sigma2': 18.38}
bic [2, 1, 2] n gap 6.476057023974136e-08 iter 1 aic -10433.809313776128
  params (name, value, se, z, p) [('ar.L1', -1.792, 0.024, -74.78, 0.0), ('ar.L2', -0.9211, 0.0231, -39.79, 0.0), ('ma.L1', 1.751, 0.0302, 57.98, 0.0), ('ma.L2', 0.8643, 0.029, 29.77, 8.78e-195), ('sigma2', 0.0003464, 6.66e-06, None, None)]
  burned [{'date': '2015-01-02', 'resid': 3.1851847171036805, 'resid_std': 0.003185184716536415}] max|resid| after 0.11882428737665762
  LB [(5, 4, True, 0.01817317076016588), (10, 4, True, 0.039189106473483816), (20, 4, True, 0.08368482694346832)]
  JB {'kurtosis': 7.196920854815583, 'p_value': 0.0, 'skew': -0.2758728861700408, 'statistic': 1520.0918569950813} ARCH [(5, 6.743634058855572e-49), (10, 4.66281843758333e-53)] {'arch': 'found', 'normality': 'rejected', 'serial_correlation': 'found'}
  acf past band 3 squared 28 band 0.043436938124839806 t df 3.373765469650318
  pairs [(0, 0, 0.03714137781015551), (1, 1, 0.03714137781015551)]
  roots (modulus, degrees): AR [(0.96, -159.0), (0.96, 159.0)] MA [(0.93, -160.3), (0.93, 160.3)] | AR-MA distances [[0.037, 0.658], [0.658, 0.037]]
  rows 2036 2015-01-05 2023-02-03 QQ lowest {'sample': -6.384448657076929, 't_theoretical': -8.10013315576893, 'theoretical': -3.397206692243049} highest {'sample': 5.341296365881514, 't_theoretical': 8.249159662865125, 'theoretical': 3.397206692243049}
  statsmodels df_adjust model_df 4 p+q 4 lag-10 stat, p [13.253038055111807, 0.039189106473483816]
  se opg {'ar.L1': 0.024, 'ar.L2': 0.0231, 'ma.L1': 0.0302, 'ma.L2': 0.029, 'sigma2': 0.0}
  se oim/opg {'ar.L1': 1.15, 'ar.L2': 1.16, 'ma.L1': 1.19, 'ma.L2': 1.22, 'sigma2': 1.63}
  se approx/opg {'ar.L1': 1.7, 'ar.L2': 1.47, 'ma.L1': 1.87, 'ma.L2': 1.71, 'sigma2': 1.63}
  se robust/opg {'ar.L1': 1.44, 'ar.L2': 1.43, 'ma.L1': 1.56, 'ma.L2': 1.64, 'sigma2': 2.85}
  z with robust se {'ar.L1': -51.77, 'ar.L2': -27.82, 'ma.L1': 37.16, 'ma.L2': 18.16, 'sigma2': 18.23}
course [0, 1, 1] n gap None iter 2 aic -10395.390686176892
  params (name, value, se, z, p) [('ma.L1', -0.07881, 0.0145, -5.42, 5.96e-08), ('sigma2', 0.000354, 6.41e-06, None, None)]
  burned [{'date': '2015-01-02', 'resid': 3.1851847171036805, 'resid_std': 0.0031851847165363504}] max|resid| after 0.1294507865244965
  LB [(5, 1, True, 0.2389042485494634), (10, 1, True, 6.56301653044273e-08), (20, 1, True, 1.5286148006141465e-08)]
  JB {'kurtosis': 7.764263374492483, 'p_value': 0.0, 'skew': -0.2609865849434356, 'statistic': 1948.677783205106} ARCH [(5, 7.240202735586895e-54), (10, 3.602642538049152e-60)] {'arch': 'found', 'normality': 'rejected', 'serial_correlation': 'found'}
  acf past band 10 squared 26 band 0.043436938124839806 t df 3.2392342696213836
  pairs []
  roots (modulus, degrees): AR [] MA [(0.079, 0.0)] | AR-MA distances []
  rows 2036 2015-01-05 2023-02-03 QQ lowest {'sample': -6.879924527158211, 't_theoretical': -8.4622031932605, 'theoretical': -3.397206692243049} highest {'sample': 5.568448696063404, 't_theoretical': 8.612384444886434, 'theoretical': 3.397206692243049}
  course-style QQ (resid whole): top 3.1851847171036805 next 0.10477441439673196 | drift cell aic -10398.937029014745
course [0, 1, 1] True -11693.89801005583 [{'name': 'intercept', 'value': 0.0009096594884237003}, {'name': 'ma.L1', 'value': -0.07611925438036903}, {'name': 'sigma2', 'value': 0.0003328096722259158}] {'order': [0, 1, 1], 'trend': 't', 'with_intercept': True} True 2264 227
drift dropped {'aic_gap': 3.546044937789702, 'aic_with_drift': -10398.936731114682, 'aic_without_drift': -10395.390686176892, 'drift': 0.0008992935291032927, 'drift_p_value': 0.020626214220511165, 'drift_std_err': 0.0003885044460242766, 'refit_trend': 'n', 'selected_trend': 't'}
clustering {'acf_squared_expected_by_chance': 2.5, 'acf_squared_outside_count': 29, 'arch_lm_rejections': 2, 'confirmed': True, 'model_id': 'aic'}
simulated restart gain 5.3958085572958225e-06
three residuals files together 1450049
corpus [(('fit', False), 88), (('fit', True), 13), (('residuals_aic', False), 20), (('residuals_aic', True), 4)] 413 cases, 8 token cases
app/dist/assets/FitView-B65sdK1J.js 41302 bytes
app/dist/assets/index-9a0aKoLw.js 227091 bytes
```

`sigma2`'s z and p-value are `None`: the fix round exports them as null (a boundary null,
Review fix round). The `se opg` lines are rounded to four decimals for display, which shows the drift's and
`sigma2`'s errors as 0.0004 and 0.0; their full values are in `fit.json` (0.000394 and 6.95e-06).
The implied forecast variance of the burned residual is (resid / resid_std)², computed from the
`burned` row above. The milestone-3 payload time came from a separate one-liner: `fit_payloads` on
`table_from_prices(prices)` and the committed grid, timed with `time.perf_counter()`; it printed
`fit_payloads: 1.20 s; equal to the committed files: True`. The export time is from the run that wrote
the committed files (its log printed `real 9m42.006s`, `user 90m52.099s`); milestone 2's 491 s is
the coordinator's measurement, recorded in the milestone-2 walkthrough. The app numbers are from the
gate's `npm run build` (Vite's gzip figure as it printed it); this probe measured the bytes of the
files that build wrote.

The simulations of concept notes 08 and 09 (Ljung–Box with and without p + q, the ARMA(1, 1)
spread as two roots approach each other) are in those notes, with their script and output.

### Mutation testing

A *mutant* is a deliberately broken copy of the code. A test that fails *kills* it. The Python
mutants ran on a scratch copy. The app mutants were applied in the working tree, and each file was
restored and compared byte for byte with its backup.

**Python:**

Run on a scratch copy of the working tree (a `git clone` with the tree copied over it) by a harness
that applies one textual change, runs the named tests, expects a failure, restores the file and
checks its hash. Baseline on the unchanged copy: the targeted tests pass (`33 passed` for
`tests/test_diagnostics.py` and `tests/test_payloads_fit.py`, and the full suite in the gate table).

| # | File | Mutation | What fails |
|---|---|---|---|
| 1 | `diagnostics.py` | `burn_in` returns 0 (no burn-in drop) | `test_the_burn_in_is_d_and_matches_statsmodels_own_rule[1]` |
| 2 | `diagnostics.py` | `burn_in` uses `nobs_diffuse` alone (0 here) | the same test |
| 3 | `diagnostics.py` | Ljung–Box called with `model_df = 0` instead of p + q | `test_model_diagnostics_shapes_and_the_dropped_residual` |
| 4 | `diagnostics.py` | `acorr_ljungbox` without `model_df` | `test_ljung_box_uses_p_plus_q_degrees_of_freedom_and_skips_lags_it_cannot_test` |
| 5 | `diagnostics.py` | a lag equal to p + q counted as applied (`>=`) | the same test, after the fix below |
| 6 | `diagnostics.py` | the outside flag compares the signed value with the band | `test_the_acf_band_is_the_white_noise_band_and_a_negative_spike_is_flagged` |
| 7 | `diagnostics.py` | the band uses 1.96 instead of z | the same test |
| 8 | `fitting.py` | the cancelling threshold made exclusive (`gap >= distance` stops) | `test_cancelling_pairs_follow_the_stated_rule` |
| 9 | `fitting.py` | cancelling pairs not one to one | the same test |
| 10 | `fitting.py` | one-sided p-value | `test_parameter_rows_define_z_p_and_the_interval_and_agree_with_statsmodels` |
| 11 | `fitting.py` | the grid llf gap never checked | `test_a_grid_cell_refits_to_the_grid_llf_and_a_wrong_record_is_refused` |
| 12 | `fitting.py` | the course refit keeps a drift (`trend='t'`) | `test_the_course_refit_drops_the_drift_at_d_1` |
| 13 | `payloads.py` | `validate_residuals` skips the outside-against-band check | `test_python_refuses_residuals_that_break_a_statistical_rule[an outside flag against its band]` |
| 14 | `payloads.py` | `validate_fit` skips the cancelling-rule check | `test_python_refuses_a_fit_that_breaks_a_statistical_rule[a pair the rule does not make]` |
| 15 | `payloads.py` | `validate_fit` skips `applied == (lag > model_df)` | `test_a_ljung_box_row_applied_against_its_lag_is_named_for_that_rule`, after the fix below |
| 16 | `tools/export_app_data.py` | `--only` writes every file | `test_only_rewrites_the_named_files_from_the_committed_grid` |

**Two survived the first run** (14 of 16 killed), and each led to a test change, not a code change:

- **Mutant 5** survived because the Ljung–Box test used lags 5, 10 and 20 with model_df 7, so no lag
  sat on the boundary. The test now also asks for lags 10 and 11 with model_df 10, and expects lag 10
  not to be applied.
- **Mutant 15** survived the shared corpus: in every corpus case that flips `applied`, the df and
  p-value null rules also break, so the file is refused anyway and only the message differs. A
  Python test now checks that the applied rule itself names the problem.

Re-run: both killed. All 16 killed, every file restored to its hash. Together with the six app
mutants below, 22 mutants, all killed.

**App** (each mutant restored afterwards; the suite was green again after each):

| # | Mutation | What fails |
|---|---|---|
| a | `FitView` ignores the exported `outside` flag and compares \|acf\| with the band itself | "draws an ACF bar as past the band exactly when Python flagged it" (`FitView.test.tsx`) |
| b | `parseResiduals` accepts any model id | "refuses the file of another model" (`contract.fit.test.ts`) and the corpus case "residuals_aic: the model_id of another model" |
| c1 | `parseFit`'s check of the model ids' order disabled | the corpus case "fit: model ids out of order" |
| c2 | `parseFit`'s check of the parameter names disabled | the corpus case "fit: parameter names in the wrong order" |
| d1 | the Ljung–Box reading ignores the verdict | "reads each test by the verdict Python exported, not by its p-values" (`FitView.test.tsx`) |
| d2 | every AR × MA combination ringed as a cancelling pair | "marks the cancelling pairs Python exported, and only those" (`FitView.test.tsx`) |

All six app mutants are killed.

### Gate results

Both trees on 2026-10-29: the working tree (with the raw snapshot under `data/`), and a fresh
`git clone` of `d0051d1` with the working tree copied over it minus every ignored file (so no
`data/`), its own `uv sync --frozen` and `npm ci`. The machine was shared with other jobs, so the
times are wall clock under load.

| Gate | Command | Full tree | Fresh clone |
|---|---|---|---|
| Python tests | `uv run pytest -q` | `1380 passed in 380.27s` | `1379 passed, 1 skipped in 590.44s`; the skip is `tests/test_config.py:224`, "this checkout is named 'clone', so its parent puts data elsewhere" |
| Notebook sync | `uv run python tools/build_notebooks.py --check` | `notebooks are in sync` | `notebooks are in sync` |
| App gate | `cd app && npm run verify` | lint clean; `Test Files  43 passed (43)`, `Tests  1082 passed (1082)` | the same |
| App coverage | same | statements 96.34% (2374/2464), branches 91.72% (2173/2369), functions 99.28% (417/420), lines 99.37% (1913/1925) | the same numbers |
| App build | same | `index` 227.13 kB (gzip 72.88 kB), `FitView` 38.94 kB (gzip 12.18 kB), three.js chunk 1,081.29 kB (its size warning predates this milestone) | the same |
| Export check | `VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py --check` | `app data is current: meta, prices, eda, stationarity, acf_pacf, aic_grid, fit, residuals_aic, residuals_bic, residuals_course (schema_version, artifact and data compared; generated_at and source_commit are not)`, exit 0, 9 min 26.7 s | without a snapshot: exit 2, "no complete snapshot". With `VOL_DATA_DIR` pointed at the full tree's snapshot (outside the clone): the same "app data is current" line, exit 0, 11 min 15.6 s |
| Full export | `time (OPENBLAS_NUM_THREADS=1 VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py)` | 9 min 42.0 s; the six milestone-2 files changed only in their envelopes | not run |
| Data rule | `uv run pytest -q tests/test_repo_data.py` | part of the 1380 | part of the 1379 |
| Cite script | `check_cites.py` on every doc this milestone touched | `problems: 0` for this walkthrough, concept notes 07, 08 and 09, the milestone-2 walkthrough, README and LEARNING_LOG. `contract.md` reports 4 and ADR-0002 55, the same counts as at `d0051d1`: every one is a cite into an installed package (statsmodels, pmdarima, pandas, yfinance), which the script looks for in the repo; those were checked against the installed files | not run separately (same text) |

**The first full-tree run failed twice** (`2 failed, 1378 passed in 494.14s`). Two older tests
named the milestone-2 artifact list or the old `build_payloads` signature:
`tests/test_provenance.py` compared the exported file names with a literal list of six, and
`tests/test_export.py`'s NaN test replaced `build_payloads` with a one-argument stand-in, which the
tool now calls with `aic_grid=`. Both now follow `export.ARTIFACTS`; the NaN test also puts its NaN in
the last payload, as its comment always claimed. The runs in the table are after that fix.

The corpus gained 102 cases in this milestone: 81 for `fit` (10 valid, 71 invalid) and 21 for
`residuals_aic` (3 valid, 18 invalid), 390 in all, plus 8 token cases (6 before). Both readers run
every case.

### Review fix round

Two adversarial reviews (statistics; code, contract and app) and the coordinator's own look at the
page in a real browser found what follows wrong; the coordinator re-ran the main refutations before
this round. Each fix was measured with the command shown, and each new test was shown to fail on a
mutant (the table after the list). The first build's tables above are kept as they were, except
where a number changed.

1. **The standard-error explanation was wrong.** This walkthrough and concept note 09 said OPG
   understates the AR and MA errors because the residuals are fat-tailed. With independent shocks the
   information-matrix equality holds for the AR and MA coefficients whatever the kurtosis; kurtosis
   moves only `sigma2`'s error. What makes the sandwich errors 1.80 to 1.99 times OPG here is
   dependence in the order of the shocks, consistent with volatility clustering (the pitfall row "OPG
   errors assume no volatility clustering" has the evidence), and the sandwich needs only the
   conditional mean to be right. Concept note 09 now says so and shows a seeded simulation
   (`cov_probe.py`): independent Student-t(3.4) shocks give a sandwich-to-OPG ratio of 0.96 for an AR
   coefficient, GARCH(1, 1) shocks 1.75.
2. **"The refits are the grid's maxima" was false for the BIC choice.** The 1e-6 guard shows that the
   recorded point is reproduced, not that it is a maximum. Restarted there, Nelder–Mead gains 1.27e-4
   for the BIC choice (Powell 1.24e-4) and nothing for the AIC choice (Powell 1.8e-8), by the probe
   below. The wording is fixed here, in `fitting.py`'s docstrings and in notebook 03.
3. **BIC's Ljung–Box "found" is fragile.** It rests on the unadjusted any-lag rule: per-lag p 0.018
   (lag 5) and 0.039 (lag 10); Holm's adjustment across its three applied lags gives 0.0545 at the
   smallest; a Box–Pierce statistic robust to the clustering (each squared autocorrelation divided
   by its own variance estimate, the mean of e(t)² e(t − k)² over the squared variance) gives 0.117,
   0.384 and 0.566. The course model still rejects (0.0048 at lag 10). The rule is kept; this walkthrough,
   ADR-0002 and the app's reading ("at least one lag rejects at 5%, unadjusted for testing several
   lags") now say it is unadjusted.
4. **The cancelling pairs were closest first, not a maximum matching.** AR {0.5, 0.6} and MA {0.51,
   0.41} gave one pair where two exist within 0.1. `cancelling_pairs` now takes the matching with the
   most pairs, then the least total distance; Python's validator restates the rule by dynamic
   programming. On AAPL the pairs are unchanged; `CANCEL_DISTANCE` stays 0.1.
5. **The validators let inconsistent files through, and could be made to crash.** Each test's
   p-value is now tied to its statistic (Ljung–Box on `df`; Jarque–Bera on 2; ARCH-LM on the number
   of lags, which is what `het_arch` uses: `acorr_lm` takes `stats.chi2.sf(lm, usedlag)`, and ddof
   only scales the statistic), to 1e-9 relative, with a 1e-300 floor where a p-value underflows; each
   statistic is ≥ 0 and the kurtosis ≥ 1; the drift's error and p-value are null together, the error
   is positive, and the p-value is tied to drift / error; `selected_trend` equals
   `full_series.trend`; the course model's trend is statsmodels' default at its d; BIC and AICc are
   tied to llf, k and `nobs_effective` like AIC (the made-up fixture's AICc was undefined, n − k − 1 =
   0, so it now has 10 training rows); the burn is at most 2; `primary` must be `"aic"`. Both readers
   bound p and q (≤ 10) and d (≤ 2) before they build anything from an order: an order of 10⁸ had
   made Python raise `MemoryError` and the app run out of heap, and 2³² a `RangeError`; each now gives
   one short problem. The export tool checks `fit.json` against the residual files before and after
   writing, `--only` included. The corpus gained 23 cases (413 in all), and
   `tests/test_payloads_fit.py` went from 22 tests to 53.
6. **`sigma2`'s z-test is a boundary null, and the page printed a bare "0".** `fit.json` now holds
   `sigma2`'s z and p-value as null (the only change to the exported data: the other nine files are
   equal to the first build's, apart from their envelopes); the table shows a dash and a note. A
   p-value that underflows to 0.0 prints "< 1e-300", and powers of ten are set with a superscript.
7. **The page could hang, and two sizes were wrong in a real browser.** A parser that throws now
   gives an error state instead of "loading" for ever, and a failed residual file is fetched again on
   the next pick. The legend icons had drawn at 300 × 300 px and the QQ plot at 927 × 579 px with
   oversized text.
8. **Mutants survived.** The reviews found tests that passed with the code broken: the llf guard's
   tolerance and direction, the burned residual fed to one diagnostic, ARCH-LM's ddof, `all()` for
   `any()`, `same_order` without the intercept, the validator's ARCH check (its test case had no
   message to check), crossed verdict wires on the page, the not-tested text, the badge colour, a
   zeroed drift row, and the burned residual in the largest |residual|. Each now has a test that
   fails on its mutant (below).
9. **Notes.** `contract.md` said `fit.json` holds "never a price"; the burned residual is about the
   first log price and is exported so the page can show it. `diagnostics.py` called ddof = 0 "the
   docstring's option"; it is `het_arch`'s default, and its docstring recommends p + q for ARMA
   residuals: with p + q the AIC choice's ARCH-LM p-values are 3.6e-50 and 4.1e-53, the same
   verdict. Concept note 09 now gives the main reason the extra AR and MA factors cancel (daily
   returns are close to white noise). One residual-ACF bar of the AIC choice, lag 18, is 8.7e-5 past
   its band, so another BLAS could flip that flag.
10. **Defaults**, recorded in LEARNING_LOG for the owner to override: `CANCEL_DISTANCE` 0.1 as a
   display rule (now a maximum matching), OPG errors on the page and the robust ones in the docs,
   Ljung–Box `model_df` = p + q, and the per-lag Ljung–Box verdict, unadjusted.

**The fix round's probe**, `m3_fix_probe.py`, run from the repository root with
`OPENBLAS_NUM_THREADS=1 .venv/bin/python -I m3_fix_probe.py` (6.8 s). It reads the committed files:

```python
import json, warnings
import numpy as np
from scipy import stats
from statsmodels.stats.diagnostic import het_arch
from arima_forecasting import selection
warnings.simplefilter("ignore")
D = "app/public/data/"
load = lambda name: json.load(open(D + name + ".json"))["data"]
fit, grid = load("fit"), load("aic_grid")
y = np.array([r["log_close"] for r in load("prices")["rows"] if r["segment"] == "train"])
cells = {(c["d"], c["p"], c["q"], c["trend"]): c for c in grid["cells"]}
# 1. Is the recorded point a maximum? Restart other optimisers there (tight tolerances).
for m in fit["models"][:2]:
    p, d, q = m["order"]
    cell = cells[(d, p, q, m["trend"])]
    model = selection._model(y, d, p, q, m["trend"])
    x0 = np.array([cell["params"][name] for name in model.param_names])
    for method, kw in (("nm", {"maxiter": 20000, "xatol": 1e-10, "fatol": 1e-12}), ("powell", {"maxiter": 20000, "xtol": 1e-10, "ftol": 1e-13})):
        r = model.fit(start_params=x0, method="statespace", method_kwargs={"method": method, "disp": False, **kw})
        print(f"{m['id']} restart {method}: llf gain {r.llf - cell['llf']:+.3e}, largest parameter move {np.max(np.abs(r.params - x0)):.1e}")
# 2. Ljung-Box with several lags: Holm's adjustment, and a heteroskedasticity-robust Box-Pierce.
for m in fit["models"]:
    lb = sorted((r["p_value"], r["lag"]) for r in m["diagnostics"]["ljung_box"] if r["applied"])
    holm = {lag: min(1.0, max(lb[i][0] * (len(lb) - i) for i in range(j + 1))) for j, (_, lag) in enumerate(lb)}
    e = np.array([r["resid_std"] for r in load("residuals_" + m["id"])["rows"]])
    e, n = e - e.mean(), len(e)
    g0, pq = np.mean(e * e), m["order"][0] + m["order"][2]
    rows = []
    for h in (5, 10, 20):
        r2 = [(np.sum(e[k:] * e[:-k]) / n / g0) ** 2 for k in range(1, h + 1)]
        tau = [np.mean(e[k:] ** 2 * e[:-k] ** 2) / g0**2 for k in range(1, h + 1)]
        Q = float(n * sum(a / b for a, b in zip(r2, tau)))
        robust = None if h <= pq else float(f"{stats.chi2.sf(Q, h - pq):.3g}")
        plain = next((p for p, lag in lb if lag == h), None)
        rows.append((h, None if plain is None else float(f"{plain:.3g}"), None if plain is None else float(f"{holm[h]:.4g}"), round(Q, 3), robust))
    print(f"{m['id']} Ljung-Box (lag, p, Holm-adjusted p, robust Q*, robust p): {rows}")
# 3. ARCH-LM with ddof = p + q (het_arch's docstring) beside ddof = 0; the residual ACF bar closest to its band.
for m in fit["models"]:
    res = load("residuals_" + m["id"])
    e = np.array([r["resid_std"] for r in res["rows"]])
    pq = m["order"][0] + m["order"][2]
    rows = [(k, het_arch(e, nlags=k, ddof=0, result_object=True).lmpval, het_arch(e, nlags=k, ddof=pq, result_object=True).lmpval) for k in (5, 10)]
    near = min(res["acf"]["rows"], key=lambda r: abs(abs(r["acf"]) - res["acf"]["band"]))
    print(f"{m['id']} ARCH-LM p (lags, ddof 0, ddof {pq}) {[(k, float(f'{a:.3g}'), float(f'{b:.3g}')) for k, a, b in rows]}; ACF bar nearest its band: lag {near['lag']}, |acf| - band {abs(near['acf']) - res['acf']['band']:+.2e}, outside {near['outside']}")
```

It printed:

```text
aic restart nm: llf gain -5.457e-12, largest parameter move 1.3e-15
aic restart powell: llf gain +1.787e-08, largest parameter move 6.3e-07
bic restart nm: llf gain +1.267e-04, largest parameter move 1.7e-04
bic restart powell: llf gain +1.243e-04, largest parameter move 5.4e-05
aic Ljung-Box (lag, p, Holm-adjusted p, robust Q*, robust p): [(5, None, None, 0.201, None), (10, 0.185, 0.3708, 2.425, 0.489), (20, 0.489, 0.4887, 7.773, 0.858)]
bic Ljung-Box (lag, p, Holm-adjusted p, robust Q*, robust p): [(5, 0.0182, 0.05452, 2.458, 0.117), (10, 0.0392, 0.07838, 6.358, 0.384), (20, 0.0837, 0.08368, 14.437, 0.566)]
course Ljung-Box (lag, p, Holm-adjusted p, robust Q*, robust p): [(5, 0.239, 0.2389, 2.327, 0.676), (10, 6.56e-08, 1.313e-07, 23.701, 0.0048), (20, 1.53e-08, 4.586e-08, 38.046, 0.00586)]
aic ARCH-LM p (lags, ddof 0, ddof 7) [(5, 2.36e-50, 3.57e-50), (10, 2.59e-53, 4.11e-53)]; ACF bar nearest its band: lag 18, |acf| - band +8.74e-05, outside True
bic ARCH-LM p (lags, ddof 0, ddof 4) [(5, 6.74e-49, 8.48e-49), (10, 4.66e-53, 6.06e-53)]; ACF bar nearest its band: lag 19, |acf| - band +1.41e-03, outside True
course ARCH-LM p (lags, ddof 0, ddof 1) [(5, 7.24e-54, 7.71e-54), (10, 3.6e-60, 3.88e-60)]; ACF bar nearest its band: lag 15, |acf| - band +2.31e-04, outside True
```

**The page in a browser.** With `npx vite --port 5191` serving the working tree, a script drove
playwright's cached headless Chromium over the DevTools protocol (a headless browser on this machine,
not the coordinator's own browser). At 1280 × 900: the three legend icons are 12 × 12 px, the unit
circle 300 × 300 px, the QQ plot 560 × 350 px with its tick text 14 px high (the full-width residual
plot beside it: 1,018 px, text 16 px). `sigma2`'s row reads `0.0003441`, `0.000006953`, `—`, `—†`,
`[0.0003304, 0.0003577]`, with the note below; the ARCH-LM p-values are set as `2.4 × 10<sup>−50</sup>`.
With `residuals_bic.json` answering 503 once, picking the BIC choice showed "Could not load
residuals_bic.json."; picking the AIC choice and then the BIC choice again fetched it a second time
and drew its plots. A `fit.json` with an AR order of 2³² showed one line, "data.models[0].order[0]:
expected an integer from 0 to 10, got 4294967296", not a page left loading. No exception reached the
console. At 375 × 812 the page has no horizontal scroll (scroll width 375), the icons are 12 px and
the QQ plot 293 px wide.

**Fix-round mutants.** The same harness as above, on a scratch copy, each file restored and its
hash checked: 55 Python mutants and 22 app mutants. 74 of the 77 were killed on the first run. The
three survivors were weaknesses of the new tests: the llf-guard test scaled its gaps by the constant
it tested, so a tolerance of 1e-4 or 5e-4 moved the gaps too (it now writes them from 1e-6), and no
case had two maximum matchings within the threshold with different totals (one now does). Re-run:
all 77 killed.

| Mutants | Mutation | What fails |
|---|---|---|
| F4a, F4b | `cancelling_pairs` closest first; or pairs past the threshold kept | `test_cancelling_pairs_are_a_maximum_matching_not_closest_first`; `test_cancelling_pairs_follow_the_stated_rule` |
| F4c to F4f | the validator skips the rule's count and total, the "above cancel_distance" check, the listing order; or its dynamic programming keeps the larger total | `test_the_cancelling_rule_is_a_maximum_matching_not_closest_first`, and the cases "a pair the rule makes, left out" and "pairs not listed by AR index" |
| F5b1 to F5b5 | `MAX_PQ` 11, `MAX_D` 3, the bound refusing its own value, the residual burn unbounded, the fit order unbounded (under a 4 GB limit) | `test_a_huge_order_gives_one_short_problem` (the last by `MemoryError`), `test_orders_at_the_bounds_are_not_refused_for_their_size`, corpus cases on the bounds |
| F5t1 to F5t14 | each p-value tie removed (Ljung–Box, Jarque–Bera, ARCH-LM, drift), ARCH-LM on lags + 1 df, the chi-squared series one term long, `P_FLOOR` 0 or 1e-290, statistic ≥ 0 or kurtosis ≥ 1 dropped, BIC with nobs + 1 or not tied, AICc with n − k, the undefined AICc not named | the named `FIT_CASES` rows, `test_a_p_value_that_underflows_to_zero_passes_within_the_floor`, `test_the_bases_are_valid`, `test_aicc_where_n_minus_k_minus_1_is_not_positive_is_refused` |
| F5s1 to F5s8 | `primary` any id, `sigma2` treated like the others or allowed a z and p, the drift's nulls or its error's sign not checked, `selected_trend` not tied, the course trend rule dropped, the default trend always `"n"` | the new corpus cases (both readers), and `test_the_bases_are_valid` |
| F5x1 to F5x4 | `validate_fit_residuals` skips `nlags` or a missing file; the tool's check before writing, or after it, removed | `test_a_residuals_file_that_contradicts_fit_is_named[nlags]`, `test_a_missing_or_extra_residuals_file_is_named`, `test_only_fit_refuses_to_write_beside_residual_files_that_contradict_it`, `test_the_tool_checks_the_fit_and_residual_files_again_after_writing` |
| F6a | `sigma2`'s z and p exported | `test_parameter_rows_define_z_p_and_the_interval_and_agree_with_statsmodels` |
| F8l1 to F8l5 | `LLF_TOLERANCE` 1e-4, 5e-4 or 1e-7; the guard one-sided either way | `test_the_llf_guard_refuses_a_gap_past_the_tolerance_on_either_side_and_only_then` |
| F8b1 to F8b7 | the unburned series fed to Ljung–Box, Jarque–Bera, ARCH-LM, QQ, the residual ACF or the squared ACF; the largest \|residual\| taken with the burned one | `test_every_diagnostic_leaves_the_burned_residual_out` |
| F8a1 to F8a5 | ARCH-LM `ddof=1`; the ARCH verdict by `all()`; `same_order` without the intercept; the validator's ARCH verdict check dropped; the drift row zeroed | `test_arch_lm_is_engles_n_r_squared_with_no_degrees_of_freedom_taken_off`, `test_verdicts_by_hand`, `test_same_order_compares_the_intercept_too[False-False]`, the case "an ARCH verdict against its p-values", `test_fit_models_fits_the_aic_bic_and_course_models` |
| T-b1 to T-b4 | the app's `MAX_PQ` 11, its bound refusing its own value, the residual burn unbounded, the order unbounded | "bounds p and q by 10 and d by 2", "bounds burn_excluded by d's bound, 2", corpus cases; the unbounded order crashes the test worker (heap out of memory) |
| T-s1 to T-s7 | the app's `primary`, `sigma2`, drift, `selected_trend` and course-trend rules, each removed or loosened | its unit test in `contract.fit.test.ts` and its corpus case |
| A2, A7, A8, A9 | the not-tested reading shows the not-found text; the ARCH badge colour inverted; the ARCH reading keyed by the normality verdict; the serial reading keyed by the ARCH verdict | "reads each test by its own exported verdict, with one verdict flipped at a time", "reads a model with no applied Ljung–Box lag as not tested" |
| T-p1 to T-p3, T-r1 | no superscript; an underflowed p printed "0"; the `sigma2` note dropped; the serial reading without "unadjusted" | the `FitView.test.tsx` and `fitText.test.ts` cases named for each |
| T-h1 to T-h3 | `useFitData` without `.catch`; a failed residual file cached; the old failure shown while it is fetched again | the three new `useFitData.test.tsx` cases |

**Fix-round gates**, on 2026-10-29, both trees as before (the clone is `d0051d1` with the working
tree copied over it, minus ignored files, so no `data/`; its own `uv sync --frozen` and `npm ci`).
After the clone was made, one message string in `payloads.py` and the docs changed; those files were
copied into the clone and its affected suites re-run (`718 passed`). The full-tree pytest ran twice,
the second time on the final code.

| Gate | Command | Full tree | Fresh clone |
|---|---|---|---|
| Python tests | `uv run pytest -q` | `1445 passed in 605.10s` (first run `1445 passed in 635.93s`) | `1444 passed, 1 skipped in 1016.85s`; the skip is `tests/test_config.py:224` (the checkout's name) |
| Notebook sync | `uv run python tools/build_notebooks.py --check` | `notebooks are in sync` | `notebooks are in sync` |
| App gate | `cd app && npm run verify` | lint clean; `Test Files  43 passed (43)`, `Tests  1121 passed (1121)`; 20 s | the same counts; 13 s |
| App coverage | same | statements 96.35% (2405/2496), branches 91.86% (2212/2408), functions 99.28% (419/422), lines 99.38% (1939/1951) | the same numbers |
| App build | same | `index` 227.09 kB (gzip 72.86 kB), `FitView` 41.30 kB (gzip 12.98 kB) | the same |
| Full export | `time (OPENBLAS_NUM_THREADS=1 VOL_DATA_DIR=$PWD/data .venv/bin/python tools/export_app_data.py)` | 6 min 4.1 s; only `fit.json`'s data changed (`sigma2`'s z and p) | not run |
| Export check | `VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py --check` | "app data is current: meta, …, residuals_course", exit 0, 9 min 11.6 s | without a snapshot: exit 2, "no complete snapshot"; with `VOL_DATA_DIR` at the full tree's snapshot: "app data is current", exit 0, 6 min 50.8 s |
| Cite script | `check_cites.py` on every doc this round touched | `problems: 0` for this walkthrough (130 cites), concept notes 08 (12) and 09 (11), LEARNING_LOG; `contract.md` 4 and ADR-0002 55, the same counts as before the round, all cites into installed packages | not run separately (same text) |

### Second review fix round

A re-review of the fix round, with its own probes and mutants, found what follows; the coordinator
confirmed items 1, 2 and 4 before this round. Each fix was measured with the command shown, and each
new test was shown to fail on a mutant (the table after the probes).

1. **The validator's root check grew like 2^k.** `_check_roots` flagged a root list whose length
   disagreed with the order but returned the roots anyway, and `_check_pairs` then ran its matching,
   a dynamic programme over every subset of the MA roots. A file with k equal roots a side and the
   order unchanged took 0.13, 0.38, 1.69 and 7.78 s at k = 12, 14, 16 and 18 (`roots_probe.py`
   below, run while the full export was busy): about 4.5 times as long for every two more roots.
   The docstring's "at most 2^MAX_PQ of them, since the orders are bounded first" was false:
   the orders were bounded, the root lists were not. Now a list of the wrong length is one problem
   and no roots come back, and the matching never runs on more than `MAX_PQ` roots a side (the case
   where the order is itself out of bounds, so there is no count to compare with). k = 1000 gives
   the two count problems in under a millisecond. The app's parser has no such loop: it reads each
   root once and checks the pair indices with two sets, and the page draws roots only from a file
   that parsed, so at most ten a side.
2. **A file could set its own tolerances.** `validate_fit` and `parseFit` took `llf_tolerance` and
   `cancel_distance` from the file they were checking, so a self-consistent file that stated
   `llf_tolerance` 1.0 beside a refit 0.5 from the grid's llf passed: the hole milestone 2 closed
   for `nesting_tolerance`. Both readers now hold 1e-6 and 0.1 themselves (`LLF_TOLERANCE` and
   `CANCEL_DISTANCE` in `payloads.py` and in `contract.fit.ts`; a test ties the Python pair to
   `fitting.py`) and refuse any other stated value. Four corpus cases (417 in all).
3. **The Jarque–Bera tie checked nothing on the shipped data.** The exported statistics are 1415.1,
   1520.1 and 1948.7, all above about 1382, where the chi-squared tail on 2 df is below `P_FLOOR`
   (1e-300); there the p-value tie passes any p below the floor, a p on the wrong df included. The
   statistic is now tied to n / 6 (S² + (K − 3)²/4) from the exported skew, kurtosis and n, to 1e-9
   relative (on the shipped files the difference is 0.0 for all three models), and the kurtosis must
   be at least 1 + skew², which every sample satisfies. A p below the floor computed on another df
   still passes; the statistic it stands beside can no longer be wrong. The made-up fixture's
   kurtoses changed to obey the tie (its statistics, p-values and skews are kept).
4. **A p-value of exactly 0 had no test.** The tie already refused a 0 beside a moderate statistic,
   but a mutant that let every 0 through survived. The rule now has its own branch and message: 0.0
   is taken only where the tail at that statistic and df is below `P_FLOOR`. Tests at Jarque–Bera
   1381 (tail 1.3e-300: refused) and 1382 (8.0e-301: taken), and a 0 beside a moderate statistic of
   each test.
5. **Three more impossible files passed Python.** A Ljung–Box Q below the Q of an earlier lag (Q is
   a running sum of terms ≥ 0, so it cannot fall), an ARCH-LM statistic above n − m − ddof (it is
   (n − m − ddof) R², and R² ≤ 1; the made-up fixture's 7.9 at 2 lags with n = 9 broke it and is now
   6.9), and a `sigma2` ≤ 0. Each is refused now, Python only.
6. **Three matching mutants survived.** `too_far` without its `1.0 +` (AR {0.5} against MA {0.9,
   0.5}: one pair by the rule, none under the mutant), and each of the validator's two threshold
   comparisons made exclusive. New tests: the pair at distance 0, and a pair exactly 0.1 apart
   (0.32 − 0.22 is the double 0.1) in both `tests/test_fitting.py` and `tests/test_payloads_fit.py`.
7. **`--only meta` had stopped working** in a folder without fit files: the first round's cross-file
   check refused it ("fit.json does not exist"). The check now runs only when the run writes a fit or
   residuals file or the folder already holds one.
8. **Text.** Concept note 09 said the drift's OPG error, like the AR and MA ones, holds for shocks
   "of any distribution". With skewed independent shocks it does not: the constant's sandwich error
   is 0.772 of OPG with centred chi-squared(4) shocks, where √(1 − γ²/(κ − 1)) gives 0.775. The note
   now says the AR and MA block is immune to the shock distribution, the drift is not (skew), and
   `sigma2` depends on the kurtosis, with that probe. The pitfall row above said the review "showed
   it is the clustering"; the evidence (`aapl_iid_probe.py` below) shows the inflation comes from
   the order of the shocks, as volatility clustering would give. ARCH-LM's statistic is (n − m) R²,
   m the number of lags, not n R² (`diagnostics.py` and the page now say so, as concept note 08 did).
9. **The first round's CSS fix had no test.** The legend icons now carry their size as an inline
   style besides their `width` and `height` attributes, and the QQ plot's container a `max-width`
   style; an inline style outranks `.plot svg`, and the view test reads both (jsdom loads no
   stylesheet).

**The root check, before and after.** `roots_probe.py`, run from the repository root as
`OPENBLAS_NUM_THREADS=1 .venv/bin/python -I roots_probe.py SRC 12 14 16 18`, with SRC a copy of the
first fix round's `src` folder, and then with SRC = `src` and `12 14 16 18 30 1000`:

```python
# validate_fit on the committed fit.json with k equal inverse roots on each side of the AIC choice
# (order unchanged, no pairs), timed. Usage: roots_probe.py SRC k [k ...], SRC the package's src folder.
import copy, json, sys, time
sys.path.insert(0, sys.argv[1])
from arima_forecasting.payloads import validate_fit
fit = json.load(open("app/public/data/fit.json"))["data"]
for k in map(int, sys.argv[2:]):
    bad = copy.deepcopy(fit)
    m = bad["models"][0]
    m["inv_roots_ar"] = [{"re": 0.5, "im": 0.0, "modulus": 0.5} for _ in range(k)]
    m["inv_roots_ma"] = [{"re": 0.5, "im": 0.0, "modulus": 0.5} for _ in range(k)]
    m["cancelling_pairs"] = []
    t = time.perf_counter()
    problems = validate_fit(bad)
    print(f"k={k}: {len(problems)} problems in {time.perf_counter() - t:.3f} s: {[p[:60] for p in problems]}")
```

It printed:

```text
== before: the first fix round's payloads.py ==
k=12: 3 problems in 0.133 s: ['data.models[0].inv_roots_ar: has 12 roots, expected 3', 'data.models[0].inv_roots_ma: has 12 roots, expected 4', 'data.models[0].cancelling_pairs: is [] (total distance 0), b']
k=14: 3 problems in 0.381 s: ['data.models[0].inv_roots_ar: has 14 roots, expected 3', 'data.models[0].inv_roots_ma: has 14 roots, expected 4', 'data.models[0].cancelling_pairs: is [] (total distance 0), b']
k=16: 3 problems in 1.688 s: ['data.models[0].inv_roots_ar: has 16 roots, expected 3', 'data.models[0].inv_roots_ma: has 16 roots, expected 4', 'data.models[0].cancelling_pairs: is [] (total distance 0), b']
k=18: 3 problems in 7.779 s: ['data.models[0].inv_roots_ar: has 18 roots, expected 3', 'data.models[0].inv_roots_ma: has 18 roots, expected 4', 'data.models[0].cancelling_pairs: is [] (total distance 0), b']
== after ==
k=12: 2 problems in 0.001 s: ['data.models[0].inv_roots_ar: has 12 roots, expected 3', 'data.models[0].inv_roots_ma: has 12 roots, expected 4']
k=14: 2 problems in 0.000 s: ['data.models[0].inv_roots_ar: has 14 roots, expected 3', 'data.models[0].inv_roots_ma: has 14 roots, expected 4']
k=16: 2 problems in 0.000 s: ['data.models[0].inv_roots_ar: has 16 roots, expected 3', 'data.models[0].inv_roots_ma: has 16 roots, expected 4']
k=18: 2 problems in 0.000 s: ['data.models[0].inv_roots_ar: has 18 roots, expected 3', 'data.models[0].inv_roots_ma: has 18 roots, expected 4']
k=30: 2 problems in 0.000 s: ['data.models[0].inv_roots_ar: has 30 roots, expected 3', 'data.models[0].inv_roots_ma: has 30 roots, expected 4']
k=1000: 2 problems in 0.000 s: ['data.models[0].inv_roots_ar: has 1000 roots, expected 3', 'data.models[0].inv_roots_ma: has 1000 roots, expected 4']
```

**Where the AR and MA inflation comes from.** `aapl_iid_probe.py` rebuilds the AIC choice from its
own standardised shocks, either resampled independently (kurtosis kept, order lost) or in their
original order, refits each, and compares the sandwich errors with OPG. Run from the repository root
with `OPENBLAS_NUM_THREADS=1 .venv/bin/python -I aapl_iid_probe.py` (17.4 s):

```python
# Does AAPL's own fat-tailed residual distribution, with the clustering removed (iid resampling),
# leave the AIC model's AR/MA sandwich-to-OPG ratio near 1? And with clustering kept (residuals in
# their original order, a "same shocks" refit), near the 1.8-1.99 measured?
import json, warnings
import numpy as np
from arima_forecasting import selection
warnings.simplefilter("ignore")
D = "app/public/data/"
load = lambda name: json.load(open(D + name + ".json"))["data"]
fit, grid = load("fit"), load("aic_grid")
y = np.array([r["log_close"] for r in load("prices")["rows"] if r["segment"] == "train"])
m = fit["models"][0]; p, d, q = m["order"]
cells = {(c["d"], c["p"], c["q"], c["trend"]): c for c in grid["cells"]}
cell = cells[(d, p, q, m["trend"])]
model = selection._model(y, d, p, q, m["trend"])
x0 = np.array([cell["params"][n] for n in model.param_names])
res0 = model.smooth(x0)
names = model.param_names
arma = [i for i, n in enumerate(names) if n.startswith(("ar.", "ma."))]
def ratios(res):
    se = {c: res.model.smooth(res.params, cov_type=c).bse for c in ("opg", "robust")}
    r = se["robust"] / se["opg"]
    return np.round(np.min(r[arma]), 2), np.round(np.max(r[arma]), 2), np.round(r[names.index("sigma2")], 2)
print("AAPL itself: ARMA ratio min, max; sigma2", ratios(res0))
e = np.asarray(res0.standardized_forecasts_error[0])[1:] * np.sqrt(x0[names.index("sigma2")])
rng = np.random.default_rng(1)
out = []
from scipy.signal import lfilter
phi = x0[[names.index(f"ar.L{i}") for i in range(1, p + 1)]]
theta = x0[[names.index(f"ma.L{i}") for i in range(1, q + 1)]]
beta = x0[names.index("x1")] if "x1" in names else 0.0
for rep in range(10):
    for kind in ("iid resample", "original order"):
        if kind == "iid resample":
            shocks = rng.choice(e, size=len(y) + 300, replace=True)   # kurtosis kept, clustering gone
        else:
            shocks = np.r_[rng.choice(e, size=301, replace=True), e]   # AAPL's own shocks in order (clustering kept)
            shocks = shocks[-(len(y) + 300):]
        w = lfilter(np.r_[1.0, theta], np.r_[1.0, -phi], shocks)[300:]
        sim = y[0] + np.cumsum(beta + w)
        ms = selection._model(sim, d, p, q, m["trend"])
        r = ms.fit(start_params=x0, method="statespace", method_kwargs={"method": "lbfgs", "maxiter": 500})
        out.append((kind, *ratios(r))); print(kind, rep, out[-1][1:], flush=True)
    if rep == 0:
        pass
for kind in ("iid resample", "original order"):
    arr = np.array([o[1:] for o in out if o[0] == kind], dtype=float)
    print(kind, "median over reps: ARMA min, max, sigma2", np.median(arr, axis=0))
```

It printed:

```text
AAPL itself: ARMA ratio min, max; sigma2 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 0 (np.float64(0.87), np.float64(0.96), np.float64(2.88))
original order 0 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 1 (np.float64(0.9), np.float64(0.95), np.float64(3.33))
original order 1 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 2 (np.float64(0.98), np.float64(1.14), np.float64(2.26))
original order 2 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 3 (np.float64(0.84), np.float64(1.04), np.float64(3.05))
original order 3 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 4 (np.float64(0.93), np.float64(0.96), np.float64(2.59))
original order 4 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 5 (np.float64(0.93), np.float64(0.96), np.float64(2.95))
original order 5 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 6 (np.float64(0.92), np.float64(1.07), np.float64(2.46))
original order 6 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 7 (np.float64(0.91), np.float64(1.03), np.float64(3.11))
original order 7 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 8 (np.float64(0.91), np.float64(1.11), np.float64(2.64))
original order 8 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample 9 (np.float64(0.92), np.float64(1.29), np.float64(3.1))
original order 9 (np.float64(1.8), np.float64(1.99), np.float64(2.69))
iid resample median over reps: ARMA min, max, sigma2 [0.915 1.035 2.915]
original order median over reps: ARMA min, max, sigma2 [1.8  1.99 2.69]
```

Resampled independently, the medians of the smallest and largest AR and MA ratios are 0.915 and
1.035; in their original order the same shocks give 1.80 to 1.99, the measured values. Fat tails
alone do not inflate the AR and MA errors on AAPL either; the dependence in the order of the shocks
does. `sigma2`'s ratio is large either way (medians 2.915 resampled, 2.69 in order): fat tails alone
inflate it.

**Second-round mutants.** A new harness (`mutants.py`, on a scratch copy, each file restored and its
hash checked; a control run with no mutant passes first): 28 Python mutants and 6 app mutants, all
34 killed.

| Mutants | Mutation | What fails |
|---|---|---|
| G1a, G1b, G1ab | a root list of the wrong length keeps its roots; the matching run past `MAX_PQ` roots; both (the re-reviewed code) | `test_no_matching_is_run_on_roots_of_the_wrong_count`; `test_no_matching_is_run_past_max_pq_roots_when_the_order_is_unknown` and `test_root_lists_longer_than_the_order_are_refused_at_once`, each stopped by its 10 s alarm |
| G2a to G2f | Python does not refuse a stated `llf_tolerance` or `cancel_distance`, or judges by the file's value; `LLF_TOLERANCE` 1e-5; `CANCEL_DISTANCE` 0.11 | `test_the_readers_tolerances_are_their_own_not_the_files`, the new corpus cases, `test_the_bases_are_valid` |
| T-G2a to T-G2c | the app does not refuse a stated value; its `LLF_TOLERANCE` 1e-5 or `CANCEL_DISTANCE` 0.11 | "pins llf_tolerance at 1e-6 and cancel_distance at 0.1, as fitting.py, and refuses any other stated value", the new corpus cases |
| G3a to G3d | the Jarque–Bera statistic not tied; the kurtosis bound back to 1; the tie without its 1/4, or with n + 1 | the cases "a Jarque-Bera statistic that is not n / 6 (S^2 + (K - 3)^2 / 4)" and "a Pearson kurtosis below 1 + skew^2"; `test_the_bases_are_valid` |
| N4, G4b | a p of 0 skips its tie; a 0 taken whatever the tail | `test_a_p_value_of_zero_is_taken_only_where_the_tail_is_below_the_floor` |
| G5a to G5g | Q may fall; Q may not stay level; the ARCH-LM bound dropped, made exclusive, or without ddof; `sigma2`'s sign unchecked; a `sigma2` of 0 allowed | the new `FIT_CASES` rows, `test_a_ljung_box_q_may_stay_level_from_one_lag_to_the_next`, `test_the_arch_lm_bound_is_n_minus_lags_minus_ddof_and_inclusive` |
| N1, N2, N3, N8 | `too_far` without `1.0 +`; the validator's dynamic programme or its pair check exclusive at the threshold; `cancelling_pairs` exclusive at it | `test_a_single_eligible_pair_at_distance_zero_is_found`; `test_a_pair_exactly_cancel_distance_apart_is_a_pair` (in `test_payloads_fit.py` for N2 and N3, in `test_fitting.py` for N8) |
| G7a, G7b | the cross-file check always (the first round's code); only when the run writes a fit or residuals file | `test_only_meta_into_a_folder_without_fit_files_writes_meta_as_before` |
| T-G9a to T-G9c | the legend icons without their inline size, or without `width` and `height`; the QQ container without its `max-width` | "sizes the legend icons and caps the QQ plot on the elements themselves, which no stylesheet rule outranks" |

**Second-round gates**, on 2026-10-29, both trees as before (the clone is `d0051d1` with the working
tree copied over it, minus ignored files, so no `data/`; its own `uv sync --frozen` and `npm ci`). The
clone was made before this table was written, so its copy of this walkthrough lacks the table; no
other file differs.

| Gate | Command | Full tree | Fresh clone |
|---|---|---|---|
| Python tests | `uv run pytest -q` | `1467 passed in 553.07s` | `1466 passed, 1 skipped in 791.53s`; the skip is `tests/test_config.py:224` (the checkout's name) |
| Notebook sync | `uv run python tools/build_notebooks.py --check` | `notebooks are in sync` | `notebooks are in sync` |
| App gate | `cd app && npm run verify` | lint clean; `Test Files  43 passed (43)`, `Tests  1127 passed (1127)`; 31 s | the same counts; lint clean; 17 s |
| App coverage | same | statements 96.35% (2407/2498), branches 91.86% (2212/2408), functions 99.28% (419/422), lines 99.38% (1941/1953) | the same numbers |
| App build | same | `index` 227.09 kB (gzip 72.87 kB), `FitView` 41.52 kB (gzip 13.09 kB) | the same |
| Full export | `time (OPENBLAS_NUM_THREADS=1 VOL_DATA_DIR=$PWD/data .venv/bin/python tools/export_app_data.py)` | 7 min 31.2 s; every file's data equal to the first fix round's, only `generated_at` changed | not run |
| Export check | `VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py --check` | "app data is current: meta, …, residuals_course", 9 min 41.2 s | without a snapshot: exit 2, "no complete snapshot"; with `VOL_DATA_DIR` at the full tree's snapshot: "app data is current", 7 min 40.0 s |
| Cite script | `check_cites.py` on every doc this round touched | `problems: 0` for this walkthrough (139 cites), concept notes 08 (12) and 09 (11), the milestone-2 walkthrough (132); `contract.md` 4, the same four cites into installed packages as before the round | not run separately (same text) |

### Third review fix round

A third review attacked the second round's fixes with its own probes (`fit_lags5.json`,
`dos_probe.py`, `chi2_probe.py`) and its own mutants (O1 to O6); the coordinator confirmed the crash in
item 2. It found one hole in the pinned values, one crash, one slow path and six mutants that
survived. Each fix was measured with the command shown, and each new test was shown to fail on its
mutant (the table after the list).

1. **A file chose its own Ljung–Box and ARCH-LM lags.** Round 2 pinned `llf_tolerance` and
   `cancel_distance` but left `ljung_box_lags`, `arch_lm_lags`, `nlags` and `arch_lm_ddof` to be read
   from the file under check, and the lags decide which rows exist, so which verdict is reached.
   The re-review's probe cut the shipped file's lags to `[5]` and kept the lag-5 rows: the course
   model's serial-correlation verdict went from "found" (its lag-10 p-value is 6.6e-08) to
   "not_found" and the AIC model's to "not_tested". On the second round's code `validate_fit` gave
   `[]` for it and `parseFit` returned `ok` with the verdicts `not_tested, found, not_found`
   (measured on a copy of the tree before this round). Both readers now hold `ALPHA` 0.05,
   `LJUNG_BOX_LAGS` (5, 10, 20), `ARCH_LM_LAGS` (5, 10), `ARCH_LM_DDOF` 0 and `NLAGS` 50 themselves
   (`src/arima_forecasting/payloads.py:1249`, `app/src/lib/contract.fit.ts:58`), compare a stated value
   exactly (one 1e-12 away is another value) and judge the rows against their own values whatever the
   file says. `tests/test_diagnostics.py:189` ties the Python pins to `diagnostics.py` and to the
   settings `residual_payloads` writes, and the real `fit.json` still has 0 problems. The made-up
   fixture had to change to satisfy the pins: ARCH-LM at 10 lags needs n − 10 ≥ its statistic, so
   `n_train` is 40 (nobs_effective and the diagnostics' n 39, BIC and AICc recomputed), the AIC model
   is ARIMA(3, 1, 2) so that its lag-5 Ljung–Box row is not applied, as the real AIC model's is, and
   every Ljung–Box and ARCH-LM row is scipy's tail of a made-up statistic. Twelve corpus cases were
   edited for the new numbers, and 129 of them were run on the old and the new fixture to compare
   which paths each reports: 7 report a different set of paths (side
   effects of the old n and lags gone or changed, and the two sigma2 cases moved with the index), and
   each still reports the rule it names. Six cases were added (423 in all), the re-review's flipped
   verdicts among them; both readers refuse `fit_lags5.json` itself.
2. **A statistic of 5e-324 crashed `validate_fit`, and a long lag stalled it.** `_chi2_sf` raised
   `ValueError: math domain error` for a Ljung–Box, Jarque–Bera or ARCH-LM statistic of 5e-324 (half
   of it rounds to 0.0, and `math.log(0.0)` raises), and it loops df / 2 times for a df read from
   the file. Measured on the old tree with the re-review's `dos_probe.py`: the three tiny-statistic
   cases raised; a Ljung–Box lag of 1e7 took 2.457 s and ARCH-LM lags of 1e7 took 2.492 s; the
   re-review's lag of 1e9 ran past `timeout 60`. Now the tail is computed only for a pinned lag with
   the df that lag gives (`payloads.py:1587` and `:1637`), so a row off the pins is a problem and its
   p-value is not tied, and a halved statistic of 0.0 gives a tail of 1 (`:1276`). After: all eight
   probe cases take 0.001 s or less, the tiny statistics give one "gives p = 1.0" problem each, and
   the lag of 1e9 gives its lag problems in 0.000 s.
3. **Six mutants survived**, each now killed by a test that states what it tests: O1 (the Jarque–Bera
   tie loosened to 1e-2) by a statistic 1e-6 relative off, whose p-value underflows to 0.0 so that
   only the formula sees it; O2 (1% slack on the kurtosis bound) by skew 3 with kurtosis exactly 10
   (valid) and 9.99999 (refused); O3 (the cross-file check looking for `fit.json` only) by `--only
   meta` beside a lone residuals file; O4 and O6 (pins compared within 1e-9) by pins 1e-12 away in both
   readers; O5 (Q monotone only between applied rows) by a lag-5 Q, not applied for the AIC model,
   above the lag-10 Q.

**Third-round mutants.** `mutants.py` (same method as round 2; a control run with no mutant passes
first, for the Python and the app tests): 35 mutants, all killed. The 33 round-2 mutants whose text
still exists were run again against the changed tests and all are killed (G5e's text changed; it is
G5e below).

| Mutants | Mutation | What fails |
|---|---|---|
| H1a, H1b | `ljung_box_lags` or `arch_lm_lags` read from the file, not refused (the re-reviewed code) | `test_a_file_cannot_change_a_verdict_by_stating_other_lags`, `test_a_stated_residual_test_setting_other_than_the_pinned_one_is_refused`, the corpus cases "ljung_box_lags [5] with every model's rows…" and "arch_lm_lags [5] with…" |
| H1c to H1e | a stated `arch_lm_ddof`, `nlags` or `alpha` not refused | `test_a_stated_residual_test_setting_other_than_the_pinned_one_is_refused`, `test_a_self_consistent_file_with_other_nlags_is_judged_at_the_pinned_one`, the corpus cases |
| H1f to H1j | a pinned constant changed (`LJUNG_BOX_LAGS` (5, 10, 21), `ARCH_LM_LAGS` (5, 11), `NLAGS` 49, `ALPHA` 0.01, `ARCH_LM_DDOF` 1) | `test_the_bases_are_valid` and about 40 more; `test_the_readers_pin_the_settings_the_exporter_writes` |
| T-H1a, T-H1b | the app does not refuse a stated lag list; or a stated alpha, ddof or nlags | "pins the residual tests’ settings as diagnostics.py, and refuses any other stated value", "refuses a file whose own lags give the course model another serial-correlation verdict", the corpus cases |
| T-H1c to T-H1g | the app's pinned constants changed (the same five) | the base fixture no longer parses: 47 failures, the pin test among them |
| T-H1h | the app compares a stated alpha, ddof or nlags within 1e-9 | "compares a stated pin exactly: a value 1e-12 away is another value and is refused" |
| H2a, H2b | a Ljung–Box or ARCH-LM tail computed whatever the row's lag and df | `test_a_lag_far_past_the_pinned_ones_never_reaches_the_chi_squared` (each runs 5 s, then the alarm stops it) |
| H2c, H2d | the Ljung–Box tail without its model_df condition, or without its pinned-lag condition | `test_a_ljung_box_row_whose_df_is_not_the_pinned_one_skips_the_p_value_tie`; the far-lag test |
| H2e, H2f | `_chi2_sf` without its guard, or guarding only 0 | `test_the_chi_squared_tail_of_zero_and_of_the_smallest_subnormals_is_one`, `test_a_statistic_of_zero_or_a_subnormal_has_a_p_value_of_one_and_never_raises` (for LB, JB and ARCH-LM) |
| O1 | Jarque–Bera tie at 1e-2 | `test_the_jarque_bera_statistic_is_tied_to_its_formula_to_a_part_in_a_billion` |
| O2 | kurtosis bound with 1% slack | `test_the_kurtosis_bound_is_1_plus_skew_squared_with_no_slack_to_speak_of` |
| O3 | cross-file check looks for `fit.json` only | `test_only_meta_into_a_folder_holding_only_a_residuals_file_still_runs_the_cross_file_check` (alone: `1 failed`) |
| O4 | app pins compared within 1e-9 | "compares a stated pin exactly: a value 1e-12 away is another value and is refused" |
| O5 | Q monotone only between applied rows | `test_a_ljung_box_q_at_a_lag_that_is_not_applied_may_not_exceed_a_later_one` |
| O6, O6b, O6c | Python pins (`llf_tolerance`, `cancel_distance`, the new ones) compared within 1e-9 | `test_a_stated_pin_one_part_in_a_trillion_away_is_refused` |
| G5c to G5e | the ARCH-LM bound dropped, made exclusive, or without ddof | `test_the_arch_lm_bound_is_n_minus_lags_minus_ddof_and_inclusive` (ddof is now the reader's own constant, so the test sets `ARCH_LM_DDOF` to 1 and checks the bound moves) |

**Third-round gates**, on 2026-10-29, full tree only (the brief asked for no fresh-clone run). The
machine was shared with other test runs, so the times are loose.

| Gate | Command | Result |
|---|---|---|
| Python tests | `OPENBLAS_NUM_THREADS=1 VOL_DATA_DIR=$PWD/data .venv/bin/python -m pytest -q` | `1506 passed in 321.69s` |
| Notebook sync | `.venv/bin/python tools/build_notebooks.py --check` | `notebooks are in sync` |
| App gate | `cd app && npm run verify` | lint clean; `Test Files  43 passed (43)`, `Tests  1136 passed (1136)`; 10 s |
| App coverage | same | statements 96.36% (2414/2505), branches 91.88% (2220/2416), functions 99.29% (421/424), lines 99.38% (1947/1959) |
| App build | same | `index` 227.09 kB (gzip 72.86 kB), `FitView` 41.89 kB (gzip 13.19 kB) |
| Export check | `VOL_DATA_DIR=$PWD/data .venv/bin/python tools/export_app_data.py --check` | "app data is current: meta, …, residuals_course", 401 s: the exported data did not change, so no re-export |
| Cite script | `check_cites.py` on every doc this round touched | `problems: 0` for this walkthrough (145 cites, the moved ones re-pointed by the text of the cited line) and concept note 09 (11); `contract.md` 4, the same four cites into installed packages as before the round |

---

## Explain it back

Answer out loud or on paper, without notes. Name files, lines and functions.

1. **The data flow.** Walk the training log closes from `fit_payloads` to the Fit page. Which rows
   does each of the three models see, and which step sees more? Name every check that could stop
   the export or the page, in Python and in the app.
2. **Refit, not fit.** Why are the AIC and BIC choices refitted from the grid's recorded estimates
   instead of fitted afresh? What does `LLF_TOLERANCE` guard, and what does it not prove (what did
   Nelder–Mead find at the BIC choice's point)? What does the simulated 5.4e-6 in
   `tests/test_fitting.py` show?
3. **The course's two problems.** How does `course_track` measure the leak and the dropped drift?
   On AAPL the leak changed nothing measurable: why is it still a flaw, and what would show it?
4. **The burned residual.** Why is the first residual 3.18 and its standardised value 0.0032? What
   would the course's QQ plot look like with it, and which statsmodels rule drops it?
5. **Degrees of freedom.** Why does Ljung–Box lose p + q degrees of freedom on residuals? What
   happens at lag 5 for the AIC choice? Why does statsmodels' own rule give 8, and does it change
   the verdict?
6. **Reading the tests together.** The AIC choice passes Ljung–Box and fails Jarque–Bera and ARCH-LM.
   What does the model get right, what does it miss, and what does that mean for the width of the
   forecast intervals in milestone 4?
7. **The unit circle.** Read the AIC choice's roots: where are they, what period does ±154.7°
   mean, and which pairs nearly cancel? Why do near-cancelling roots inflate standard errors, why
   does BIC's closer pair not do so, and why is `CANCEL_DISTANCE` a display rule and not a test?
   Why must the pairing be a maximum matching, not closest first?
8. **Which standard errors.** What does OPG estimate, and what must hold for OPG and the sandwich to
   agree on the AR and MA coefficients? The robust errors are up to twice OPG here: is that the fat
   tails or the volatility clustering, and which row of concept note 09's simulation tells you?
   Which of the AIC choice's coefficients would then not be called significant?
9. **A trade-off: the budget.** The residual series of three models are 1,450,049 bytes. Compare
   three files, one columnar file, and thinned rows: what does each cost the contract, the readers
   and the reader of the page?

---

## Concepts used

- [08 · Residual diagnostics](../concepts/08-residual-diagnostics.md)
- [09 · Parameter inference and root cancellation](../concepts/09-parameter-inference-and-root-cancellation.md)
- From milestone 2: [06 · ACF, PACF and their bands](../concepts/06-acf-pacf-and-their-bands.md) (why
  the band is too narrow for returns) and [07 · AIC within one d](../concepts/07-aic-within-one-d-and-the-landscape.md)
  (the prediction this milestone tests).
- From milestone 0: [00 · Background](../concepts/00-background.md) §5 to §7.

---

## What is next, and open decisions

**Milestone 4** forecasts the test period with the primary model: the course's static multi-step
forecast, a walk-forward one-step forecast and a random walk as the baseline, scored on both
windows. That is where the near-cancelling AIC choice meets data it did not see.

**Decided in this milestone:** the owner's default, recorded in LEARNING_LOG: fit all three models,
and the AIC choice is the primary model (the owner can override).

**Open, for the owner:**

- **Keep the BIC and course models in milestone 4?** The course model fails Ljung–Box in-sample
  clearly; the BIC choice fails it only narrowly, by the unadjusted any-lag rule (Holm-adjusted
  0.0545). In-sample fit is not forecast skill either way. Forecasting all three costs little and tests whether AIC's extra
  parameters pay off out of sample; forecasting only the primary model keeps the page simple.
- **Model the volatility clustering, or only report it?** Every model's residuals cluster. A GARCH
  layer would model it and change the forecast intervals; it is outside the course and outside
  ADR-0002. Reporting it, as now, keeps the scope.
- **`CANCEL_DISTANCE` is a display rule.** 0.1, now applied as a maximum matching, flags both
  models' complex pairs and not the AIC choice's real pair (0.218 apart). Whether to keep 0.1, drop
  the rule, or replace it with a test for a common factor is open.
- **Forecast intervals with the Student-t?** The residuals have kurtosis about 7 and a fitted t with
  df about 3.4. Normal intervals will be too narrow in the tails. Whether milestone 4's intervals
  should use the t fit (and say so) or the normal (the course's, and statsmodels' default) is open.
- **OPG standard errors** stay statsmodels' default and the course's. The robust errors are
  measured above; whether the page should show them beside OPG is open.
