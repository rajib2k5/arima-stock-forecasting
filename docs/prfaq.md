# PR/FAQ: arima-stock-forecasting

> **Status: milestone-0 draft, written working backwards.** This is the press release we want to be able to publish when milestone 5 ships, written before any model has been fitted. It contains **no results**: every number about forecast accuracy is left to the final milestone and will be measured, not predicted. The quotes are placeholders, clearly marked; the owner rewrites them in their own words.

---

## Press release

### Does a textbook ARIMA forecast of Apple's stock beat a random walk? A new open-source study shows every step of the answer

**For people learning time-series forecasting for quant interviews: a reproducible Python pipeline, an interactive app with 3D views, and concept notes that rebuild a common course project and fix the places where it goes wrong.**

**[Launch date: when milestone 5 ships]**. Today we release `arima-stock-forecasting`, a public repository that forecasts Apple (AAPL) daily closing prices with ARIMA models and asks the one question that decides whether a price forecast is any good: *does it beat a random walk?* A random walk is the simplest possible forecast, "tomorrow's price is today's price"; a model that cannot beat it has learned nothing. The study follows the ten-module structure of a widely used sample course (2015–2023 data, a 90/10 train/test split), then tests the same models on 1 January 2024 to 30 September 2026, a period the models never saw while they were being built. Every forecast is reported next to a random-walk baseline, on both periods, with the code behind each number one click away.

**The problem.** ARIMA stock-forecasting tutorials are everywhere. The sample course this project follows makes four mistakes that are common in them:
1. It picks the model order on the whole series, test period included, so the test is no longer a test.
2. It forecasts the whole test period (the last tenth of nine years of trading days) in one shot, which gives an almost flat line, and calls it a forecast.
3. It reports an error in dollars with nothing to compare it to, so no one can tell whether it is good.
4. It exponentiates a log-price forecast and treats the result as the expected price. That gives the median price, not the mean, because the exponential of an average log is not the average of the prices.

A learner who follows them ends up with a model that runs, and cannot answer the first question an interviewer asks about it.

**The solution.** The repository rebuilds the course project module by module (data, preprocessing, EDA, stationarity, identification, split, fit, diagnostics, forecast, evaluation) in tested Python, and adds what the course leaves out:
- the model order is chosen on the training data only;
- the KPSS test is run alongside ADF, because the two have opposite null hypotheses;
- a walk-forward, one-step-ahead forecast is run alongside the course's static multi-step forecast;
- a random-walk baseline appears under every metric;
- a final note, "where the sample goes wrong", explains each of the four mistakes above and measures what each one costs.

Each milestone ships a code walkthrough with `file:line` references, concept notes with the maths, "predict before you look" questions to answer before reading the results, and "explain it back" interview questions that test whether the reader can explain the code and the maths without notes.

> "[Placeholder: owner's quote, to be written by the owner. It should say why an honest negative result teaches more than a flattering one.]"
> — Project owner

**How it works.** Python does all the computing. A loader pulls AAPL prices from Yahoo Finance through `yfinance` into a local cache outside the repository, in the folder named by the `VOL_DATA_DIR` environment variable (default `~/data/vol-projects`); nothing downloaded is committed. The pipeline fits and evaluates the models and writes versioned JSON files, each stamped with a schema version, a timestamp and the git commit that produced it. A React app reads only those files and draws them:
- a price and log-price explorer;
- a stationarity lab, where you toggle differencing and watch ADF and KPSS change their verdicts;
- a 3D landscape of AIC over the model orders (p, q) for each amount of differencing d;
- an animated walk-forward forecast fan against the actual prices;
- residual diagnostics.

Notebooks are generated from the same source code, and a test fails if they drift from it.

> "[Placeholder: an illustrative learner persona's quote, not a real person. Example of the reaction we are aiming for: 'I finally understand why my ARIMA forecast was a flat line, and I can say in one sentence what that line means.']"
> — Hypothetical learner

**Get started.** Clone the repository, run `uv sync`, `uv run pytest` and `uv run python tools/export_app_data.py` (which writes the JSON the app reads), then `cd app && npm ci && npm run dev`. Before you read any milestone's results, answer its predict-first questions in `docs/milestones/`.

---

## External FAQ

**Is this a trading tool or investment advice?**
No. It is an educational study of one statistical method on one stock. Nothing in it is a recommendation to buy or sell anything.

**Do I need a paid data subscription?**
No. Prices come from Yahoo Finance through the open-source `yfinance` library and are cached on your machine. Yahoo's terms of service govern that data. The raw download stays on your machine. The two derived files that carry prices, `prices.json` and `eda.json`, are committed, by the owner's decision of 2026-10-29 (open question 2 below), so a fresh clone runs the whole app; [`DATA.md`](../DATA.md) says what is committed and that the data is not covered by the repository's MIT licence.

**Why Apple, and why these dates?**
The course outline uses AAPL from 2015 to 2023, and following it lets you compare our steps with the original. The 2024–2026 window is added because a model judged only on data its builders could see has not really been tested.

**If ARIMA on prices ends up close to a random walk, why bother?**
Because showing that properly is a skill. You have to identify the model, check its residuals, forecast honestly and compare it with a baseline. The same steps carry over to volatility, which does show strong autocorrelation; that is project 1 of this series, implied-volatility forecasting.

**How is the work staged?**
In six milestones, each paused for review:
- **0:** scaffold, data contract, design.
- **1:** course modules 2–4 (data, preprocessing, EDA).
- **2:** modules 5–6 plus the train/test split, which moves earlier so that order selection sees training data only.
- **3:** modules 7–8 (fit, residual diagnostics).
- **4:** modules 9–10 (forecast, evaluation), with walk-forward and random-walk forecasts added.
- **5:** "where the sample goes wrong", and polish.

**Will my numbers match the course's?**
Not exactly, and the repository explains why. The library versions differ (for example, `yfinance` now adjusts prices for splits and dividends by default), and the order-selection leak is fixed. The course's code also no longer runs as written on these versions (measured on simulated data): its forecast step stops with an error, because statsmodels 0.15 cannot forecast from a trading-day date index, which has no fixed frequency because of holidays; and once that is worked around, its MAPE line prints `nan`, because `yfinance` 1.7.0 returns the closing prices as a one-column table, which pandas lines up with the forecast by label instead of by row.

**Can I run it on another ticker?**
The ticker is a single constant in `src/arima_forecasting/config.py`. Other tickers are untested.

---

## Internal FAQ

**Data: where does it come from, and is it reproducible?**
From Yahoo Finance via `yfinance==1.7.0`. Yahoo's adjusted history can change after the fact (a new dividend re-scales every earlier adjusted price), so a re-download is not guaranteed to match a past one. The loader therefore caches the raw download outside the repo, at `$VOL_DATA_DIR/arima-stock-forecasting/raw/`, and every published result names the code commit that produced it. Raw data is never committed.

**Is it feasible on the build machine (Linux aarch64, Python 3.12)?**
Yes, as far as it has been checked (on 2026-10-28). `pmdarima==2.1.1` installs from an official Linux aarch64 wheel for Python 3.12 and runs with numpy 2. The full AIC grid that the 3D view needs is a grid of small statsmodels fits. The expensive part is the walk-forward forecast, which refits or updates the model once per test day; how to keep it fast (refit every k days, or update the state with fixed parameters) is decided and timed in milestone 4, not assumed here.

**What are the main risks?**
- **`yfinance` breaks.** It reads Yahoo's unofficial endpoints. The cached raw file means analysis keeps working, and the loader fails loudly instead of returning partial data.
- **Leakage creeps back in.** Order selection, differencing and any scaling are fitted on the training window only, and a test checks this.
- **Overclaiming.** No sentence in the README or this document states a result that the `verifier` has not re-measured, and every metric sits next to the random-walk baseline.
- **Fits that fail to converge.** Failed fits are recorded with their reason, never dropped silently.

**How will we know it worked?** These are the launch criteria; none is met yet.
- Every forecast method is reported against the random walk on both windows, with RMSE, MAE and MAPE.
- A number goes into the README or this document only after the `verifier` agent (an independent checker that re-runs each measurement) has reproduced it.
- `uv run pytest`, the notebook sync check and `npm run verify` (the app's lint, test, coverage and build gate) all pass, and every test has been seen to fail when the code it guards is broken.
- Each milestone passes an adversarial review: a separate reviewer tries to refute the milestone's claims and commits its evidence ledger under `docs/validation/`.
- Most important: the owner can answer each milestone's explain-it-back questions without notes.

**What will we not do?**
- No trading signals, no backtest and no claim of an edge.
- No machine-learning models. LSTM forecasting belongs to project 1 (implied-volatility forecasting).
- No live data feed: results are fixed to the stated windows, and the out-of-sample window ends on 30 September 2026 so that the numbers stay reproducible.
- No bulk raw data. The raw download is never committed. The exported data the app and the docs need, `prices.json` and `eda.json` included, is committed: decided by the owner on 2026-10-29 (open question 2, now answered; see `DATA.md`).
- No copying of the course's text or code. Only its module structure is followed, and it is credited.

---

## Open questions for the owner (to settle at the milestone-0 checkpoint)

1. Write the leader quote (the "Project owner" quote above) in your own words.
2. **Answered.** Should the app's price series (`prices.json`, and the actual prices drawn under the forecasts) be committed? Committing them lets the app run straight from GitHub, but it redistributes Yahoo-derived prices. The alternatives are listed at the end of `docs/adr/0001-python-computes-app-visualises.md`. **Decided by the owner on 2026-10-29: committed.** The project is a portfolio, so the real data the app and the docs need goes into the repository, and a fresh clone runs the whole app. Bulk raw files (the snapshot CSV, its manifest, yfinance's caches) stay out, and `tests/test_repo_data.py` fails if git tracks one. Milestone 1 had held `prices.json` and `eda.json` (git-ignored, named in `meta.held_artifacts`); `held_artifacts` is now empty. `DATA.md` names the source and its terms. The public history stays as it is.
3. Who is the main reader: interviewers looking at your GitHub, or other learners? This sets the tone of the README.
4. Should milestone 4 add a Diebold–Mariano test of "ARIMA vs random walk", or should that stay in project 1? **Default taken on 2026-10-29: added.** Each model's one-step walk-forward forecast is tested against the random walk on both windows, with Harvey, Leybourne and Newbold's small-sample correction, on squared and on absolute log errors, two-sided at 5% ([ADR-0003](adr/0003-evaluation-protocol.md), `src/arima_forecasting/evaluation.py`). The static path is not tested (one path from one origin). You can override this.
5. Should the 14-day package-age rule apply to Python too? The app holds every npm package to at least 14 days old, but `uv.lock` pins 17 Python packages that were younger than that when it was written on 2026-10-28 (among them the direct dependencies `pandas==3.1.0`, 6 days old, and `pytest==9.2.0`, under a day). Applying the rule would change the pinned statistics stack whose behaviour the docs cite at `file:line`, so every such citation would need re-checking. **Default taken on 2026-10-29: keep the current Python pins, and require every new or upgraded Python pin to be at least 14 days old on the day it is locked.** Milestone 1 added no Python dependency. You can override this.
