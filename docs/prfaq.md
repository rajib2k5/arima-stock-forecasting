# PR/FAQ: arima-stock-forecasting

> **Status: milestone 5, results measured.** This document was written at milestone 0, working backwards from the launch, with no results in it. It is revised at milestone 5 with the measured answers: every number below is read from the committed files in `app/public/data/`, or measured by a command in the [milestone-5 walkthrough](milestones/05-where-the-sample-goes-wrong.md), and each one says where it lives. The quotes and the launch date are still placeholders, each marked **draft for owner review**: the owner writes them in their own words.

---

## Press release

### Does a textbook ARIMA forecast of Apple's stock beat a random walk? Not one day ahead, and a new open-source study shows every step of the answer

**For people learning time-series forecasting for quant interviews: a reproducible Python pipeline, an interactive app with 3D views, and concept notes that rebuild a common course project and measure what each of its mistakes costs.**

**[Launch date: draft for owner review]**. Today we release `arima-stock-forecasting`, a public repository that forecasts Apple (AAPL) daily closing prices with ARIMA models and asks the one question that decides whether a price forecast is any good: *does it beat a random walk?* A random walk is the simplest possible forecast, "tomorrow's price is today's price"; a model that cannot beat it has learned nothing. The study follows the ten-module structure of a widely used sample course (2015–2023 data, a 90/10 train/test split), then tests the same models on 2 January 2024 to 30 September 2026, 689 trading days on which no model, order or forecast was chosen (the inference method for the comparisons was chosen after milestone 4's results on them were seen). Every forecast is reported next to a random-walk baseline, on both periods, with the code behind each number one click away.

**What it found.** One day ahead, no ARIMA model has a lower RMSE than yesterday's price: on both windows every one-step forecast's dollar RMSE is 1.0056 to 1.0174 times the random walk's (`evaluation.json`, `metrics[].ratio_to_rw.usd_median.rmse`). The Diebold–Mariano verdicts in the same file, DM-HLN, per test, uncorrected (16 tests, each at 5%), are "worse than the random walk" in 5, all out of sample, "no difference" in 11, and "better" in none (`dm[].verdict`). In the simulated size check, DM-HLN rejected 4.35% to 26.65% of true nulls (it ignores autocorrelation), so each of those verdicts is one uncorrected test; after the corrected re-analysis below, 1 "worse" survives. The AIC model's static paths, the only ones with a drift, are far below their baseline (RMSE ratios 0.4134 on the test window and 0.5370 out of sample). A random walk carrying the same drift has an RMSE of $10.339 against the model's $10.632 on the same test path (milestone-4 walkthrough, "The two probes that separate causes"): one path each, not a test, which points to the drift in a rising market rather than the ARMA terms. The course's driftless static out-of-sample path is at 0.9991, a hair below 1. The one-step intervals were too wide in 2023 and about right from 2024: out of sample, the 95% intervals and the Student-t 80% interval are "consistent" for every model, the normal 80% interval "too wide" (`coverage[]`, Kupiec's test). The 32 Kupiec tests are per test, uncorrected: Holm's correction over the 32 keeps 13 of the 20 "too wide" verdicts (9 on test, 4 out of sample).

**The problem.** ARIMA stock-forecasting tutorials are everywhere. The sample course this project follows makes four mistakes that are common in them. Measured on AAPL (milestone-5 walkthrough, ["The mistakes and their costs"](milestones/05-where-the-sample-goes-wrong.md#the-mistakes-and-their-costs)):
1. It picks the model order on the whole series, test period included, so the test is no longer a test. On AAPL the leak cost nothing measurable: the search chooses the same ARIMA(0, 1, 1) with a drift with and without the test rows (`fit.json`, `course_track.same_order`). It is still a flaw in the procedure.
2. It forecasts the whole test period in one shot and calls the result a forecast. The course's path is a flat line at $151.47 for all 227 test days, while the price ranged over $52.74; its RMSE, $25.991, is 1.07% above that of a flat line at the last training close (`forecast_course_static.json`; `evaluation.json`, `metrics[course, static, test]`).
3. It reports an error in dollars with nothing to compare it to. Its $25.99 RMSE and 12.68% MAPE read like a result; the flat random walk scores $25.72 and 12.54% on the same days.
4. It exponentiates a log-price forecast and treats the result as the expected price. That is the median: at the end of the course's static paths the mean is 3.47% higher (test) and 10.91% higher (out of sample) (`metrics[course, static, *].back_transform.max_pct`).

Building the study found three more. The course's refit drops the drift its own search chose, which costs more than any of the four: with the drift, its static test RMSE would be $10.55 instead of $25.99 (`fit.json`, `course_track.drift_dropped`, and the walkthrough's probe). Its residual plots keep the first residual, which is the price level, not a shock: one point 24.6 times the size of any other, and a kurtosis of 1,774 instead of 7.76 (`fit.json`, `models[].diagnostics.burned`). And its code no longer runs as written: the forecast call raises an error on a trading-day date index, and the MAPE prints `nan` (`tests/test_forecasting.py`, `tests/test_evaluation.py`).

A learner who follows the course ends up with a model that runs, and cannot answer the first question an interviewer asks about it.

**The solution.** The repository rebuilds the course project module by module (data, preprocessing, EDA, stationarity, identification, split, fit, diagnostics, forecast, evaluation) in tested Python, and adds what the course leaves out:
- the model order, and its trend, are chosen on the training data only;
- the KPSS test is run alongside ADF, because the two have opposite null hypotheses;
- a walk-forward, one-step-ahead forecast is run alongside the course's static multi-step forecast;
- a random-walk baseline appears under every metric, with a Diebold–Mariano test and the coverage of the intervals;
- the [milestone-5 walkthrough](milestones/05-where-the-sample-goes-wrong.md) and [concept note 12](concepts/12-where-the-sample-goes-wrong.md) take each mistake in turn and measure what it costs.

Each milestone ships a code walkthrough with `file:line` references, concept notes with the maths, "predict before you look" questions to answer before reading the results, and "explain it back" interview questions that test whether the reader can explain the code and the maths without notes.

> "[Draft for owner review. Placeholder: the owner's quote, to be written by the owner. It should say why an honest negative result teaches more than a flattering one.]"
> — Project owner

**How it works.** Python does all the computing. A loader pulls AAPL prices from Yahoo Finance through `yfinance` into a local cache outside the repository, in the folder named by the `VOL_DATA_DIR` environment variable (default `~/data/vol-projects`); the raw download is never committed. The pipeline fits and evaluates the models and writes 18 versioned JSON files, each stamped with a schema version, a timestamp and the git commit that produced it. A React app reads only those files and draws them, recomputing nothing:
- a price and log-price explorer, with the training, test and out-of-sample segments;
- a stationarity page, with ADF and KPSS side by side for d = 0, 1 and 2, and the ACF and PACF of each;
- a 3D landscape of AIC over the model orders (p, q), with and without a drift;
- the fitted models with their parameters, inverse roots and residual diagnostics;
- the forecasts against the actual prices, with an animated walk-forward fan and every score beside the random walk's.

Notebooks are generated from the same source code, and a test fails if they drift from it. A test also fails if the README's results table and `evaluation.json` disagree.

> "[Draft for owner review. Placeholder: an illustrative learner persona's quote, not a real person. Example of the reaction we are aiming for: 'I finally understand why my ARIMA forecast was a flat line, and I can say in one sentence what that line means.']"
> — Hypothetical learner

**Get started.** Clone the repository, run `uv sync`, `uv run pytest -q` and `uv run python tools/results_table.py` (which prints the results tables from the committed data), then `cd app && npm ci && npm run dev`. The data the app reads is committed, so nothing needs downloading. Before you read any milestone's results, answer its predict-first questions in `docs/milestones/`.

---

## Inference robustness (corrected for 28 tests)

<!-- filled from docs/validation/m5-comparison-inference-v2.md -->

Every DM verdict in this document is DM-HLN, per test, with no correction for multiple tests. A pre-registered re-analysis ([plan v2](validation/m5-preregistration-v2.md), [results](validation/m5-comparison-inference-v2.md)) tests all 28 comparisons with the random walk again. It uses the EWC fixed-smoothing t test (ν = 14 on test, 31 on oos) and Holm's correction at 5%.

- **One verdict survives.** BIC's one-step forecast is worse than the random walk on the out-of-sample window under absolute loss (Holm p 0.0041).
- **The other 15 tested comparisons:** no difference detected. That is not "equal": the [minimum detectable effects](validation/m5-comparison-inference-v2.md#minimum-detectable-effects) say how large a difference each test could see.
- **A limit the size check did not cover.** The real out-of-sample loss differentials have heavier tails than any process in the simulated size check: for aic walk-forward under squared loss, the excess kurtosis is 135.3 and the top 5 days carry 67% of the squared deviations. So the out-of-sample squared-loss p-values are not reliable, and none survives the correction anyway. The surviving result is on absolute loss ([addendum](validation/m5-preregistration-addendum.md), §2).
- **The 12 static comparisons** are not tested: their errors come from one origin and accumulate.
- **How the test was chosen.** Plan v1's block bootstrap failed its size check on simulated data (9.70% against a limit of 8%) before any of its own results was computed. Plan v2 was frozen before its run, and its test passed (4.05% to 5.80% in all ten cells). Both plans wrongly said that no real statistic had been seen: milestone 4 had already published block-bootstrap and Newey–West p-values on the real out-of-sample loss differentials. The [addendum](validation/m5-preregistration-addendum.md) corrects them.
- **Not a fresh holdout:** milestone 4 scored both windows once.
- **What is measured:** the log forecast loss on AAPL's adjusted close, a proxy. It is not a trading P&L.

---

## External FAQ

**Is this a trading tool or investment advice?**
No. It is an educational study of one statistical method on one stock. Nothing in it is a recommendation to buy or sell anything.

**Did any model beat the random walk?**
Not one day ahead: every one-step forecast has a higher dollar RMSE than the random walk, on both windows (ratios 1.0056 to 1.0174), and no DM test (DM-HLN, per test, uncorrected) says "better". The AIC model's static paths, the only ones with a drift, have 0.4134 (test) and 0.5370 (out of sample) of a flat line's RMSE while the price kept rising; a random walk with the same drift comes out close on the one test path ($10.339 against $10.632), one path each and not a test, which points to the drift rather than the ARMA terms. The [README's results table](../README.md#results) has every model, method and window.

**Do I need a paid data subscription?**
No. Prices come from Yahoo Finance through the open-source `yfinance` library and are cached on your machine. Yahoo's terms of service govern that data. The raw download stays on your machine. The exported files the app reads are committed, by the owner's decision of 2026-10-29 (open question 2 below); `prices.json`, `eda.json` and the seven forecast files carry prices. A fresh clone runs the whole app. [`DATA.md`](../DATA.md) says that the data is not covered by the repository's MIT licence.

**Why Apple, and why these dates?**
The course outline uses AAPL from 2015 to 2023, and following it lets you compare our steps with the original. The 2024–2026 window is added because a model judged only on data its builders could see has not really been tested.

**If ARIMA on prices ends up close to a random walk, why bother?**
It did end up there, and showing that properly is the skill. You have to identify the model, check its residuals, forecast honestly and compare it with a baseline. The same steps carry over to volatility, which does show strong autocorrelation; that is project 1 of this series, implied-volatility forecasting.

**How is the work staged?**
In six milestones, each paused for review; all six are built:
- **0:** scaffold, data contract, design.
- **1:** course modules 2–4 (data, preprocessing, EDA).
- **2:** modules 5–6 plus the train/test split, which moves earlier so that order selection sees training data only.
- **3:** modules 7–8 (fit, residual diagnostics).
- **4:** modules 9–10 (forecast, evaluation), with walk-forward and random-walk forecasts added.
- **5:** "where the sample goes wrong", and polish.

**Will my numbers match the course's?**
Not exactly, and the repository explains why. The library versions differ (for example, `yfinance` now adjusts prices for splits and dividends by default), the order-selection leak is fixed, and the drift the course's refit drops is kept. The course's code also no longer runs as written on these versions (measured on simulated data): its forecast step stops with an error, because statsmodels 0.15 cannot forecast from a trading-day date index, which has no fixed frequency because of holidays; and once that is worked around, its MAPE line prints `nan`, because `yfinance` 1.7.0 returns the closing prices as a one-column table, which pandas lines up with the forecast by label instead of by row.

**Can I run it on another ticker?**
The ticker is a single constant in `src/arima_forecasting/config.py`. Other tickers are untested.

---

## Internal FAQ

**Data: where does it come from, and is it reproducible?**
From Yahoo Finance via `yfinance==1.7.0`. Yahoo's adjusted history can change after the fact (a new dividend re-scales every earlier adjusted price), so a re-download is not guaranteed to match a past one. The loader therefore caches the raw download outside the repo, at `$VOL_DATA_DIR/arima-stock-forecasting/raw/`, `prices.json` carries the snapshot's SHA-256, and every exported file names the code commit that produced it. Raw data is never committed. With `SOURCE_DATE_EPOCH` set, a re-export is byte-identical, and `tools/export_app_data.py --check` says whether the committed files are current.

**Is it feasible on the build machine (Linux aarch64, Python 3.12)?**
Yes, measured. `pmdarima==2.1.1` installs from an official Linux aarch64 wheel for Python 3.12 and runs with numpy 2. The full export, the AIC grid and every forecast included, took 862 s in milestone 4's measured run on a shared machine. The walk-forward forecast avoids one refit per day: it filters the data once at fixed parameters, and the primary model is also re-estimated every 21 days (`evaluation.json`, `refit_every`).

**What are the main risks, and how did they turn out?**
- **`yfinance` breaks.** It reads Yahoo's unofficial endpoints. The cached raw file means analysis keeps working, the loader fails loudly instead of returning partial data, and the committed exports let a clone run without any download.
- **Leakage creeps back in.** Order selection, differencing and any scaling are fitted on the training window only; `tests/test_export.py` (`test_the_order_selection_payloads_use_the_training_rows_only`) checks it.
- **Overclaiming.** Every metric sits next to the random-walk baseline; every DM verdict is labelled DM-HLN, per test, uncorrected; the README's results tables are printed from `evaluation.json` and pinned by `tests/test_results_table.py`. The milestone-5 numbers in the README and in this document are re-measured by the `verifier` before they are final (pending at the time of writing).
- **Fits that fail to converge.** Failed and unconverged fits are recorded with their status, never dropped silently, and the AIC landscape draws them.

**How will we know it worked?** These are the launch criteria, with where each stands.
- Every forecast method is reported against the random walk on both windows, with RMSE, MAE and MAPE. **Met:** `evaluation.json` scores 14 model, method and window combinations against 4 random-walk baselines.
- A number goes into the README or this document only after the `verifier` agent (an independent checker that re-runs each measurement) has reproduced it. **Met at milestone 5:** the verifier re-measured the numbers, paths and commands in the README and in this document, and what it disagreed with was fixed before the milestone-5 commit.
- `uv run pytest`, the notebook sync check and `npm run verify` (the app's lint, test, coverage and build gate) all pass, and every test has been seen to fail when the code it guards is broken. **Met at milestone 5:** the gate results are in the milestone-5 walkthrough, and each new or changed test's hand mutant is in [`docs/validation/m5-mutant-ledger.md`](validation/m5-mutant-ledger.md).
- Each milestone passes an adversarial review: a separate reviewer tries to refute the milestone's claims and its evidence is kept. **Met for milestones 0 to 4** (the ledgers of milestones 0 to 2 are in `docs/validation/`; milestones 3 and 4 record their reviews and fix rounds in their walkthroughs); **milestone 5 in part:** an adversarial reviewer attacked the procedure of the pre-registered re-analysis, and its corrections are in [`docs/validation/m5-preregistration-addendum.md`](validation/m5-preregistration-addendum.md). No adversarial review of milestone 5's code as a whole was run, and none is pending.
- Most important: the owner can answer each milestone's explain-it-back questions without notes. **The owner's**; `LEARNING_LOG.md` tracks it.

**What will we not do?**
- No trading signals, no backtest and no claim of an edge.
- No machine-learning models. LSTM forecasting belongs to project 1 (implied-volatility forecasting).
- No live data feed: results are fixed to the stated windows, and the out-of-sample window ends on 30 September 2026 so that the numbers stay reproducible.
- No bulk raw data. The raw download is never committed. The exported data the app and the docs need is committed: decided by the owner on 2026-10-29 (open question 2, answered; see `DATA.md`).
- No copying of the course's text or code. Only its module structure is followed, and it is credited.

---

## Open questions for the owner

### Closed

2. **Answered.** Should the app's price series (`prices.json`, and the actual prices drawn under the forecasts) be committed? Committing them lets the app run straight from GitHub, but it redistributes Yahoo-derived prices. The alternatives are listed at the end of `docs/adr/0001-python-computes-app-visualises.md`. **Decided by the owner on 2026-10-29: committed.** The project is a portfolio, so the real data the app and the docs need goes into the repository, and a fresh clone runs the whole app. Bulk raw files (the snapshot CSV, its manifest, yfinance's caches) stay out, and `tests/test_repo_data.py` fails if git tracks one. Milestone 1 had held `prices.json` and `eda.json` (git-ignored, named in `meta.held_artifacts`); `held_artifacts` is now empty. `DATA.md` names the source and its terms. The public history stays as it is.
3. **Default taken in milestone 5: interviewers.** Who is the main reader: interviewers looking at your GitHub, or other learners? The README is written for an interviewer with five minutes: the question, the headline result, the results table, the mistakes and their costs, then screenshots and how to run it; the learning docs follow it. You can override this.
4. **Default taken on 2026-10-29: added; the results are in.** Should milestone 4 add a Diebold–Mariano test of "ARIMA vs random walk", or should that stay in project 1? Each model's one-step walk-forward forecast is tested against the random walk on both windows, with Harvey, Leybourne and Newbold's small-sample correction, on squared and on absolute log errors, two-sided at 5% ([ADR-0003](adr/0003-evaluation-protocol.md), `src/arima_forecasting/evaluation.py`). The static path is not tested (one path from one origin). Result (DM-HLN, per test, uncorrected): 5 of 16 tests "worse than the random walk", 11 "no difference", none "better". After the pre-registered re-analysis with Holm's correction over all 28 comparisons, 1 "worse" survives (see Inference robustness); it is not a fresh holdout, and its metric is log loss on the adjusted close, not a P&L. You can override this.
5. **Default taken on 2026-10-29.** Should the 14-day package-age rule apply to Python too? The app holds every npm package to at least 14 days old, but `uv.lock` pins 17 Python packages that were younger than that when it was written on 2026-10-28 (among them the direct dependencies `pandas==3.1.0`, 6 days old, and `pytest==9.2.0`, under a day). Applying the rule would change the pinned statistics stack whose behaviour the docs cite at `file:line`, so every such citation would need re-checking. **Default: keep the current Python pins, and require every new or upgraded Python pin to be at least 14 days old on the day it is locked.** You can override this.

### Still open

1. **Draft for owner review.** Write the leader quote (the "Project owner" quote above) in your own words.
6. **Draft for owner review.** Keep, rewrite or remove the illustrative persona quote ("Hypothetical learner").
7. **Draft for owner review.** The launch date.
8. **Default taken in milestone 5, open to you:** no "Where the course goes wrong" page in the app. Every cost is in the milestone-5 walkthrough and notebook 05, and most are already on the Fit and Forecast pages. A page would need a small Python-computed artifact, validators in both readers and a full re-export. Do you want it?
9. Hero renders: Blender was unreachable during milestone 5, so the README uses stills of the app's three.js views. Do you want Blender renders later?
10. The inference re-analysis has landed (plan v1's block bootstrap failed its size check; plan v2's EWC test with Holm over 28 ran): its numbers are in the marked section above and the README's; how much of it the README's headline should carry is yours to decide.
