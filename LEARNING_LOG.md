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
| 3 | Fit and diagnostics (modules 7–8) | [03-fit-and-diagnostics](docs/milestones/03-fit-and-diagnostics.md) | [08-residual-diagnostics](docs/concepts/08-residual-diagnostics.md), [09-parameter-inference-and-root-cancellation](docs/concepts/09-parameter-inference-and-root-cancellation.md) | current: built | |
| 4 | Forecast and evaluation (modules 9–10, plus walk-forward and random walk) | — | — | planned | |
| 5 | Where the sample goes wrong, and polish | — | — | planned | |

## Queued checkpoints

- Milestone 00 (queued, 0 of 17 answered). Answer in its quiz widget, or say "quiz me on milestone 0" to resume it.
- Milestone 01 (queued, 0 of 15 answered). Answer in its quiz widget, or say "quiz me on milestone 1" to resume it.
- Milestone 02 (queued, 0 of 15 answered). Answer in its quiz widget, or say "quiz me on milestone 2" to resume it.

## Decisions and defaults

- **Data policy: decided by the owner on 2026-10-29. It is final, and it replaces the strict rule set earlier that day.** This repo is a portfolio, so it commits the real data that the app and the docs need: `prices.json`, `eda.json` and the other exported JSON. Docs may quote real values. It never commits bulk raw files: the yfinance snapshot CSV, its manifest and the caches stay in the git-ignored `data/`. No committed data file may exceed 10 MB. The terms are in `DATA.md`. Tests keep their made-up values. Public history stays as it is.
- **The 14-day package-age rule for Python.** Default taken 2026-10-29, owner can override. Keep the current `uv.lock` pins, because the docs cite their behaviour at `file:line`. Every Python pin added or upgraded from now on must be at least 14 days old when it is locked.
- **Milestone 3 fits three models; the AIC choice is the primary model.** Default taken 2026-10-29, owner can override. The fit artifact holds ADR-0002's AIC choice (the primary model, which milestone 4 forecasts first), BIC's choice and the course's own refit, so the residual tests can compare them. Whether milestone 4 keeps the other two as comparisons is open (milestone-3 walkthrough, "What is next").
- **Near-cancelling roots are flagged within `CANCEL_DISTANCE` = 0.1, as a display rule.** Default taken 2026-10-29 in the milestone-3 fix round, owner can override. The rule is now a maximum matching (as many AR–MA pairs within 0.1 as possible, one to one, then the least total distance), not closest first; on AAPL both give the same pairs. It is not a test of a common factor (concept note 09).
- **The page shows statsmodels' OPG standard errors; the robust (sandwich) ones are measured in the docs only.** Default taken 2026-10-29, owner can override. OPG is what the course's `summary()` prints. For the AR and MA coefficients the sandwich errors are 1.80 to 1.99 times OPG, because the residuals' volatility clusters (concept note 09).
- **Ljung–Box takes `model_df` = p + q.** Default taken 2026-10-29, owner can override. statsmodels' `df_adjust=True` would count every parameter but one, the drift included (8 for the AIC choice, where p + q = 7); the verdicts are the same either way.
- **A Ljung–Box verdict is "any applied lag rejects at 5%", unadjusted for testing several lags.** Default taken 2026-10-29, owner can override. The app's reading says so. BIC's "found" rests on it: Holm's adjustment across its three lags gives 0.0545 (milestone-3 walkthrough, review fix round).

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

## Validation

Each milestone's adversarial review and evidence ledger: [`docs/validation/`](docs/validation/).
