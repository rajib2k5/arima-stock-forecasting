"""What goes into the JSON files the web app reads. Pure: builds dicts, writes nothing.

`tools/export_app_data.py` is the thin wrapper that wraps these payloads in the envelope
(see contract.py) and writes them to disk. The field-by-field description of every payload is
docs/architecture/contract.md, section 3.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

import pandas as pd

from arima_forecasting import eda
from arima_forecasting.config import (
    COURSE_WINDOW,
    OOS_WINDOW,
    PROJECT_SLUG,
    TICKER,
    TRAIN_FRACTION,
    StudyWindow,
)
from arima_forecasting.data import PROVIDER, Snapshot
from arima_forecasting.diagnostics import residual_payloads
from arima_forecasting.evaluation import evaluation_payload
from arima_forecasting.fitting import MODEL_IDS, fit_models
from arima_forecasting.forecasting import FORECAST_ARTIFACTS, forecast_payloads
from arima_forecasting.identification import acf_pacf_payload
from arima_forecasting.prep import clean_close, price_table, segment_bounds
from arima_forecasting.selection import aic_grid_payload
from arima_forecasting.stationarity import stationarity_payload

TITLE = "ARIMA stock forecasting, done carefully"

# (id, slug, title, status) for every milestone. Exactly one is "current". When a milestone
# ships, move "current" down one row; the app shows this list as the project's progress bar.
_MILESTONES = (
    (0, "scaffold", "Scaffold, contract and design", "done"),
    (1, "data-eda", "Data and EDA", "done"),
    (2, "stationarity", "Stationarity and identification", "done"),
    (3, "fit-diagnostics", "Fit and diagnostics", "done"),
    (4, "forecast-eval", "Forecast and evaluation", "current"),
    (5, "where-it-goes-wrong", "Where the sample goes wrong, and polish", "planned"),
)

# Every artifact one export writes, in the order the tool writes them. meta lists exactly these, so
# the app knows which views it can switch on.
# The residual plot series are one file per fitted model (see diagnostics.residual_payloads), and the
# forecasts one file per model and method (forecasting.FORECASTS).
RESIDUAL_ARTIFACTS = tuple(f"residuals_{model_id}" for model_id in MODEL_IDS)
ARTIFACTS = ("meta", "prices", "eda", "stationarity", "acf_pacf", "aic_grid", "fit", *RESIDUAL_ARTIFACTS, *FORECAST_ARTIFACTS, "evaluation")

# Artifacts the export writes but the repository does not commit (meta.data.held_artifacts). Empty
# since the owner's decision of 2026-10-29: every exported file is committed, prices.json and
# eda.json included (DATA.md, ADR-0001). The mechanism stays: the root .gitignore would have to
# ignore exactly these files (tests/test_gitignore.py checks it), and a copy that lacks a held file
# says how to build it instead of failing. Removing the meta field would be a major schema bump.
HELD_ARTIFACTS: tuple[str, ...] = ()


def _window(window: StudyWindow) -> dict[str, str]:
    # ISO text ("2015-01-01"), because JSON has no date type.
    return {"start": window.start.isoformat(), "end_exclusive": window.end_exclusive.isoformat()}


def meta_payload() -> dict[str, Any]:
    """The `data` part of the "meta" artifact: what this project is and how far along it is.

    Windows and ticker come from config.py, not from retyped literals, so the app can never
    show dates that differ from the dates the Python code actually uses.
    """
    return {
        "project": PROJECT_SLUG,
        "title": TITLE,
        "ticker": TICKER,
        "windows": {window.name: _window(window) for window in (COURSE_WINDOW, OOS_WINDOW)},
        "milestones": [
            {"id": number, "slug": slug, "title": title, "status": status}
            for number, slug, title, status in _MILESTONES
        ],
        "artifacts": list(ARTIFACTS),
        "held_artifacts": list(HELD_ARTIFACTS),
    }


PRICE_BASIS = "adjusted_close"
FILL_METHOD = "ffill"


def source_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The `source` block of `prices`: where the snapshot came from, copied from its manifest.

    `downloaded_at` is the manifest's time, not the export clock, so a re-export of the same
    snapshot writes the same block.
    """
    request = manifest["request"]
    return {
        "provider": PROVIDER,
        "yfinance_version": manifest["yfinance_version"],
        "raw_sha256": manifest["sha256"],
        "raw_rows": int(manifest["rows"]),
        "downloaded_at": manifest["downloaded_at"],
        "request": {
            "start": request["start"],
            "end_exclusive": request["end"],
            "interval": request["interval"],
            "auto_adjust": request["auto_adjust"],
        },
    }


def prices_payload(
    table: pd.DataFrame, filled_dates: Iterable[date], source: Mapping[str, Any]
) -> dict[str, Any]:
    """The `data` part of the "prices" artifact: every trading day of both windows, labelled.

    `table` comes from prep.price_table: close_usd, log_close and segment, indexed by date.
    """
    in_table = set(table.index.date)
    return {
        "ticker": TICKER,
        "price_basis": PRICE_BASIS,
        "source": dict(source),
        "fill": {
            "method": FILL_METHOD,
            "filled_dates": [day.isoformat() for day in sorted(filled_dates) if day in in_table],
        },
        "splits": {"train_fraction": TRAIN_FRACTION, **segment_bounds(table)},
        "rows": [
            {
                "date": ts.date().isoformat(),
                "close_usd": float(close),
                "log_close": float(log_close),
                "segment": segment,
            }
            for ts, close, log_close, segment in zip(
                table.index, table["close_usd"], table["log_close"], table["segment"], strict=True
            )
        ],
    }


def eda_payload(table: pd.DataFrame) -> dict[str, Any]:
    """The `data` part of the "eda" artifact. Only the training rows are used."""
    train = table[table["segment"] == "train"]
    returns = eda.log_returns(train["log_close"])
    return {
        "sample": "train",
        "summary": eda.summary(train),
        "kdes": [
            eda.kde(train["log_close"].to_numpy(), "log_close"),
            eda.kde(returns.to_numpy(), "log_return"),
        ],
        "decomposition": eda.decomposition(train["log_close"]),
    }


def order_selection_payloads(table: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """The three milestone-2 payloads, from the training rows of the price table only.

    The unit-root tests choose d first; the AIC grid then ranks (p, q, trend) within that d only
    (ADR-0002, sections 2 and 3).
    """
    train = table.loc[table["segment"] == "train", "log_close"].to_numpy()
    stationarity = stationarity_payload(train)
    return {
        "stationarity": stationarity,
        "acf_pacf": acf_pacf_payload(train),
        "aic_grid": aic_grid_payload(train, stationarity["decision"]["d_selected"]),
    }


def fit_payloads(table: pd.DataFrame, aic_grid: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The milestone-3 payloads: the three fits with their residual tests (`fit`), and each model's
    residual plot series (`residuals_<id>`). The fits use the training rows; the course's
    auto_arima uses the training and test rows, as the course does (fitting.py)."""
    train = table[table["segment"] == "train"]
    course = table[table["segment"] != "oos"]
    fit, results = fit_models(train["log_close"].to_numpy(), course["log_close"].to_numpy(), aic_grid)
    series = residual_payloads(fit, results, train.index)
    return {"fit": fit, **series}


def forecast_evaluation_payloads(table: pd.DataFrame, fit: dict[str, Any], residuals: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The milestone-4 payloads: one forecast file per model and method, on the test and oos windows,
    from the fitted parameters in `fit` and each model's residual t fit; then `evaluation`, computed
    from those files' rows. The parameters come from the training rows; the filters see every row
    before each forecast (forecasting.py)."""
    forecasts = forecast_payloads(table, fit, residuals)
    return {**forecasts, "evaluation": evaluation_payload(forecasts, fit)}


def price_payloads(snapshot: Snapshot) -> tuple[dict[str, dict[str, Any]], pd.DataFrame]:
    """The milestone-0 and milestone-1 payloads (meta, prices, eda) from one raw snapshot, and the
    price table they come from. No model is fitted, so this takes seconds (notebook 01 uses it)."""
    cleaned = clean_close(snapshot.frame)
    table = price_table(cleaned.close)
    payloads = {
        "meta": meta_payload(),
        "prices": prices_payload(table, cleaned.filled_dates, source_from_manifest(snapshot.manifest)),
        "eda": eda_payload(table),
    }
    return payloads, table


def build_payloads(snapshot: Snapshot, aic_grid: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Every payload one export writes, keyed by artifact name, from one raw snapshot.

    `aic_grid` (an existing aic_grid payload) skips the grid, which takes minutes, and is used in
    its place; only `tools/export_app_data.py --only` passes it, to rebuild the later artifacts."""
    first, table = price_payloads(snapshot)
    if aic_grid is None:
        order = order_selection_payloads(table)
    else:
        train = table.loc[table["segment"] == "train", "log_close"].to_numpy()
        order = {"stationarity": stationarity_payload(train), "acf_pacf": acf_pacf_payload(train), "aic_grid": aic_grid}
    fitted = fit_payloads(table, order["aic_grid"])
    residuals = {name: data for name, data in fitted.items() if name != "fit"}
    payloads = {**first, **order, **fitted, **forecast_evaluation_payloads(table, fitted["fit"], residuals)}
    if tuple(payloads) != ARTIFACTS:  # pragma: no cover - a guard for whoever edits this list
        raise RuntimeError(f"payloads {tuple(payloads)} do not match ARTIFACTS {ARTIFACTS}")
    return payloads
