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
| 1 | Data and EDA (course modules 2–4) | [01-data-and-eda](docs/milestones/01-data-and-eda.md) | [02-adjusted-prices-snapshots-and-forward-fill](docs/concepts/02-adjusted-prices-snapshots-and-forward-fill.md), [03-log-returns-fat-tails-and-kde](docs/concepts/03-log-returns-fat-tails-and-kde.md), [04-classical-decomposition-additive-on-logs](docs/concepts/04-classical-decomposition-additive-on-logs.md) | current | |
| 2 | Stationarity and identification (modules 5–6, split moved earlier) | — | — | planned | |
| 3 | Fit and diagnostics (modules 7–8) | — | — | planned | |
| 4 | Forecast and evaluation (modules 9–10, plus walk-forward and random walk) | — | — | planned | |
| 5 | Where the sample goes wrong, and polish | — | — | planned | |

## Queued checkpoints

- Milestone 00 (queued, 0 of 17 answered). Answer in its quiz widget, or say "quiz me on milestone 0" to resume it.

## Defaults taken (owner can override)

- **`prices.json`: on hold.** The owner has not decided whether Yahoo-derived prices may go in this public repo. Until they decide, `prices.json` is not committed.
- **The 14-day package-age rule for Python.** Default taken 2026-10-29, owner can override. Keep the current `uv.lock` pins, because the docs cite their behaviour at `file:line`. Every Python pin added or upgraded from now on must be at least 14 days old when it is locked.

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
