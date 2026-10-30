# Learning log

Learning mode: queued

How to use this repo to learn: work through one milestone at a time.
1. Read its walkthrough.
2. Answer the **predict before you look** questions *before* you read the results section.
3. Read the concept notes it points to.
4. Answer the **explain it back** questions without notes. The session grades your answers and fills the gaps.

| # | Milestone | Walkthrough | Concepts | Status | Checkpoint |
|---|---|---|---|---|---|
| 0 | Scaffold, data contract, design | [00-scaffold](docs/milestones/00-scaffold.md) | [00-background](docs/concepts/00-background.md), [01-reproducibility-and-contracts](docs/concepts/01-reproducibility-and-contracts.md) | done | queued, 0 of 17 answered |
| 1 | Data and EDA (course modules 2–4) | [01-data-and-eda](docs/milestones/01-data-and-eda.md) | [02-adjusted-prices-snapshots-and-forward-fill](docs/concepts/02-adjusted-prices-snapshots-and-forward-fill.md), [03-log-returns-fat-tails-and-kde](docs/concepts/03-log-returns-fat-tails-and-kde.md), [04-classical-decomposition-additive-on-logs](docs/concepts/04-classical-decomposition-additive-on-logs.md) | done |  queued, 0 of 15 answered |
| 2 | Stationarity and identification (modules 5–6, split moved earlier) | [02-stationarity-and-identification](docs/milestones/02-stationarity-and-identification.md) | [05-adf-kpss-power-and-the-two-by-two-table](docs/concepts/05-adf-kpss-power-and-the-two-by-two-table.md), [06-acf-pacf-and-their-bands](docs/concepts/06-acf-pacf-and-their-bands.md), [07-aic-within-one-d-and-the-landscape](docs/concepts/07-aic-within-one-d-and-the-landscape.md) | done | queued, 0 of 15 answered |
| 3 | Fit and diagnostics (modules 7–8) | [03-fit-and-diagnostics](docs/milestones/03-fit-and-diagnostics.md) | [08-residual-diagnostics](docs/concepts/08-residual-diagnostics.md), [09-parameter-inference-and-root-cancellation](docs/concepts/09-parameter-inference-and-root-cancellation.md) | done | queued, 0 of 15 answered |
| 4 | Forecast and evaluation (modules 9–10, plus walk-forward and random walk) | [04-forecast-and-evaluation](docs/milestones/04-forecast-and-evaluation.md) | [10-forecast-evaluation-and-diebold-mariano](docs/concepts/10-forecast-evaluation-and-diebold-mariano.md), [11-log-normal-back-transform-and-interval-coverage](docs/concepts/11-log-normal-back-transform-and-interval-coverage.md) | current: built | |
| 5 | Where the sample goes wrong, and polish | — | — | planned | |

## Queued checkpoints

- Milestone 00 (queued, 0 of 17 answered). Answer in its quiz widget, or say "quiz me on milestone 0" to resume it.
- Milestone 01 (queued, 0 of 15 answered). Answer in its quiz widget, or say "quiz me on milestone 1" to resume it.
- Milestone 02 (queued, 0 of 15 answered). Answer in its quiz widget, or say "quiz me on milestone 2" to resume it.
- Milestone 03 (queued, 0 of 15 answered). Answer in its quiz widget, or say "quiz me on milestone 3" to resume it.

## Decisions and defaults

- **Data policy: decided by the owner on 2026-10-29. It is final, and it replaces the strict rule set earlier that day.** This repo is a portfolio, so it commits the real data that the app and the docs need: `prices.json`, `eda.json` and the other exported JSON. Docs may quote real values. It never commits bulk raw files: the yfinance snapshot CSV, its manifest and the caches stay in the git-ignored `data/`. No committed data file may exceed 10 MB. The terms are in `DATA.md`. Tests keep their made-up values. Public history stays as it is.
- **The 14-day package-age rule for Python.** Default taken 2026-10-29, owner can override. Keep the current `uv.lock` pins, because the docs cite their behaviour at `file:line`. Every Python pin added or upgraded from now on must be at least 14 days old when it is locked.
- **Milestone 3 fits three models; the AIC choice is the primary model.** Default taken 2026-10-29, owner can override. The fit artifact holds ADR-0002's AIC choice (the primary model, which milestone 4 forecasts first), BIC's choice and the course's own refit, so the residual tests can compare them. Whether milestone 4 keeps the other two as comparisons is open (milestone-3 walkthrough, "What is next").
- **Near-cancelling roots are flagged within `CANCEL_DISTANCE` = 0.1, as a display rule.** Default taken 2026-10-29 in the milestone-3 fix round, owner can override. The rule is now a maximum matching (as many AR–MA pairs within 0.1 as possible, one to one, then the least total distance), not closest first; on AAPL both give the same pairs. It is not a test of a common factor (concept note 09).
- **The page shows statsmodels' OPG standard errors; the robust (sandwich) ones are measured in the docs only.** Default taken 2026-10-29, owner can override. OPG is what the course's `summary()` prints. For the AR and MA coefficients the sandwich errors are 1.80 to 1.99 times OPG, because the residuals' volatility clusters (concept note 09).
- **Ljung–Box takes `model_df` = p + q.** Default taken 2026-10-29, owner can override. statsmodels' `df_adjust=True` would count every parameter but one, the drift included (8 for the AIC choice, where p + q = 7); the verdicts are the same either way.
- **A Ljung–Box verdict is "any applied lag rejects at 5%", unadjusted for testing several lags.** Default taken 2026-10-29, owner can override. The app's reading says so. BIC's "found" rests on it: Holm's adjustment across its three lags gives 0.0545 (milestone-3 walkthrough, review fix round).
- **Milestone 4 forecasts all three fitted models; the page opens on the AIC choice.** Default taken 2026-10-29, owner can override. Seven forecast files (AIC: static, walk-forward, refit; BIC and course: static, walk-forward), one per model and method because a model's paths together pass the 1 MB budget.
- **Volatility clustering is reported, not modelled.** Default taken 2026-10-29, owner can override. No GARCH layer (project 1's ground); its effect on the intervals is measured instead (milestone-4 walkthrough: the test window's one-step errors are 0.66 times the stated sd).
- **Intervals: the normal (statsmodels' and the course's) is primary; a Student-t with the milestone-3 residual fit's df, scaled to the forecast variance, is reported beside it.** Default taken 2026-10-29, owner can override. Coverage of both at 80% and 95% on each window; one-step coverage tested with Kupiec's LR, static coverage shown and not tested.
- **PR/FAQ question 4: a Diebold–Mariano test is added.** Default taken 2026-10-29, owner can override. Each one-step forecast against the random walk, Harvey–Leybourne–Newbold correction, squared and absolute log errors, two-sided at 5% (ADR-0003). A forecast within 1e-9 log points of the random walk's is "same_as_rw" and not tested.
- **No Newey–West DM in the contract; the γ̂₀ test stays primary; the robustness checks are in the docs.** Default taken 2026-10-30 in the third review pass, owner can override. The second pass's claim that the oos squared-loss differentials of BIC and the course model are robustly autocorrelated is withdrawn: its White (HC0) joint test rejects 38% and 49% of the time under a sign-flip null with no autocorrelation (calibrated p 0.15 and 0.34), while the γ̂₀ test against t(n − 1) rejects 4.0% to 5.7% of the time, so it is correctly sized here. Every oos squared-loss verdict is borderline (five days carry 60% to 74% of the squared deviations; Newey–West at 9 lags or a block bootstrap moves the AIC, AIC-refit and BIC verdicts across 5%); the absolute-loss "worse than the random walk" verdicts hold under every variance tried (milestone-4 walkthrough, probe 5; ADR-0003, "Revisit when": not met).
- **Walk-forward protocol: training parameters, the Kalman state updated each day, no refit; plus a refit every 21 trading days for the AIC model as a robustness check.** Default taken 2026-10-29, owner can override. One filter pass takes about 0.03 s; the refit 12 s to 28 s (two runs on a loaded machine). Each refit starts from the previous estimates.
- **Timings are measured in the walkthrough, not stored in `evaluation.json`.** Decided 2026-10-29 against the brief's suggestion, owner can override: the contract keeps wall-clock values out of `data` (§2, "Determinism"), so `--check` and byte-identical re-exports keep working.
- **The headline dollar metric is on the median, exp(μ), as the course reports; the mean's metrics sit beside it. The DM test uses log errors.** Default taken 2026-10-29, owner can override.
- **The project's windows are pinned in both readers.** Default taken 2026-10-30 in the third review pass, owner can override. `meta.windows.oos` must be 2024-01-01 to 2026-10-01 (exclusive), `prices.json`'s oos rows must lie inside that window and its train and test rows before it, and its `train_fraction` must be 0.9 (config.py's constants; a test ties each reader's copy to them). The forecast fixtures are made-up 2021 windows, so the forecast and evaluation files' windows are not pinned to dates; Python ties them to `prices.json`'s splits across files instead. The course window is not pinned.
- **The Method picker's labels are pinned per method id in both readers** (`evaluation.METHOD_LABELS`), not taken from the file. Default taken 2026-10-30, owner can override.
- **Every list in a payload is bounded before it is read, in both readers.** Default taken 2026-10-30, owner can override: lists of days and points at 10,000 (`MAX_LIST`; the download window has 4,291 calendar days), short lists of names at 100 (`MAX_NAMES`), the AIC grid by its dimensions (324 cells, 6 orders, 3 specs; pmdarima's 2 runs of at most 72 fits), the fit's lists by its order and pinned settings, warnings at 100. A longer list is one short problem.
- **A one-step forecast's variance must be its parameters' sigma2 to 1e-4 relative** (`SIGMA2_REL`, Python's cross-file check). Default taken 2026-10-30, owner can override. statsmodels' steady-state switch leaves the one-step variance a constant fraction above sigma2: 2.67e-5 (BIC), 2.38e-7 (course), 5.7e-14 (AIC) on AAPL, measured.
- **A reader stops at 200 problems per file and quotes every value from a file through one function.** Default taken 2026-10-30 in the milestone-4 second fix round, owner can override: `MAX_PROBLEMS` = 200 for the whole file (then one line that says the reader stopped), in both readers, word for word (the corpus's `cap_cases`); `shown()` quotes at most 80 characters of a string and never walks a nested value (contract.md, "Bounds").
- **`prices.json`'s rows must follow the producer's split and its oos coverage rule, not pinned first and last trading days.** Default taken 2026-10-30, owner can override. The train rows must be `int(n × 0.9)` of the course window's n (`prep.train_size`); the oos rows must start at most 7 calendar days after 2024-01-01, end at most 7 before 2026-10-01 and have no gap over 7 days (`prep.check_coverage`, `MAX_GAP_DAYS`), in both readers. The brief asked for the first and last oos rows to equal pinned dates exactly; 2024-01-02 and 2026-09-30 would refuse the synthetic snapshot the tests export (it trades every weekday, so its oos rows start on 2024-01-01), so the producer's own rule was taken instead. It does not see up to four trading days dropped at an edge or inside.
- **The Model picker's labels are pinned per model id in both readers** (`MODEL_LABELS` = `fitting.LABELS`) in the forecast files and `evaluation.json`. Default taken 2026-10-30, owner can override. `fit.json`'s labels are not pinned per file (the fit page draws its own fixed names); Python's cross-file check ties them to the forecast files'.

## Design documents

- [PR/FAQ](docs/prfaq.md): what this project promises, written working backwards.
- [ADR-0001](docs/adr/0001-python-computes-app-visualises.md): Python computes, the app visualises.
- [ADR-0002](docs/adr/0002-order-selection.md): how (p, d, q) and the trend term are chosen.
- [JSON contract](docs/architecture/contract.md) and [diagrams](docs/architecture/README.md).

## Question log

| Milestone | Predict-first | Explain-it-back | Your answers graded |
|---|---|---|---|
| 0 | [questions](docs/milestones/00-scaffold.md#predict-before-you-look) | [questions](docs/milestones/00-scaffold.md#explain-it-back) | not yet |
| 1 | [questions](docs/milestones/01-data-and-eda.md#predict-before-you-look) | [questions](docs/milestones/01-data-and-eda.md#explain-it-back) | not yet |
| 2 | [questions](docs/milestones/02-stationarity-and-identification.md#predict-before-you-look) | [questions](docs/milestones/02-stationarity-and-identification.md#explain-it-back) | not yet |
| 3 | [questions](docs/milestones/03-fit-and-diagnostics.md#predict-before-you-look) | [questions](docs/milestones/03-fit-and-diagnostics.md#explain-it-back) | not yet |

## Validation

Each milestone's adversarial review and evidence ledger: [`docs/validation/`](docs/validation/).
