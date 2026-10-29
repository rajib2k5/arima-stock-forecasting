# Data

This repository contains market data. This page says where it comes from, which terms govern it,
what is committed and what is not.

## Sources

| Data | Source and terms |
|---|---|
| AAPL daily prices (open, high, low, close, volume) | Yahoo Finance via yfinance; Yahoo's terms of service govern its use. |

There is no other data source. Every number in the app, the notebooks and the docs is computed from
one download of AAPL's daily prices from that source.

**The data is not covered by this repository's MIT licence.** The licence covers the code and the
text written for this project. The prices, and files derived from them, remain under Yahoo's terms.

## What is committed

The JSON files the app reads, in `app/public/data/`:

| File | What it holds |
|---|---|
| `meta.json` | The project's description, study windows and milestone list. No market data. |
| `prices.json` | AAPL's adjusted daily close and its natural log for every trading day of the two study windows (2015-01-02 to 2026-09-30), with the train, test and out-of-sample labels and the snapshot's SHA-256. |
| `eda.json` | A summary, two kernel density estimates and a decomposition of the training segment. Its decomposition rows carry the training log closes. |
| `stationarity.json` | ADF and KPSS test results for the training log price and its differences. |
| `acf_pacf.json` | Autocorrelations and partial autocorrelations of the same three series, with their bands. |
| `aic_grid.json` | AIC values and fit diagnostics of 144 ARIMA fits on the training segment. |

**Why:** the project is a portfolio. The owner decided on 2026-10-29 that the real data the app and
the docs need goes into the repository, so a fresh clone runs the whole app and every test without a
download. The docs may quote real AAPL values. Tests use made-up values.

## What is not committed

| File | Where it lives | Why not |
|---|---|---|
| The raw snapshot, `AAPL_1d_2015-01-01_2026-10-01.csv` | `$VOL_DATA_DIR/arima-stock-forecasting/raw/` | Bulk raw vendor data. `tools/fetch_prices.py` downloads it again. |
| Its manifest, `AAPL_1d_2015-01-01_2026-10-01.manifest.json` | next to the snapshot | It describes the raw file, which is not here. Its SHA-256 is copied into `prices.json`. |
| yfinance's caches (`cookies.db`, `tkr-tz.db`) | `$VOL_DATA_DIR/arima-stock-forecasting/cache/` | Local state of the download library. |

`.gitignore` keeps these out: the anchored `/data/`, `/raw/` and `/cache/`, and any
`arima-stock-forecasting/raw/` or `cache/` folder at any depth.

## How the rule is checked

`tests/test_repo_data.py` runs with `uv run pytest`. It fails if git tracks, or `git add -A` would
stage:

- a raw vendor file: anything under the top-level `data/`, anything in a folder named `raw/` or
  `cache/`, a snapshot CSV or manifest named like the ones above, or a `*.db` file;
- a file under `app/public/data/` larger than 10 MB.

`tools/licensing/scan_real_rows.py` compares committable text files with the local raw snapshot and
lists lines that copy its values. It was the gate before a push while the price files were held. It is
now an optional tool.

## History

Milestone 1 (commit `2a52d8d`) held `prices.json` and `eda.json` out of the repository while the
owner decided. Milestone 2 commits them. The public history stays as it is.
